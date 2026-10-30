#!/usr/bin/env bash
# GRPO on CoRE-DB with the format + execution reward: one prompt x 32 rollouts per optimizer step,
# lr 8e-6 (linear decay), beta 0.04, GRPO loss, prompt/completion length 2048, seed 42, checkpoint every 250 steps.
#
# Usage: DATA_DIR=... GT_CACHE=... OUT_DIR=... training/train.sh <run>
#   run    GPUs  PD x GA  vLLM  steps  start                                              released
#   0.5b   1     4 x 8    0.3   13504  MODEL=griffith-bigdata/FINER-SQL-0.5B-BIRD           checkpoint-6750
#   1.5b-a 2     4 x 4    0.2   3000   RESUME=<1.5B checkpoint-750, FINER-SQL reward>
#   1.5b-b 2     4 x 4    0.2   8892   RESUME=<1.5b-a checkpoint-3000>                    checkpoint-6750
#   3b     1     4 x 8    0.3   1250   MODEL=<3B checkpoint-1750, FINER-SQL reward>       checkpoint-1000
# The reward endpoint (training/serve_coredb.sh) must be running; API_URL overrides it.
set -euo pipefail
: "${DATA_DIR:?}" "${GT_CACHE:?}" "${OUT_DIR:?}"
here=$(cd "$(dirname "$0")" && pwd)
flags=()
case "${1:?run: 0.5b | 1.5b-a | 1.5b-b | 3b}" in
  0.5b) gpus=1 pd=4 ga=8 util=0.3 steps=13504; model=${MODEL:-griffith-bigdata/FINER-SQL-0.5B-BIRD}
        flags=(--dynamic_sampling_mask --skip_masked_compute) ;;
  1.5b-a|1.5b-b) gpus=2 pd=4 ga=4 util=0.2; model=${MODEL:-griffith-bigdata/Qwen-2.5-Coder-1.5B-SQL-Writer}
        steps=$([ "$1" = 1.5b-a ] && echo 3000 || echo 8892)
        flags=(--ddp_bucket_view --no_grad_ckpt --resume_from_checkpoint "${RESUME:?set RESUME}") ;;
  3b) gpus=1 pd=4 ga=8 util=0.3 steps=1250; model=${MODEL:?set MODEL to the 3B checkpoint-1750} ;;
  *) echo "unknown run $1"; exit 2 ;;
esac
config=$here/configs/accelerate_${gpus}gpu.yaml
mkdir -p "$OUT_DIR"
cd "$here"
export PYTHONUNBUFFERED=1 NCCL_CUMEM_ENABLE=0 no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
python -m accelerate.commands.launch --config_file "$config" train_grpo.py \
  --model_path "$model" --data_root "$DATA_DIR" --gt_cache "$GT_CACHE" --out_dir "$OUT_DIR" \
  --api_url "${API_URL:-http://127.0.0.1:8021/execute}" --max_steps "$steps" --save_steps 250 --seed 42 \
  --learning_rate 8e-6 --beta 0.04 --num_generations 32 --per_device_train_batch_size "$pd" \
  --gradient_accumulation_steps "$ga" --vllm_gpu_memory_utilization "$util" \
  --max_prompt_length 2048 --max_completion_length 2048 "${flags[@]}" 2>&1 | tee -a "$OUT_DIR/train.log"
