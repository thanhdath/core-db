"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time

from .schema import read_schema
from .spec import build_spec
from .generate import generate_rows, insert_generated
from .pool import build_pool


def _instance_path(root, ds, name, tag, i):
    d = '%s__%s_%04d' % (name, tag, i)
    return os.path.join(root, ds, d, d + '.sqlite')


def _copy_compact(orig, dst):
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    part = dst + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig, part)
    os.chmod(part, 0o644)
    os.replace(part, dst)


def _one(i, schema, spec, pool, args):
    """Build instance i: copy compact db, append generated rows."""
    path = _instance_path(args['root'], args['ds'], args['db'], args['tag'], i)
    if os.path.exists(path):
        return 0, 0, {}, {}
    rng = random.Random(args['seed_base'] * 100003 + i)
    _copy_compact(args['orig'], path)
    con = sqlite3.connect(path)
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys=OFF')
        rows = generate_rows(schema, spec, pool, rng)
        added, skipped = insert_generated(con, schema, rows)
        con.commit()
    finally:
        con.close()
    return 1, 0, added, skipped


def main(argv=None):
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
    schema = read_schema(a.orig)
    spec = build_spec(schema)
    pool, pool_skipped = build_pool(sqls, schema)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag,
            'seed_base': a.seed_base, 'orig': a.orig}
    n_ok = n_fail = 0
    rows_added, rows_skipped = {}, {}
    errors = {}
    for i in range(a.i0, a.i1):
        try:
            ok, fail, added, skipped = _one(i, schema, spec, pool, args)
            n_ok += ok
            n_fail += fail
            for t, v in added.items():
                rows_added[t] = rows_added.get(t, 0) + v
            for t, v in skipped.items():
                rows_skipped[t] = rows_skipped.get(t, 0) + v
        except Exception as e:
            n_fail += 1
            errors[type(e).__name__] = errors.get(type(e).__name__, 0) + 1
            print('unit %d failed: %r' % (i, e), file=sys.stderr)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': n_fail,
                      'wall_s': round(time.time() - t0, 2),
                      'pool_sqls': len(sqls), 'pool_skipped': pool_skipped,
                      'pool_values': sum(len(v) for v in pool.values()),
                      'errors': errors, 'rows_added': rows_added,
                      'rows_skipped': rows_skipped}))


if __name__ == '__main__':
    main()
