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
from .spec import load_specification
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict, spec: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args
    _G['spec'] = spec


def _one(i: int) -> str:
    """Build and write unit i; returns '' on success or the exception type name."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return ''
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], None, rng, _G['spec'])
        write_instance_sqlite(_G['schema'], inst, p, _G['args']['orig'])
        return ''
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return type(e).__name__


def _find_spec(orig: str) -> str:
    """Locate specification.json next to the compact database or in the package dir."""
    cand = os.path.join(os.path.dirname(os.path.abspath(orig)), 'specification.json')
    if os.path.exists(cand):
        return cand
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specification.json')
    if os.path.exists(here):
        return here
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
    spec = load_specification(_find_spec(a.orig))
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base, 'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args, spec=spec)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args, spec)) as pool_:
            res = pool_.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    for r in res:
        if r:
            errs[r] = errs.get(r, 0) + 1
    rows_added, rows_skipped = _summarize_rows(schema, args, idx)
    print(json.dumps({'db': a.db, 'n_ok': res.count(''), 'n_fail': len(res) - res.count(''),
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped}))


def _summarize_rows(schema, args, idx) -> tuple:
    """Sum appended rows per table over instances by re-reading each written sqlite file."""
    import sqlite3
    added: dict = {}
    skipped: dict = {}
    for i in idx:
        p = unit_path(args['root'], args['ds'], args['db'], i, args['tag'])
        if not os.path.exists(p):
            continue
        try:
            con = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
            for t in schema.tables:
                try:
                    n = con.execute('select count(*) from "%s"' % t.replace('"', '""')).fetchone()[0]
                except sqlite3.Error:
                    n = 0
                base = schema.original_sizes.get(t, 0)
                added[t] = added.get(t, 0) + max(0, n - base)
            con.close()
        except sqlite3.Error:
            continue
    return added, skipped


if __name__ == '__main__':
    main()
