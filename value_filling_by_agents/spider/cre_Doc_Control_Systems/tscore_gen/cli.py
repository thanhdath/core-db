"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .instance import build_random_instance
from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int):
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return ('', {}, {})
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng)
        stats = write_instance_sqlite(_G['schema'], inst, p, orig_path=a['orig'])
        return ('', stats['rows_ok'], stats['rows_failed'])
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return (type(e).__name__, {}, {})


def _empty_stats(schema) -> dict:
    return {t: [0, 0] for t in schema.tables}


def main(argv=None) -> None:
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
    stats = _empty_stats(schema)
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    for err, ok, bad in res:
        if err:
            errs[err] = errs.get(err, 0) + 1
        for t, o in ok.items():
            stats.setdefault(t, [0, 0])[0] += o
        for t, b in bad.items():
            stats.setdefault(t, [0, 0])[1] += b
    n_ok = sum(1 for err, _, _ in res if not err)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': {t: v[0] for t, v in stats.items()},
                      'rows_skipped': {t: v[1] for t, v in stats.items()},
                      'rows_added_total': sum(v[0] for v in stats.values()),
                      'rows_skipped_total': sum(v[1] for v in stats.values())}))


if __name__ == '__main__':
    main()
