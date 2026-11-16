"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .instance import build_random_instance, compact_state
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
        return ''
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        schema = _G['schema']
        state = compact_state(schema)
        inst = build_random_instance(schema, _G['pool'], None, rng, state)
        write_instance_sqlite(schema, inst, p, compact_exists=True, orig_path=a['orig'])
        return ''
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return type(e).__name__


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
    if not os.path.exists(a.orig):
        raise SystemExit('compact database not found: %s' % a.orig)
    with open(a.pool_sqls) as f:
        raw = json.load(f)
    sqls = [s for s in raw if isinstance(s, str)]
    good, skipped = [], 0
    for s in sqls:
        try:
            extract_typed_values(s)
            good.append(s)
        except Exception:
            skipped += 1
    schema = read_schema(a.orig)
    empty = [t for t, rows in schema.compact_rows.items() if not rows]
    if empty:
        raise SystemExit('compact database has empty tables: %s' % ', '.join(sorted(empty)))
    pool = seed_literal_pool_from_queries(good, schema, spec_pool=_spec_pool())
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base,
            'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    for r in res:
        if r:
            errs[r] = errs.get(r, 0) + 1
    print(json.dumps({'db': a.db, 'n_ok': res.count(''), 'n_fail': len(res) - res.count(''),
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': {}, 'rows_skipped': {}}))


def _spec_pool() -> dict:
    """Column-keyed literal seeds from the generation specification."""
    return {
        ('game', 'ID'): ['74', '75', '76', '10030', '10031', '10032'],
        ('game_publisher', 'ID'): ['6656', '6657', '6658', '10030', '10031', '10032'],
        ('game_platform', 'ID'): ['25', '26', '27', '9657', '9658', '9659'],
        ('publisher', 'ID'): ['463', '464', '465'],
        ('game', 'GENRE_ID'): ['1', '2', '3'],
        ('genre', 'ID'): ['1', '2', '3'],
        ('game_publisher', 'PUBLISHER_ID'): ['463', '464', '465'],
        ('game_platform', 'GAME_PUBLISHER_ID'): ['6656', '6657', '6658'],
        ('game_platform', 'RELEASE_YEAR'): ['1999', '2000', '2001', '2002', '2003', '2006', '2007', '2008'],
        ('game', 'GAME_NAME'): ['ModNation Racers', 'modnation racers', 'Panzer Tactics', 'panzer tactics',
                                 'FIFA 07', 'fifa 08', 'Marvel Ultimate Alliance'],
        ('publisher', 'PUBLISHER_NAME'): ['Culture Brain', 'culture brain', 'Atari', 'atari', 'Athena', 'athena',
                                           '10TACLE Studios', '10tacle studios', 'Brash Entertainment',
                                           'Electronic Arts'],
        ('genre', 'GENRE_NAME'): ['Sports', 'sports', 'Strategy', 'strategy', 'Adventure', 'adventure',
                                   'Simulation', 'simulation', 'Shooter', 'Role-Playing', 'Puzzle'],
        ('platform', 'PLATFORM_NAME'): ['PS3', 'ps3', 'X360', 'x360', 'PS4', 'ps4', 'PSP', 'psp', 'Wii', 'DS'],
        ('region', 'REGION_NAME'): ['Europe', 'europe', 'North America', 'north america', 'Japan', 'japan',
                                     'Other'],
        ('region_sales', 'NUM_SALES'): ['2.99', '3', '3.01', '3.49', '3.5', '3.51', '0.51', '1.43'],
        ('region_sales', 'REGION_ID'): ['1', '2', '3', '4', '5'],
        ('region_sales', 'GAME_PLATFORM_ID'): ['25', '26', '27', '9657', '9658', '9659'],
    }


if __name__ == '__main__':
    main()
