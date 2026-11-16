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
from .spec import load_spec, build_column_specs, mild_ranges
from .writer import unit_path, append_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict, spec: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args
    _G['spec'] = spec
    _G['cols'] = build_column_specs(_G['schema'], spec)
    _G['mild'] = mild_ranges(_G['schema'])


def _one(i: int):
    """Build and write unit i; returns (error_name_or_'', counts_dict_or_None)."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return '', None
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng,
                                     spec=_G['spec'], col_specs=_G['cols'], mild=_G['mild'])
        counts = append_instance_sqlite(_G['schema'], inst, a['orig'], p)
        return '', counts
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return type(e).__name__, None


def _spec_path(orig: str) -> str:
    """specification.json written by the pipeline next to the package or beside the database."""
    cands = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'tscore_gen', 'specification.json'),
             os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          'tscore_gen', 'specification.json'),
             os.path.join(os.path.dirname(os.path.abspath(orig)), 'specification.json')]
    for c in cands:
        if os.path.exists(c):
            return c
    return ''


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
    sp = _spec_path(a.orig)
    spec = load_spec(sp) if sp else {}
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base,
            'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _init(a.orig, pool, args, spec)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args, spec)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    tot = {'rows_added': {t: 0 for t in schema.tables},
           'rows_skipped': {t: 0 for t in schema.tables}}
    n_ok = 0
    for err, counts in res:
        if err:
            errs[err] = errs.get(err, 0) + 1
        else:
            n_ok += 1
        if counts:
            for t, n in counts.get('rows_added', {}).items():
                tot['rows_added'][t] = tot['rows_added'].get(t, 0) + n
            for t, n in counts.get('rows_skipped', {}).items():
                tot['rows_skipped'][t] = tot['rows_skipped'].get(t, 0) + n
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': tot['rows_added'], 'rows_skipped': tot['rows_skipped']}))


if __name__ == '__main__':
    main()
