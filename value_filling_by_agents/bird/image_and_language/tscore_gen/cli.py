"""CLI: python -m tscore_gen.cli generate --db <db_id> --orig <compact.sqlite> --ds <bird|spider> --root <out_root>
--pool-sqls <pool_sqls.json> --i0 0 --i1 <N> --seed-base 42 --procs <P> --tag <tag>"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .instance import build_and_write_instance
from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .writer import unit_path

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int):
    """Build and write unit i from a copy of the compact DB; returns ('', stats) or (errname, stats)."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return '', None
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        stats = build_and_write_instance(_G['schema'], _G['pool'], a['orig'], p, rng, a['spec'])
        return '', stats
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return type(e).__name__, None


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
    spec = _load_spec(a.db)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag,
            'seed_base': a.seed_base, 'orig': a.orig, 'spec': spec}
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
    n_ok = 0
    for name, st in res:
        if name:
            errs[name] = errs.get(name, 0) + 1
        else:
            n_ok += 1
        if st:
            for t, v in st.get('rows_added', {}).items():
                rows_added[t] = rows_added.get(t, 0) + v
            for t, v in st.get('rows_skipped', {}).items():
                rows_skipped[t] = rows_skipped.get(t, 0) + v
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good),
                      'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped}))


def _load_spec(db: str) -> dict:
    """Load the specification for this db if present (tscore_gen/specification.json); never required."""
    for cand in (os.path.join(os.path.dirname(__file__), 'specification.json'),
                 os.path.join(os.path.dirname(__file__), '..', 'specification.json')):
        try:
            with open(cand) as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                if db in obj and isinstance(obj[db], dict):
                    return obj[db]
                if 'db' in obj and obj.get('db') == db:
                    return obj
                return obj
        except Exception:
            continue
    return {}


if __name__ == '__main__':
    main()
