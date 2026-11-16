"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .specgen import build_spec, generate_rows
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, spec: dict, args: dict) -> None:
    """Worker initializer: read and prepare the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['spec'] = spec
    _G['args'] = args


def _one(i: int) -> dict:
    """Build and write unit i; returns a per-instance report dict."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return {'ok': True, 'added': {}, 'skipped': {}, 'err': None, 'checks': {}}
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        schema = _G['schema']
        rows = generate_rows(schema, _G['pool'], _G['spec'], rng)
        res = write_instance_sqlite(schema, rows, p, orig=a['orig'])
        return {'ok': True, 'added': res.get('rows_ok', {}), 'skipped': res.get('rows_failed', {}),
                'err': None, 'checks': res.get('checks', {})}
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return {'ok': False, 'added': {}, 'skipped': {}, 'err': type(e).__name__, 'checks': {}}


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
    spec = build_spec(schema, pool)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag,
            'seed_base': a.seed_base, 'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, spec=spec, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, spec, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    rows_added: dict = {}
    rows_skipped: dict = {}
    checks_failed: dict = {}
    n_ok = 0
    for r in res:
        if r['ok']:
            n_ok += 1
        else:
            errs[r['err']] = errs.get(r['err'], 0) + 1
        for t, n in (r.get('added') or {}).items():
            rows_added[t] = rows_added.get(t, 0) + int(n)
        for t, n in (r.get('skipped') or {}).items():
            rows_skipped[t] = rows_skipped.get(t, 0) + int(n)
        for k, v in (r.get('checks') or {}).items():
            if not v:
                checks_failed[k] = checks_failed.get(k, 0) + 1
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped,
                      'checks_failed': checks_failed}))


if __name__ == '__main__':
    main()
