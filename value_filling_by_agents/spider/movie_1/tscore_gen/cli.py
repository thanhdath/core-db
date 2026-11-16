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
from .spec import load_specification, spec_from_columns
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, spec: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['spec'] = spec
    _G['args'] = args


def _one(i: int):
    """Build and write unit i."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return '', {}, {}
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng, spec=_G['spec'])
        rep = write_instance_sqlite(_G['schema'], inst, p)
        return '', rep.get('rows_ok', {}), rep.get('rows_failed', {})
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return type(e).__name__, {}, {}


def _load_spec(a) -> dict:
    """Specification: tscore_gen/specification.json next to the package, else derived from --spec-json."""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, 'specification.json')
    if os.path.exists(cand):
        try:
            return load_specification(cand)
        except Exception:
            pass
    if getattr(a, 'spec_json', None) and os.path.exists(a.spec_json):
        try:
            return load_specification(a.spec_json)
        except Exception:
            pass
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
    g.add_argument('--spec-json', default=None)
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
    spec = _load_spec(a)
    if not spec:
        spec = spec_from_columns(schema)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, spec=spec, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, spec, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    added: dict = {}
    skipped_rows: dict = {}
    for status, ok, bad in res:
        if status:
            errs[status] = errs.get(status, 0) + 1
        for t, n in (ok or {}).items():
            added[t] = added.get(t, 0) + int(n)
        for t, n in (bad or {}).items():
            skipped_rows[t] = skipped_rows.get(t, 0) + int(n)
    n_ok = sum(1 for status, _, _ in res if not status)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': added, 'rows_skipped': skipped_rows}))


if __name__ == '__main__':
    main()
