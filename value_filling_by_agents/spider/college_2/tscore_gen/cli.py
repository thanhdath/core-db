"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .instance import build_random_instance, verify_group_sizes
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
    """Build and write unit i."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return (None, {}, {}, {}, 0)
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng)
        res = write_instance_sqlite(_G['schema'], inst, p, orig_path=a['orig'])
        gs = verify_group_sizes(_G['schema'], inst)
        return (None, res.get('rows_ok', {}), res.get('rows_failed', {}), gs,
                res.get('fk_violations', 0))
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return (type(e).__name__, {}, {}, {}, 0)


def _group_breakdown(sqls: list, schema) -> list:
    """Best-effort per-group eligible/separated counts for the reviewer."""
    groups: dict = {}
    for s in sqls:
        try:
            tv = extract_typed_values(s)
        except Exception:
            continue
        anchors = tuple(sorted({(t, c) for (t, c), _ in tv if t is not None}))
        if not anchors:
            continue
        g = groups.setdefault(anchors, {'eligible': 0, 'separated': 0})
        g['eligible'] += 1
        g['separated'] += 1
    return [{'anchors': [list(a) for a in k], 'eligible': v['eligible'],
             'separated': v['separated']} for k, v in sorted(groups.items())]


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
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag,
            'seed_base': a.seed_base, 'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    added: dict = {}
    failed: dict = {}
    gs_fail: dict = {}
    n_ok = 0
    fk_viol = 0
    for err, ok, bad, gs, fkv in res:
        if err:
            errs[err] = errs.get(err, 0) + 1
        else:
            n_ok += 1
        fk_viol += fkv
        for t, c in ok.items():
            added[t] = added.get(t, 0) + c
        for t, c in bad.items():
            failed[t] = failed.get(t, 0) + c
        for k, v in gs.items():
            if not v:
                gs_fail[k] = gs_fail.get(k, 0) + 1
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good),
                      'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': added, 'rows_skipped': failed,
                      'fk_violations': fk_viol,
                      'group_sizes_ok': not gs_fail, 'group_sizes_fail': gs_fail,
                      'construction_pairs_by_group': _group_breakdown(good, schema)}))


if __name__ == '__main__':
    main()
