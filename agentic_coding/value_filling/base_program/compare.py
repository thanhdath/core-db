"""Denotation comparison (unofficial/exec_eval.py:20-119, 171-232)."""
import random
from collections import Counter
from itertools import product

import requests


def _unorder_row(row: tuple) -> tuple:
    return tuple(sorted(row, key=lambda x: str(x) + str(type(x))))


def _quick_rej(r1: list, r2: list, order_matters: bool) -> bool:
    s1, s2 = [_unorder_row(r) for r in r1], [_unorder_row(r) for r in r2]
    return s1 == s2 if order_matters else set(s1) == set(s2)


def _perms(sets1: list, r2: list):
    n = len(r2[0])
    cons = [set(range(n)) for _ in range(n)]
    if n <= 3:
        return product(*cons)
    rng = random.Random(0)
    for _ in range(20):
        row = rng.choice(r2)
        for c1 in range(n):
            for c2 in sorted(cons[c1]):
                if row[c2] not in sets1[c1]:
                    cons[c1].remove(c2)
    return product(*[sorted(c) for c in cons])


def result_eq(rows_a: list, rows_b: list, order_matters: bool) -> bool:
    """Bag equality up to column permutation (exec_eval.py:20-119)."""
    a, b = [tuple(r) for r in rows_a], [tuple(r) for r in rows_b]
    if not a and not b:
        return True
    if len(a) != len(b):
        return False
    n = len(a[0])
    if len(b[0]) != n:
        return False
    if not _quick_rej(a, b, order_matters):
        return False
    sets1 = [{r[i] for r in a} for i in range(n)]
    for perm in _perms(sets1, b):
        if len(set(perm)) != len(perm):
            continue
        bp = b if n == 1 else [tuple(r[i] for i in perm) for r in b]
        if order_matters:
            if a == bp:
                return True
        elif set(a) == set(bp) and Counter(a) == Counter(bp):
            return True
    return False


def execute_batch(api_base: str, ds: str, db_id: str, sqls: list, timeout_ms: int = 30000) -> list:
    """POST <base>/execute_batch of the db_execution API (replaces upstream subprocess execution)."""
    r = requests.post(api_base.rstrip('/') + '/execute_batch',
                      json={'dataset_name': ds, 'db_id': db_id, 'sqls': list(sqls), 'mode': 'read_only',
                            'timeout_ms': timeout_ms, 'max_rows': 10000},
                      timeout=timeout_ms / 1000 * max(1, len(sqls)) + 30)
    r.raise_for_status()
    return r.json()


def execute_and_compare(sql_a: str, sql_b: str, instance_id: str, ds: str, api_base: str, order_matters=None):
    """True same denotation, False differ or sql_b fails, None if sql_a unusable (exec_eval.py:171-232)."""
    if order_matters is None:
        order_matters = 'order by' in sql_a.lower()
    ra, rb = execute_batch(api_base, ds, instance_id, [sql_a, sql_b])
    if not ra.get('ok') or ra.get('timed_out'):
        return None
    if not rb.get('ok') or rb.get('timed_out'):
        return False
    return result_eq(ra.get('rows') or [], rb.get('rows') or [], order_matters)
