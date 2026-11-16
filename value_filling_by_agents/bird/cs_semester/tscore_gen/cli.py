"""Command-line driver: generate instances by appending consistent rows to copies of a compact DB."""
import argparse
import json
import os
import random
import shutil
import sys
import time

from .schema import read_schema
from .pool import build_literal_pool
from .sampler import generate_instance_rows
from .writer import unit_path, append_rows_sqlite


def _db_stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _load_pool_sqls(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data if isinstance(x, str)]
    if isinstance(data, dict):
        out = []
        for v in data.values():
            if isinstance(v, list):
                out.extend(str(x) for x in v if isinstance(x, str))
            elif isinstance(v, str):
                out.append(v)
        return out
    return []


def _run_one(schema, pool, orig, root, ds, db, i, seed, tag):
    rng = random.Random(seed)
    rows = generate_instance_rows(schema, pool, rng)
    path = unit_path(root, ds, db, i, tag=tag)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig, part)
    res = append_rows_sqlite(schema, rows, part)
    os.replace(part, path)
    return res


def _generate(args):
    t0 = time.time()
    schema = read_schema(args.orig)
    pool_sqls = _load_pool_sqls(args.pool_sqls)
    pool = build_literal_pool(pool_sqls, schema)
    db = args.db or _db_stem(args.orig)
    i0 = args.i0 if args.i0 is not None else 0
    i1 = args.i1 if args.i1 is not None else i0 + 1
    seed_base = args.seed_base if args.seed_base is not None else 42
    tag = args.tag or 'gen'

    n_ok = n_fail = 0
    rows_added = {}
    rows_skipped = {}
    errors = []
    for i in range(i0, i1):
        seed = seed_base * 100003 + i
        try:
            res = _run_one(schema, pool, args.orig, args.root, args.ds, db, i, seed, tag)
            n_ok += 1
            for t, c in res.get('rows_ok', {}).items():
                rows_added[t] = rows_added.get(t, 0) + c
            for t, c in res.get('rows_failed', {}).items():
                rows_skipped[t] = rows_skipped.get(t, 0) + c
        except Exception as e:  # noqa: BLE001 - report, do not crash the whole batch
            n_fail += 1
            errors.append('%s: %s' % (i, e))

    summary = {
        'db': db,
        'n_ok': n_ok,
        'n_fail': n_fail,
        'wall_s': round(time.time() - t0, 3),
        'pool_sqls': len(pool_sqls),
        'pool_skipped': 0,
        'pool_values': sum(len(v) for v in pool.values()),
        'errors': errors[:20],
        'rows_added': rows_added,
        'rows_skipped': rows_skipped,
    }
    print(json.dumps(summary))
    return 0 if n_fail == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog='tscore_gen.cli')
    sub = ap.add_subparsers(dest='cmd')

    g = sub.add_parser('generate', help='generate instances by appending rows to compact-DB copies')
    g.add_argument('--db', default=None, help='database id (defaults to compact file stem)')
    g.add_argument('--orig', required=True, help='compact sqlite database path (read-only)')
    g.add_argument('--ds', required=True, help='dataset name (output subdir)')
    g.add_argument('--root', required=True, help='output root directory')
    g.add_argument('--pool-sqls', default=None, help='JSON list of construction SQL for literal pools')
    g.add_argument('--i0', type=int, default=0, help='first instance index (inclusive)')
    g.add_argument('--i1', type=int, default=None, help='last instance index (exclusive)')
    g.add_argument('--seed-base', type=int, default=42, help='base random seed')
    g.add_argument('--procs', type=int, default=1, help='worker count (accepted; generation is sequential)')
    g.add_argument('--tag', default='gen', help='instance tag used in filenames')

    ap.add_argument('--orig', dest='orig_flat', default=None)
    ap.add_argument('--ds', dest='ds_flat', default=None)
    ap.add_argument('--root', dest='root_flat', default=None)
    ap.add_argument('--n', type=int, default=None)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--tag', dest='tag_flat', default=None)
    ap.add_argument('--queries', default=None)
    ap.add_argument('--scale', type=float, default=1.0)

    args = ap.parse_args(argv)

    if args.cmd == 'generate':
        return _generate(args)

    if args.orig_flat and args.ds_flat and args.root_flat:
        ns = argparse.Namespace(
            db=_db_stem(args.orig_flat), orig=args.orig_flat, ds=args.ds_flat, root=args.root_flat,
            pool_sqls=args.queries, i0=0, i1=(args.n if args.n is not None else 1),
            seed_base=(args.seed if args.seed is not None else 42), procs=1,
            tag=(args.tag_flat or 'gen'))
        return _generate(ns)

    ap.print_help(sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
