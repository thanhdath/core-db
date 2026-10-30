"""Generate SQL candidates with vLLM and execute every candidate through the execution API ($SQL_API_URL).

Writes <output-dir>/predicted_sqls.json (reused when present) and <output-dir>/detailed_results.pkl, the input of
vote_after_verify.py.
"""
import argparse
import json
import multiprocessing
import os
import pickle
import re

import requests
from datasets import DatasetDict, load_from_disk

multiprocessing.set_start_method('spawn', force=True)
os.environ.setdefault('VLLM_WORKER_MULTIPROC_METHOD', 'spawn')
os.environ.setdefault('VLLM_USE_V1', '0')

TIMEOUT_MS = 60000
MAX_ROWS = 10000
MAX_TOKENS = 2048


def extract_sql(text):
    """SQL after the last ``</think>`` tag ('' when missing)."""
    index = text.rfind('</think>')
    return text[index + len('</think>'):].strip() if index >= 0 else ''


def is_select_like(sql):
    return sql.lstrip().lower().startswith(('select', 'with', 'explain'))


def execute(dataset_name, db_id, sql):
    """Execution result {ok, rows, row_count, error, timed_out} of one SQL."""
    payload = {'dataset_name': dataset_name, 'db_id': db_id, 'sql': sql, 'timeout_ms': TIMEOUT_MS,
               'max_rows': MAX_ROWS, 'mode': 'read_only' if is_select_like(sql) else 'sandbox_rollback'}
    try:
        response = requests.post(os.environ['SQL_API_URL'], json=payload, timeout=TIMEOUT_MS / 1000.0 + 2)
        if response.status_code != 200:
            return {'ok': False, 'rows': None, 'error': 'HTTP %d: %s' % (response.status_code, response.text)}
        data = response.json()
    except Exception as exc:
        return {'ok': False, 'rows': None, 'error': str(exc)}
    return {'ok': bool(data.get('ok', False)), 'rows': data.get('rows'), 'row_count': data.get('row_count'),
            'error': data.get('error'), 'timed_out': bool(data.get('timed_out', False))}


def normalize_sql(sql):
    """Cache key of a SQL: trimmed, trailing semicolons dropped, whitespace collapsed."""
    return re.sub(r'\s+', ' ', re.sub(r';+\s*$', '', sql.strip()))


def execute_candidates(entry):
    """Entry plus the execution result of each candidate (the gold and identical candidates are executed once)."""
    cache = {}
    gold = entry['ground_truth_sql']
    if gold and gold.strip():
        cache[normalize_sql(gold)] = execute(entry['dataset_name'], entry['db_id'], gold)
    results = []
    for sql in entry['predicted_sqls']:
        if not sql or not sql.strip():
            results.append({'ok': False, 'rows': None, 'error': 'Empty SQL'})
            continue
        key = normalize_sql(sql)
        if key not in cache:
            cache[key] = execute(entry['dataset_name'], entry['db_id'], sql)
        results.append(cache[key])
    return dict(entry, candidate_execution_results=results)


def load_questions(path, limit):
    data = load_from_disk(path)
    if isinstance(data, DatasetDict):
        data = data['train' if 'train' in data else list(data.keys())[0]]
    return data.select(range(min(limit, len(data)))) if limit else data


def generate(args, questions):
    """Completions per question: n samples with a fixed seed, in batches of --batch-size prompts."""
    import torch
    from transformers import AutoTokenizer, set_seed
    from vllm import LLM, SamplingParams

    set_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    prompts = [tokenizer.apply_chat_template(q['messages'], tokenize=False, add_generation_prompt=True)
               for q in questions]
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
    llm = LLM(model=args.model_path, dtype='bfloat16' if bf16 else 'float16', trust_remote_code=True,
              tensor_parallel_size=1, max_model_len=args.max_model_len,
              gpu_memory_utilization=args.gpu_memory_utilization, enforce_eager=True)
    params = SamplingParams(temperature=args.temperature, max_tokens=MAX_TOKENS, stop=['<|endoftext|>'],
                            n=args.num_samples, seed=args.seed)
    completions = []
    for start in range(0, len(prompts), args.batch_size):
        outputs = llm.generate(prompts[start:start + args.batch_size], params)
        completions.extend([c.text for c in output.outputs] for output in outputs)
    return completions


def predictions(args, questions):
    """Candidates per question, generated once and stored in predicted_sqls.json."""
    path = os.path.join(args.output_dir, 'predicted_sqls.json')
    if os.path.exists(path):
        with open(path) as handle:
            return json.load(handle)
    entries = []
    for question, texts in zip(questions, generate(args, questions)):
        entries.append({'sample_id': question['sample_id'], 'dataset_name': question['dataset_name'],
                        'db_id': question['db_id'], 'question': question['question'],
                        'ground_truth_sql': question['groundtruth_sqls'][0],
                        'predicted_sqls': [extract_sql(t) for t in texts], 'full_completions': texts})
    with open(path, 'w') as handle:
        json.dump(entries, handle, indent=2, default=str)
    return entries


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', required=True, help='HF id or local path')
    parser.add_argument('--data-path', required=True, help='prompts dataset (datasets.save_to_disk folder)')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('-n', '--num-samples', type=int, default=30)
    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--batch-size', type=int, default=8, help='prompts per vLLM generate call')
    parser.add_argument('--limit', type=int, default=0, help='first N questions only; 0 = all')
    parser.add_argument('--gpu-memory-utilization', type=float, default=0.85)
    parser.add_argument('--max-model-len', type=int, default=4096)
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    entries = predictions(args, load_questions(args.data_path, args.limit))
    with multiprocessing.Pool(processes=8) as pool:
        results = pool.map(execute_candidates, entries)
    with open(os.path.join(args.output_dir, 'detailed_results.pkl'), 'wb') as handle:
        pickle.dump(results, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print('%d questions, %d candidates executed' % (len(results), sum(len(r['predicted_sqls']) for r in results)))


if __name__ == '__main__':
    main()
