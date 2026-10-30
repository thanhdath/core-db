"""Format + execution reward of the GRPO runs, executed on the CoRE-DB environment only.

A completion with the expected ``<think> ... </think> SQL`` format earns 1. On top of that, its SQL earns 2 when its
result equals the gold's on every CoRE-DB member where the gold is informative, and 1 when it only executes.
A completion without the format earns 0.
"""
import random
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

TIMEOUT_MS = 60000
MAX_ROWS = 10000
API_RECOVERY_SECONDS = 300
MEMBER_TAG = '__member__'
MEMBER_ERROR = '__error__'
CONNECTION_ERRORS = ('connection refused', 'connection reset', 'connection aborted', 'connection timeout',
                     'name or service not known', 'no route to host', 'network is unreachable',
                     'connection pool is closed', 'max retries exceeded')


def extract_sql(text):
    """SQL after the last ``</think>`` tag, or None."""
    index = text.rfind('</think>')
    if index == -1:
        return None
    return text[index + len('</think>'):].strip() or None


def has_format(text):
    """One ``<think>`` block first, a thought longer than 100 characters, then a non-empty SQL."""
    if text.count('<think>') != 1 or text.count('</think>') != 1:
        return False
    start, end = text.find('<think>'), text.find('</think>')
    if start >= end or text[:start].strip():
        return False
    return len(text[start + len('<think>'):end].strip()) > 100 and bool(extract_sql(text))


def is_select_like(sql):
    """True for SELECT / WITH / EXPLAIN statements."""
    return sql.lstrip().lower().startswith(('select', 'with', 'explain'))


def api_alive(api_url):
    """True when the execution API answers its liveness probe."""
    try:
        return requests.get(api_url.replace('/execute', '/healthz/live'), timeout=5).status_code == 200
    except requests.RequestException:
        return False


def wait_for_api(api_url):
    """Wait with backoff until the API answers again; False after API_RECOVERY_SECONDS."""
    start, delay = time.time(), 10.0
    while time.time() - start < API_RECOVERY_SECONDS:
        if api_alive(api_url):
            return True
        time.sleep(delay)
        delay = min(delay * 1.5, 60.0) + random.uniform(0, 5)
    return False


def post_sql(api_url, dataset_name, db_id, sql):
    """One /execute request; returns {ok, rows, error}."""
    payload = {'dataset_name': dataset_name, 'db_id': db_id, 'sql': sql, 'timeout_ms': TIMEOUT_MS,
               'max_rows': MAX_ROWS, 'mode': 'read_only' if is_select_like(sql) else 'sandbox_rollback'}
    response = requests.post(api_url, json=payload, timeout=TIMEOUT_MS / 1000.0 + 2)
    if response.status_code != 200:
        return {'ok': False, 'rows': None, 'error': 'HTTP %d: %s' % (response.status_code, response.text)}
    data = response.json()
    return {'ok': bool(data.get('ok', False)), 'rows': data.get('rows'), 'error': data.get('error')}


def execute(api_url, dataset_name, db_id, sql):
    """Execute one SQL; on a dead API wait for it once and retry."""
    try:
        return post_sql(api_url, dataset_name, db_id, sql)
    except Exception as exc:
        error = str(exc)
        if any(marker in error.lower() for marker in CONNECTION_ERRORS) and wait_for_api(api_url):
            try:
                return post_sql(api_url, dataset_name, db_id, sql)
            except Exception as retry_exc:
                error = str(retry_exc)
        return {'ok': False, 'rows': None, 'error': error}


def gold_can_certify(gold):
    """Only a non-empty cached result list can mark a prediction correct (not an error, timeout or empty gold)."""
    if isinstance(gold, list):
        return bool(gold)
    if isinstance(gold, dict) and not gold.get('timeout') and not gold.get('gold_error'):
        rows = gold.get('rows')
        return isinstance(rows, list) and bool(rows)
    return False


def member_of(row):
    """Member index of a member-tagged row (untagged rows belong to member 0)."""
    member = row.get(MEMBER_TAG, 0) if isinstance(row, dict) else 0
    return int(member) if isinstance(member, (int, float)) else member


def strip_tag(row):
    """Row without its member tag."""
    return {k: v for k, v in row.items() if k != MEMBER_TAG}


def is_null(value):
    """None or NaN."""
    return value is None or (isinstance(value, float) and value != value)


def gold_kind(rows):
    """ok / empty / all_null / error for the gold rows of one member."""
    if not rows:
        return 'empty'
    if any(isinstance(r, dict) and MEMBER_ERROR in r and len(r) == 1 for r in rows):
        return 'error'
    if all(isinstance(r, dict) and all(is_null(v) for v in r.values()) for r in rows):
        return 'all_null'
    return 'ok'


def split_members(rows):
    """{member: [untagged rows]} in row order."""
    members = {}
    for row in rows or []:
        if isinstance(row, dict) and MEMBER_TAG in row:
            members.setdefault(member_of(row), []).append(strip_tag(row))
        else:
            members.setdefault(0, []).append(row)
    return members


def member_row_sets(rows, keep):
    """({member: set of row tuples}, members with an error sentinel) over `keep`; None if no frame can be built."""
    members, selected, errors = [], [], set()
    for row in rows or []:
        member = member_of(row)
        if member not in keep:
            continue
        if isinstance(row, dict) and MEMBER_TAG in row:
            row = strip_tag(row)
            if MEMBER_ERROR in row and len(row) == 1:
                errors.add(member)
                continue
        members.append(member)
        selected.append(row)
    sets = {m: set() for m in keep}
    if selected:
        try:
            frame = pd.DataFrame(selected).fillna('')
        except Exception:
            return None
        for member, values in zip(members, map(tuple, frame.values.tolist())):
            sets[member].add(values)
    return sets, errors


def members_to_compare(gold_rows):
    """Members where the gold is informative; member 0 if there is none (None when member 0 cannot decide)."""
    by_member = split_members(gold_rows)
    informative = {m for m, rows in by_member.items() if gold_kind(rows) == 'ok'}
    if informative:
        return informative
    return None if gold_kind(by_member.get(0, [])) in ('error', 'empty') else {0}


def rows_match(gold_rows, pred_rows):
    """Prediction rows equal the gold's (as sets) on every member that decides."""
    keep = members_to_compare(gold_rows)
    if keep is None:
        return False
    gold_sets, pred_sets = member_row_sets(gold_rows, keep), member_row_sets(pred_rows, keep)
    if gold_sets is None or pred_sets is None or pred_sets[1]:
        return False
    return all(gold_sets[0][m] == pred_sets[0][m] for m in keep)


def execution_score(api_url, gt_cache, dataset_name, db_id, sql, gold_sql):
    """2 = paid, 1 = executes against a certifying gold, 0 = otherwise."""
    pred = execute(api_url, dataset_name, db_id, sql)
    if not pred['ok']:
        return 0.0
    gold = gt_cache.get((dataset_name, db_id, gold_sql))
    if not gold_can_certify(gold):
        return 0.0
    return 2.0 if rows_match(gold, pred['rows']) else 1.0


class FormatExecutionReward:
    """TRL reward function; ``last_paid`` holds the paid flags of the last call (for the dynamic-sampling mask)."""

    __name__ = 'format_execution_reward'

    def __init__(self, api_url, gt_cache, threads=16):
        self.api_url = api_url
        self.gt_cache = gt_cache
        self.threads = threads
        self.last_paid = []

    def __call__(self, prompts, completions, groundtruth_sqls, db_id, dataset_name, **kwargs):
        scores = [0.0] * len(completions)
        with ThreadPoolExecutor(self.threads) as pool:
            futures = {}
            for i, (text, golds, db, dataset) in enumerate(zip(completions, groundtruth_sqls, db_id, dataset_name)):
                sql = extract_sql(text)
                if sql:
                    futures[i] = pool.submit(execution_score, self.api_url, self.gt_cache, dataset, db, sql, golds[0])
            for i, future in futures.items():
                scores[i] = future.result()
        self.last_paid = [score >= 2.0 for score in scores]
        return [score + 1.0 if has_format(text) else 0.0 for text, score in zip(completions, scores)]
