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
from .specgen import build_spec_instance, load_spec
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, spec: dict, args: dict) -> None:
    """Worker initializer: read the original and specification ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['spec'] = spec
    _G['args'] = args


def _one(i: int) -> dict:
    """Build and write unit i; returns {'ok', 'err', 'rows_added', 'rows_skipped'}."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return {'ok': True, 'err': '', 'rows_added': {}, 'rows_skipped': {}}
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        if _G['spec']:
            inst, size = build_spec_instance(_G['schema'], _G['pool'], _G['spec'], rng, a['orig'])
        else:
            inst = build_random_instance(_G['schema'], _G['pool'], None, rng)
            size = None
        stats = write_instance_sqlite(_G['schema'], inst, p, base_db=a['orig'])
        return {'ok': True, 'err': '', 'rows_added': stats.get('rows_ok') or {},
                'rows_skipped': stats.get('rows_failed') or {}}
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return {'ok': False, 'err': type(e).__name__, 'rows_added': {}, 'rows_skipped': {}}


def _load_spec(a) -> dict:
    """Specification: --spec path, or tscore_gen/specification.json next to this package, else {}."""
    path = a.spec
    if not path:
        cand = os.path.join(os.path.dirname(__file__), 'specification.json')
        path = cand if os.path.exists(cand) else None
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}


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
    g.add_argument('--spec', default=None)
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
    spec = load_spec(a)
    if spec:
        from .specgen import merge_spec_pools
        merge_spec_pools(pool, spec, schema)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base, 'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _init(a.orig, pool, spec, args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, spec, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    added: dict = {}
    bad: dict = {}
    for r in res:
        if r['err']:
            errs[r['err']] = errs.get(r['err'], 0) + 1
        for t, n in (r.get('rows_added') or {}).items():
            added[t] = added.get(t, 0) + n
        for t, n in (r.get('rows_skipped') or {}).items():
            bad[t] = bad.get(t, 0) + n
    n_ok = sum(1 for r in res if r['ok'])
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': added, 'rows_skipped': bad}))


if __name__ == '__main__':
    main()
