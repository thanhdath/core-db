"""Cache the gold execution results of every training prompt on the CoRE-DB environment.

The trainer reads this pickle instead of executing the gold SQL at every step.  Golds are executed
through the CoRE-DB bundle proxy (``db_execution/bundle_proxy.py``), so each cached value is the
member-tagged row list ``[{"__member__": i, **row}, ...]`` over the compact database and every selected
instance.  Failures are stored as ``{"timeout": True, ...}`` or ``{"gold_error": True, ...}``.

Usage:
    python training/build_gt_cache.py --data DATA_DIR --api http://127.0.0.1:8021/execute --out gt_cache.pkl
"""
import argparse
import collections
import hashlib
import json
import pickle
from concurrent.futures import ThreadPoolExecutor

import requests
from datasets import load_from_disk

TIMEOUT_MS = 120000
MAX_ROWS = 10000


def unique_gold_keys(data):
    """[(dataset_name, db_id, gold_sql)] in first-appearance order."""
    keys, seen = [], set()
    for example in data:
        key = (example['dataset_name'], example['db_id'], example['groundtruth_sqls'][0])
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def cache_value(response):
    """Cached value for one proxy response (row list, or a timeout / gold-error marker)."""
    bundle = response.get('bundle') or {}
    error = str(response.get('error') or '')
    if response.get('timed_out') is True or any(t in error.lower() for t in ('timed out', 'timeout', 'interrupt')):
        return {'timeout': True, 'error': error}
    if any(bundle.get('member_truncated') or []):
        return {'gold_error': True, 'censored': True, 'error': 'member result truncated at max_rows'}
    rows = response.get('rows')
    if response.get('ok') is True and not error and isinstance(rows, list) and all(
            isinstance(r, dict) and r for r in rows):
        return rows
    return {'gold_error': True, 'error': error or 'unsuccessful or malformed'}


def execute_gold(api, key):
    """Execute one gold through the proxy; returns (key, cached value)."""
    dataset, db_id, sql = key
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(api, json={'dataset_name': dataset, 'db_id': db_id, 'sql': sql, 'mode': 'read_only',
                                           'timeout_ms': TIMEOUT_MS, 'max_rows': MAX_ROWS},
                                timeout=TIMEOUT_MS / 1000 + 30)
        if response.status_code != 200:
            return key, {'gold_error': True, 'error': 'HTTP %s: %s' % (response.status_code, response.text[:500])}
        return key, cache_value(response.json())
    except (requests.RequestException, ValueError) as exc:
        return key, {'gold_error': True, 'error': str(exc)}


def outcome(value):
    """ok / empty / timeout / error label of a cached value."""
    if isinstance(value, list):
        return 'ok' if value else 'empty'
    return 'timeout' if value.get('timeout') else 'error'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', required=True, help='training prompts (datasets.save_to_disk folder)')
    parser.add_argument('--api', default='http://127.0.0.1:8021/execute', help='bundle proxy /execute URL')
    parser.add_argument('--out', required=True, help='output pickle')
    parser.add_argument('--threads', type=int, default=48)
    args = parser.parse_args()
    keys = unique_gold_keys(load_from_disk(args.data))
    cache, counts = {}, collections.Counter()
    with ThreadPoolExecutor(args.threads) as pool:
        for i, (key, value) in enumerate(pool.map(lambda k: execute_gold(args.api, k), keys)):
            cache[key] = value
            counts[outcome(value)] += 1
            if i % 1000 == 0:
                print(i, dict(counts), flush=True)
    with open(args.out, 'wb') as handle:
        pickle.dump(cache, handle)
    with open(args.out, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    print(json.dumps({'entries': len(cache), 'counts': dict(counts), 'sha256': digest}))


if __name__ == '__main__':
    main()
