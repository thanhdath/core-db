"""Reproduce the RQ2 inference numbers of one released model on one benchmark."""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROMPTS_REPO = 'griffith-bigdata/core-db-prompts'
MODELS = {'0.5b': 'griffith-bigdata/FINER-SQL-0.5B-v2',
          '1.5b': 'griffith-bigdata/FINER-SQL-1.5B-v2',
          '3b': 'griffith-bigdata/FINER-SQL-3B-v2'}
BENCHMARKS = {
    'bird_dev': {'prompts': 'bird_dev', 'root': None},
    'spider_dev': {'prompts': 'spider_dev', 'root': 'spider_dev_root'},
    'spider_test': {'prompts': 'spider_test', 'root': 'spider_test_root'},
}
DECODING = {'k30': ['-n', '30', '--temperature', '1.0'], 'greedy': ['-n', '1', '--temperature', '0.0']}


def download_prompts(benchmark, cache_dir):
    """Local folder of the HF prompts dataset with the benchmark's folders."""
    from huggingface_hub import snapshot_download
    spec = BENCHMARKS[benchmark]
    patterns = ['evaluation/%s/*' % name for name in (spec['prompts'], spec['root']) if name]
    snapshot = snapshot_download(PROMPTS_REPO, repo_type='dataset', allow_patterns=patterns, cache_dir=cache_dir)
    return Path(snapshot) / 'evaluation'


def free_port():
    """An unused local TCP port."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def database_roots(args):
    """Environment of the execution API for the benchmark's official databases."""
    if args.benchmark == 'bird_dev':
        root = Path(args.bird_dev_root) / 'dev_databases'
        return {'BIRD_DEV_DB_ROOT': str(root), 'BIRD_TRAIN_DB_ROOT': str(root)}, root
    folder = 'database' if args.benchmark == 'spider_dev' else 'test_database'
    root = Path(args.spider_root) / folder
    return {'SPIDER_DB_ROOT': str(root)}, root


def start_api(db_env, port, log_path):
    """Start the execution API; returns the process once it answers."""
    import requests
    env = dict(os.environ, **db_env)
    log = open(log_path, 'w')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'api:app', '--app-dir', str(REPO / 'db_execution'),
                                '--host', '127.0.0.1', '--port', str(port), '--workers', '8'],
                               env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            if requests.get('http://127.0.0.1:%d/healthz/live' % port, timeout=2).ok:
                return process
        except requests.RequestException:
            time.sleep(1)
    process.terminate()
    raise RuntimeError('execution API did not start, see %s' % log_path)


def run(command, log_path, env):
    """Run one pipeline stage, appending its output to ``log_path``."""
    with open(log_path, 'a') as log:
        log.write('\n### %s\n' % ' '.join(command))
        log.flush()
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=REPO)


def generate_and_select(args, prompts_dir, out, env):
    """Stages 3 and 4: candidates, execution and majority voting."""
    data = prompts_dir / BENCHMARKS[args.benchmark]['prompts']
    run([sys.executable, '-u', str(REPO / 'inference/generate_and_execute.py'), '--model-path', args.model_path,
         '--data-path', str(data), '--output-dir', str(out), '--limit', str(args.limit),
         '--batch-size', str(args.batch_size), '--gpu-memory-utilization', str(args.gpu_memory_utilization)]
        + DECODING[args.decoding], out / 'generation.log', env)
    run([sys.executable, '-u', str(REPO / 'inference/majority_voting.py'), str(out)], out / 'majority_voting.log', env)


def first_lines(source, target, limit):
    """Copy the first ``limit`` lines (all when 0) of a text file."""
    lines = Path(source).read_text().splitlines()
    Path(target).write_text('\n'.join(lines[:limit] if limit else lines) + '\n')


def score_bird(args, out, env):
    """Official BIRD evaluation of predict_dev.json; returns (correct, n)."""
    root = Path(args.bird_dev_root)
    first_lines(root / 'dev.sql', out / 'gold_dev.sql', args.limit)
    questions = json.loads((root / 'dev.json').read_text())
    (out / 'dev_subset.json').write_text(json.dumps(questions[:args.limit] if args.limit else questions))
    run([sys.executable, str(REPO / 'evaluation/official_bird_evaluation/evaluation_bird_ex.py'),
         '--db_root_path', str(root / 'dev_databases') + '/', '--predicted_sql_json_path',
         str(out / 'predict_dev.json'), '--data_mode', 'dev', '--ground_truth_sql_path', str(out / 'gold_dev.sql'),
         '--num_cpus', str(args.num_cpus), '--mode_predict', 'gpt', '--diff_json_path', str(out / 'dev_subset.json'),
         '--meta_time_out', '3600'],
        out / 'official.log', env)
    verdicts = [int(r['res']) for r in json.loads((out / 'eval_result_dev.json').read_text())]
    return sum(verdicts), len(verdicts)


def score_spider(args, prompts_dir, db_root, out, env, name='spider_exec_persample.json'):
    """Official Spider execution evaluation of pred_dev.sql on ``db_root``; returns (correct, n)."""
    gold_root = prompts_dir / BENCHMARKS[args.benchmark]['root']
    first_lines(gold_root / 'dev_gold.sql', out / 'gold.sql', args.limit)
    run(['bash', str(REPO / 'evaluation/spider_test_suite.sh'), str(out / 'gold.sql'), str(out / 'pred_dev.sql'),
         str(db_root), str(out / name)], out / 'official.log', env)
    result = json.loads((out / name).read_text())
    return result['correct'], result['n']


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', choices=sorted(MODELS), help='released CoRE-DB model size')
    parser.add_argument('--model-path', help='HF id or local path (overrides --model)')
    parser.add_argument('--benchmark', required=True, choices=sorted(BENCHMARKS))
    parser.add_argument('--decoding', default='k30', choices=sorted(DECODING))
    parser.add_argument('--limit', type=int, default=0, help='first N questions only (smoke test); 0 = all')
    parser.add_argument('--bird-dev-root', default=os.environ.get('BIRD_DEV_ROOT', 'data/bird/dev'))
    parser.add_argument('--spider-root', default=os.environ.get('SPIDER_ROOT', 'data/spider'))
    parser.add_argument('--test-suite-db', default=os.environ.get('TEST_SUITE_DB', 'data/test_suite_database'),
                        help='Spider test-suite databases; Spider dev TS is scored when the folder exists')
    parser.add_argument('--out-root', default='outputs')
    parser.add_argument('--cache-dir', default=None, help='HF cache directory')
    parser.add_argument('--batch-size', type=int, default=0, help='prompts per vLLM generate call; 0 = all')
    parser.add_argument('--gpu-memory-utilization', type=float, default=0.85)
    parser.add_argument('--num-cpus', type=int, default=12)
    args = parser.parse_args()
    if not args.model_path:
        if not args.model:
            parser.error('give --model or --model-path')
        args.model_path = MODELS[args.model]
    return args


def main():
    args = parse_args()
    tag = re.sub(r'[^A-Za-z0-9_.-]', '_', args.model or Path(args.model_path).name)
    out = (Path(args.out_root) / tag / ('%s_%s' % (args.benchmark, args.decoding))).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prompts_dir = download_prompts(args.benchmark, args.cache_dir)
    db_env, db_root = database_roots(args)
    if not db_root.is_dir():
        sys.exit('official databases not found at %s (see README.md, "Install")' % db_root)
    port = free_port()
    env = dict(os.environ, SQL_API_URL='http://127.0.0.1:%d/execute' % port, TOKENIZERS_PARALLELISM='false',
               NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
    api = start_api(db_env, port, out / 'api.log')
    ts = None
    try:
        generate_and_select(args, prompts_dir, out, env)
        if args.benchmark == 'bird_dev':
            correct, n = score_bird(args, out, env)
        else:
            correct, n = score_spider(args, prompts_dir, db_root, out, env)
            if args.benchmark == 'spider_dev' and Path(args.test_suite_db).is_dir():
                ts = score_spider(args, prompts_dir, Path(args.test_suite_db), out, env, 'spider_ts_persample.json')
    finally:
        api.terminate()
    result = {'model': args.model_path, 'benchmark': args.benchmark, 'decoding': args.decoding, 'limit': args.limit,
              'correct': correct, 'n': n, 'ex_pct': round(100.0 * correct / max(1, n), 2),
              'protocol': 'k=30 T=1.0 seed 42 + majority voting' if args.decoding == 'k30' else 'greedy (n=1, T=0)'}
    if ts:
        result.update(ts_correct=ts[0], ts_pct=round(100.0 * ts[0] / max(1, ts[1]), 2))
    (out / 'RESULT.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
