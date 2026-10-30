"""GRPO training of a FINER-SQL model with the format + execution reward on CoRE-DB (TRL GRPOTrainer, vLLM colocate)."""
import argparse
import glob
import json
import os
import pickle
import types

import torch
from datasets import Dataset, load_from_disk
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, set_seed
from trl import GRPOConfig, GRPOTrainer

from reward import FormatExecutionReward


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model_path', required=True, help='initial model (HF id or local path)')
    parser.add_argument('--data_root', required=True, help='training prompts (datasets.save_to_disk folder)')
    parser.add_argument('--gt_cache', required=True, help='gold results on CoRE-DB (build_gt_cache.py)')
    parser.add_argument('--out_dir', required=True)
    parser.add_argument('--api_url', default='http://127.0.0.1:8021/execute', help='CoRE-DB execution endpoint')
    parser.add_argument('--max_steps', type=int, required=True)
    parser.add_argument('--save_steps', type=int, default=250)
    parser.add_argument('--learning_rate', type=float, default=8e-6)
    parser.add_argument('--beta', type=float, default=0.04, help='KL coefficient')
    parser.add_argument('--num_generations', type=int, default=32)
    parser.add_argument('--per_device_train_batch_size', type=int, default=4)
    parser.add_argument('--gradient_accumulation_steps', type=int, default=8)
    parser.add_argument('--max_prompt_length', type=int, default=2048)
    parser.add_argument('--max_completion_length', type=int, default=2048)
    parser.add_argument('--vllm_gpu_memory_utilization', type=float, default=0.3)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--resume_from_checkpoint', default=None,
                        help='full TRL checkpoint to continue from; the LR schedule is re-created for --max_steps')
    parser.add_argument('--dynamic_sampling_mask', action='store_true',
                        help='zero the advantages of groups whose rollouts are all paid or all unpaid and skip '
                             'optimizer steps in which every group is masked')
    parser.add_argument('--skip_masked_compute', action='store_true',
                        help='with --dynamic_sampling_mask: skip forward/backward of a fully masked step')
    parser.add_argument('--no_grad_ckpt', action='store_true', help='disable gradient checkpointing')
    parser.add_argument('--ddp_bucket_view', action='store_true', help='multi-GPU: DDP gradient_as_bucket_view')
    args = parser.parse_args(argv)
    if args.skip_masked_compute and not args.dynamic_sampling_mask:
        parser.error('--skip_masked_compute needs --dynamic_sampling_mask')
    return args


def load_rows(data_root):
    """Rows of a saved Dataset / DatasetDict['train'], or of every such folder directly under data_root."""
    def rows_of(path):
        try:
            data = load_from_disk(path)
        except Exception:
            return []
        if isinstance(data, Dataset):
            return data.to_list()
        return data['train'].to_list() if 'train' in data else []

    rows = rows_of(data_root)
    if not rows:
        for name in sorted(os.listdir(data_root)):
            if os.path.isdir(os.path.join(data_root, name)):
                rows.extend(rows_of(os.path.join(data_root, name)))
    if not rows:
        raise RuntimeError('no training prompts in %s' % data_root)
    return rows


def build_dataset(args, tokenizer, gt_cache):
    """Chat-rendered prompts minus golds that timed out on CoRE-DB and prompts longer than max_prompt_length."""
    rows = load_rows(args.data_root)
    for row in rows:
        row['prompt'] = tokenizer.apply_chat_template(row.pop('messages'), tokenize=False, add_generation_prompt=True)
    timed_out = {key for key, value in gt_cache.items() if isinstance(value, dict) and value.get('timeout') is True}
    dataset = Dataset.from_list(rows)
    if timed_out:
        dataset = dataset.filter(
            lambda ex: (ex['dataset_name'], ex['db_id'], ex['groundtruth_sqls'][0]) not in timed_out, num_proc=4)

    def short_enough(ex):
        gold = ex['groundtruth_sqls'][0]
        gold = gold[0] if isinstance(gold, list) else gold
        return len(tokenizer(ex['prompt']).input_ids) <= args.max_prompt_length and len(gold) > 0

    dataset = dataset.filter(short_enough, num_proc=4)
    print('training prompts: %d of %d' % (len(dataset), len(rows)))
    return dataset


def group_keep(paid, num_generations):
    """Per-rollout keep flag: a group of num_generations rollouts is kept iff it holds paid and unpaid rollouts."""
    keep = []
    for start in range(0, len(paid), num_generations):
        n_paid = sum(paid[start:start + num_generations])
        keep.extend([0 < n_paid < num_generations] * num_generations)
    return keep


class CoreDbGRPOTrainer(GRPOTrainer):
    """GRPOTrainer with the dynamic-sampling mask and the DDP bucket-view option."""

    def __init__(self, *a, options, reward, **k):
        self.options = options
        self.reward = reward
        self.step_has_signal = False
        self.batch_all_masked = False
        super().__init__(*a, **k)
        if options.skip_masked_compute and (self.args.steps_per_generation != self.args.gradient_accumulation_steps
                                            or self.num_iterations != 1):
            raise SystemExit('--skip_masked_compute needs steps_per_generation == gradient_accumulation_steps')

    def create_accelerator_and_postprocess(self):
        super().create_accelerator_and_postprocess()
        if self.options.ddp_bucket_view and int(os.environ.get('WORLD_SIZE', '1')) > 1:
            from accelerate.utils import DistributedDataParallelKwargs
            handler = self.accelerator.ddp_handler
            kwargs = handler.to_kwargs() if handler is not None else {}
            kwargs['gradient_as_bucket_view'] = True
            self.accelerator.ddp_handler = DistributedDataParallelKwargs(**kwargs)

    def create_optimizer(self):
        """With the mask, an optimizer step without any kept rollout is skipped (global step and LR still advance)."""
        optimizer = super().create_optimizer()
        if self.options.dynamic_sampling_mask and not getattr(optimizer, 'mask_wrapped', False):
            original_step = optimizer.step
            trainer = self

            def step(_optimizer, *a, **k):
                signal, trainer.step_has_signal = trainer.step_has_signal, False
                trainer._metrics['train']['dyn/step_skipped'].append(0.0 if signal else 1.0)
                return original_step(*a, **k) if signal else None

            optimizer.step = types.MethodType(step, optimizer)
            optimizer.mask_wrapped = True
        return optimizer

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        if self.options.dynamic_sampling_mask and 'dyn_keep' in inputs:
            keep = inputs['dyn_keep']
            if bool(keep.any()):
                self.step_has_signal = True
            elif model.training and self.batch_all_masked and self.options.skip_masked_compute:
                return torch.zeros((), device=keep.device, requires_grad=True)
        return super().compute_loss(model, inputs, return_outputs, **kwargs)

    def _generate_and_score_completions(self, inputs):
        output = super()._generate_and_score_completions(inputs)
        if self.options.dynamic_sampling_mask and self.model.training:
            output = self.apply_mask(output)
        return output

    def apply_mask(self, output):
        """Zero the advantages of uninformative groups and attach the per-row keep flag."""
        advantages = output['advantages']
        paid = [float(p) for p in self.reward.last_paid]
        if len(paid) != advantages.shape[0]:
            raise RuntimeError('%d reward flags for %d advantages' % (len(paid), advantages.shape[0]))
        n_local = len(paid)
        if self.accelerator.num_processes > 1:
            paid = self.accelerator.gather(torch.tensor(paid, device=advantages.device)).tolist()
        keep_all = group_keep([p > 0 for p in paid], self.num_generations)
        offset = self.accelerator.process_index * n_local if self.accelerator.num_processes > 1 else 0
        keep = torch.tensor(keep_all[offset:offset + n_local], dtype=torch.bool, device=advantages.device)
        self.batch_all_masked = not any(keep_all)
        output['advantages'] = torch.where(keep, advantages, torch.zeros_like(advantages))
        output['dyn_keep'] = keep
        return output


class ResumeScheduleCallback(TrainerCallback):
    """On resume, set the optimizer LR to the re-created schedule's value at the resumed step."""

    def on_train_begin(self, args, state, control, optimizer=None, lr_scheduler=None, **kwargs):
        lrs = [base * lam(lr_scheduler.last_epoch) for base, lam in zip(lr_scheduler.base_lrs, lr_scheduler.lr_lambdas)]
        for group, lr in zip(optimizer.param_groups, lrs):
            group['lr'] = lr
        lr_scheduler._last_lr = list(lrs)


def check_checkpoint(checkpoint, n_prompts, prompts_per_step):
    """A full TRL checkpoint whose step lies inside the first epoch (later epochs' orders are not replayed)."""
    world_size = int(os.environ.get('WORLD_SIZE', '1'))
    rng_files = ['rng_state.pth'] if world_size <= 1 else ['rng_state_%d.pth' % r for r in range(world_size)]
    missing = [f for f in ['trainer_state.json', 'optimizer.pt', 'scheduler.pt'] + rng_files
               if not os.path.isfile(os.path.join(checkpoint, f))]
    if missing:
        raise SystemExit('%s is not a full TRL checkpoint, missing %s' % (checkpoint, missing))
    with open(os.path.join(checkpoint, 'trainer_state.json')) as handle:
        step = int(json.load(handle)['global_step'])
    if step >= n_prompts // prompts_per_step:
        raise SystemExit('resume step %d is past the first epoch' % step)


def load_model(model_path, gradient_checkpointing):
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype='bfloat16',
                                                 attn_implementation='flash_attention_2')
    model.config.use_cache = False
    if gradient_checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    return model


def grpo_config(args):
    return GRPOConfig(
        output_dir=args.out_dir, num_train_epochs=-1, max_steps=args.max_steps, logging_steps=1,
        learning_rate=args.learning_rate, gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_generations=args.num_generations, per_device_train_batch_size=args.per_device_train_batch_size,
        loss_type='grpo', per_device_eval_batch_size=1, max_prompt_length=args.max_prompt_length,
        max_completion_length=args.max_completion_length, temperature=1.0, beta=args.beta,
        warmup_ratio=0.0, warmup_steps=0, max_grad_norm=1.0, save_steps=args.save_steps, bf16=True,
        save_total_limit=None, report_to='tensorboard', logging_dir=os.path.join(args.out_dir, 'logs'),
        use_vllm=True, vllm_mode='colocate', vllm_enable_sleep_mode=False,
        vllm_gpu_memory_utilization=args.vllm_gpu_memory_utilization, use_liger_kernel=True, seed=args.seed,
        **({'gradient_checkpointing': False} if args.no_grad_ckpt else {}))


def main():
    args = parse_args()
    set_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    with open(args.gt_cache, 'rb') as handle:
        gt_cache = pickle.load(handle)
    dataset = build_dataset(args, tokenizer, gt_cache)
    reward = FormatExecutionReward(args.api_url, gt_cache)
    config = grpo_config(args)
    trainer = CoreDbGRPOTrainer(model=load_model(args.model_path, not args.no_grad_ckpt), args=config,
                                train_dataset=dataset, reward_funcs=reward, options=args, reward=reward)
    if args.resume_from_checkpoint:
        checkpoint = os.path.abspath(args.resume_from_checkpoint)
        check_checkpoint(checkpoint, len(dataset), max(1, config.generation_batch_size // args.num_generations))
        trainer.add_callback(ResumeScheduleCallback())
        trainer.train(resume_from_checkpoint=checkpoint)
    else:
        trainer.train(resume_from_checkpoint=bool(glob.glob(os.path.join(args.out_dir, 'checkpoint-*'))))


if __name__ == '__main__':
    main()
