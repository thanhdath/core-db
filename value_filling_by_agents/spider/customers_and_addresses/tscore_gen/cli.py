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
from .spec import build_spec
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    schema = read_schema(orig)
    _G['schema'] = schema
    _G['spec'] = build_spec(schema)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int) -> dict:
    """Build and write unit i; returns a per-unit result dict."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    res = {'ok': 0, 'fail': 0, 'err': '', 'rows_added': {}, 'rows_skipped': {}}
    if os.path.exists(p):
        res['ok'] = 1
        return res
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst, sizes = build_random_instance(_G['schema'], _G['pool'], None, rng, _G['spec'])
        wr = write_instance_sqlite(_G['schema'], inst, p, compact_path=a['orig'])
        res['ok'] = 1
        res['rows_added'] = wr['rows_ok']
        res['rows_skipped'] = wr['rows_failed']
        return res
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        res['fail'] = 1
        res['err'] = type(e).__name__
        return res


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
        _G.update(schema=schema, spec=build_spec(schema), pool=pool, args=args)
        results = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            results = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    added: dict = {t: 0 for t in schema.tables}
    skipped_rows: dict = {t: 0 for t in schema.tables}
    for r in results:
        if r.get('err'):
            errs[r['err']] = errs.get(r['err'], 0) + 1
        for t, n in (r.get('rows_added') or {}).items():
            added[t] = added.get(t, 0) + n
        for t, n in (r.get('rows_skipped') or {}).items():
            skipped_rows[t] = skipped_rows.get(t, 0) + n
    n_ok = sum(1 for r in results if r.get('ok'))
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(results) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': added, 'rows_skipped': skipped_rows}))


if __name__ == '__main__':
    main()
