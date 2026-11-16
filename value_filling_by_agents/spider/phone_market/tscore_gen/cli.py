"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from . import specification as spec
from .instance import build_random_instance
from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int):
    """Build and write unit i; returns (error_name_or_'' , added, skipped, diagnostics)."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return ('', {}, {}, {})
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng)
        res = write_instance_sqlite(_G['schema'], inst, p, a['orig'],
                                    expected_sizes=spec.TABLE_SIZES)
        diag = _diagnostics(inst, _G['schema'])
        diag['row_count_mismatch'] = res.get('row_count_mismatch', {})
        return ('', res.get('rows_ok', {}), res.get('rows_failed', {}), diag)
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return (type(e).__name__, {}, {}, {})


def _diagnostics(inst: dict, schema) -> dict:
    """Cheap per-instance pattern-separation flags (implemented in Python, no SQL)."""
    d = {'patterns': {}, 'nulls': {}}
    for t, cols in inst.items():
        for c, vals in cols.items():
            nn = [v for v in vals if v is not None]
            d['nulls'].setdefault('%s.%s' % (t, c), [0, len(vals)])
            d['nulls']['%s.%s' % (t, c)][0] = len(vals) - len(nn)
    for (t, c), targets in spec.BOUNDARIES.items():
        if t in inst and c in inst[t]:
            vs = set(v for v in inst[t][c] if v is not None)
            d['patterns'].setdefault('comparison_boundary', [])
            d['patterns']['comparison_boundary'].append(
                {'column': '%s.%s' % (t, c), 'present': sorted(vs & set(targets)), 'targets': targets})
    for t, c in spec.GROUP_SIZE_COLUMNS:
        if t in inst and c in inst[t]:
            from collections import Counter
            sizes = sorted(Counter(inst[t][c]).values())
            d['patterns'].setdefault('group_sizes', [])
            d['patterns']['group_sizes'].append({'column': '%s.%s' % (t, c), 'sizes': sizes})
    for t, c in spec.DUPLICATE_SHARE:
        if t in inst and c in inst[t]:
            nn = [v for v in inst[t][c] if v is not None]
            share = 1.0 - (len(set(nn)) / len(nn)) if nn else 0.0
            d['patterns'].setdefault('duplicates_for_distinct', [])
            d['patterns']['duplicates_for_distinct'].append(
                {'column': '%s.%s' % (t, c), 'duplicate_share': round(share, 3)})
    for t, c in spec.TIE_COLUMNS:
        if t in inst and c in inst[t]:
            from collections import Counter
            nn = [v for v in inst[t][c] if v is not None]
            has_tie = any(n >= 2 for n in Counter(nn).values())
            d['patterns'].setdefault('ties_for_order_limit', [])
            d['patterns']['ties_for_order_limit'].append({'column': '%s.%s' % (t, c), 'tie': has_tie})
    at, ac = spec.AGGREGATE_BOUNDARY['column']
    if at in inst and ac in inst[at]:
        total = sum(v for v in inst[at][ac] if v is not None)
        d['patterns']['aggregate_boundary'] = {'column': '%s.%s' % (at, ac), 'sum': total,
                                               'targets': spec.AGGREGATE_BOUNDARY['values']}
    for t in inst:
        for cm in schema.tables[t].columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_keys = set(v for v in (inst.get(pt, {}).get(pc) or []) if v is not None)
            child_keys = set(v for v in (inst[t][cm.name] if cm.name in inst[t] else []) if v is not None)
            child_keys = set(str(v) for v in child_keys) if 'phone' == pt and 'Phone_ID' == pc else child_keys
            unmatched = set(str(v) for v in parent_keys) - child_keys if 'phone' == pt else parent_keys - child_keys
            d['patterns'].setdefault('unmatched_join_rows', [])
            d['patterns']['unmatched_join_rows'].append(
                {'child': '%s.%s' % (t, cm.name), 'parent_rows_without_children': len(unmatched)})
    return d


def main(argv=None) -> None:
    """Entry point."""
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('generate')
    for k in ('--db', '--orig', '--ds', '--root', '--pool-sqls'):
        g.add_argument(k, required=True)
    g.add_argument('--i0', type=int, default=0)
    g.add_argument('--i1', type=int, default=800)
    g.add_argument('--seed-base', type=int, default=42)
    g.add_argument('--procs', type=int, default=6)
    g.add_argument('--tag', default='gen')
    a = ap.parse_args(argv)
    t0 = time.time()
    with open(a.pool_sqls) as f:
        sqls = [s for s in json.load(f) if isinstance(s, str)]
    good, skipped = [], 0
    for s in sqls:
        try:
            extract_typed_values(s)
            good.append(s)
        except Exception:
            skipped += 1
    schema = read_schema(a.orig)
    pool = seed_literal_pool_from_queries(good, schema)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base,
            'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    rows_added: dict = {}
    rows_skipped: dict = {}
    construction_pairs_by_group: dict = {}
    nulls_by_col: dict = {}
    for err, ok, bad, diag in res:
        if err:
            errs[err] = errs.get(err, 0) + 1
        for t, n in ok.items():
            rows_added[t] = rows_added.get(t, 0) + int(n)
        for t, n in bad.items():
            rows_skipped[t] = rows_skipped.get(t, 0) + int(n)
        for gname, items in (diag.get('patterns') or {}).items():
            lst = construction_pairs_by_group.setdefault(gname, [])
            if len(lst) < 50:
                lst.append(items)
        for col, (n_null, n_tot) in (diag.get('nulls') or {}).items():
            cur = nulls_by_col.setdefault(col, [0, 0])
            cur[0] += n_null
            cur[1] += n_tot
    n_ok = sum(1 for err, _, _, _ in res if not err)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped,
                      'construction_pairs_by_group': construction_pairs_by_group,
                      'nulls_by_col': nulls_by_col}))


if __name__ == '__main__':
    main()
