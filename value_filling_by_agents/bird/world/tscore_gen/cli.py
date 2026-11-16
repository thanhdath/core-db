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
from .spec_gen import build_spec_instance
from .writer import write_copy_with_appends, unit_path, check_foreign_keys

_G: dict = {}


def _init(orig: str, pool: dict, spec: dict, args: dict) -> None:
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['spec'] = spec
    _G['args'] = args


def _one(i: int) -> dict:
    """Build and write unit i; returns stats dict; on failure returns {'ok': False, 'err': name}."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return {'ok': True, 'skip_existing': True, 'added': {}, 'skipped': {}, 'fk_violations': 0}
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        rows = build_spec_instance(_G['schema'], _G['spec'], _G['pool'], rng)
        stats = write_copy_with_appends(_G['schema'], a['orig'], rows, p)
        fk_bad = check_foreign_keys(p)
        return {'ok': True, 'added': stats['ok'], 'skipped': stats['bad'],
                'fk_violations': fk_bad}
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return {'ok': False, 'err': type(e).__name__, 'added': {}, 'skipped': {},
                'fk_violations': 0}


def _load_spec(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
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
    spec = _load_spec(os.path.join(os.path.dirname(__file__), 'specification.json'))
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base,
            'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, spec=spec, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, spec, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    n_ok = n_fail = 0
    added: dict = {}
    skipped_tbl: dict = {}
    fk_viol = 0
    for r in res:
        if r.get('ok'):
            n_ok += 1
        else:
            n_fail += 1
            if r.get('err'):
                errs[r['err']] = errs.get(r['err'], 0) + 1
        for t, c in (r.get('added') or {}).items():
            added[t] = added.get(t, 0) + int(c)
        for t, c in (r.get('skipped') or {}).items():
            skipped_tbl[t] = skipped_tbl.get(t, 0) + int(c)
        fk_viol += int(r.get('fk_violations') or 0)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': n_fail,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good),
                      'pool_skipped': skipped, 'pool_values': sum(len(v) for v in pool.values()),
                      'errors': errs, 'rows_added': added, 'rows_skipped': skipped_tbl,
                      'fk_violations': fk_viol}))


if __name__ == '__main__':
    main()
