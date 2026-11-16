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
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int) -> dict:
    """Build and write unit i; returns summary dict (never raises)."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return {'i': i, 'ok': True, 'err': None, 'rows_ok': {}, 'rows_failed': {}, 'compact_before': {},
                'compact_after': {}, 'report': {}}
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng)
        report = inst.pop('__construction__', {})
        wr = write_instance_sqlite(_G['schema'], inst, p)
        return {'i': i, 'ok': True, 'err': None,
                'rows_ok': wr.get('rows_ok', {}), 'rows_failed': wr.get('rows_failed', {}),
                'compact_before': wr.get('compact_before', {}), 'compact_after': wr.get('compact_after', {}),
                'report': report}
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return {'i': i, 'ok': False, 'err': type(e).__name__, 'rows_ok': {}, 'rows_failed': {},
                'compact_before': {}, 'compact_after': {}, 'report': {}}


def main(argv=None) -> None:
    """Entry point; last stdout line is the required JSON summary."""
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
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base}
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
    compact_changed: int = 0
    for r in res:
        if not r['ok']:
            errs[r['err'] or 'unknown'] = errs.get(r['err'] or 'unknown', 0) + 1
        for t, n in (r.get('rows_ok') or {}).items():
            rows_added[t] = rows_added.get(t, 0) + int(n)
        for t, n in (r.get('rows_failed') or {}).items():
            rows_skipped[t] = rows_skipped.get(t, 0) + int(n)
        for t, before in (r.get('compact_before') or {}).items():
            after = (r.get('compact_after') or {}).get(t, before)
            if after < before:
                compact_changed += 1
    n_ok = sum(1 for r in res if r['ok'])
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped,
                      'compact_instances_with_row_loss': compact_changed}))


if __name__ == '__main__':
    main()
