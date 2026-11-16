"""Command line entry point for the specification-driven generator."""
import argparse
import json
import os
import random
import sys
import time

from .schema import load_schema
from .spec import load_specification, build_spec
from .instance import build_random_instance
from .writer import unit_path, write_instance_sqlite
from .literals import seed_literal_pool_from_queries


def _load_pool_sqls(path):
    if not path:
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get('sqls') or data.get('pool_sqls') or []
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, str)]


def _run_generate(args):
    """Harness entry point: generate instances i0..i1-1 with seed_base * 100003 + i."""
    schema = load_schema(args.orig)
    raw = load_specification(args.spec)
    spec = build_spec(raw, schema)

    pool_sqls = _load_pool_sqls(args.pool_sqls)
    pool = seed_literal_pool_from_queries(pool_sqls, schema) if pool_sqls else {}
    spec['literal_pool'] = pool
    pool_values = sum(len(v) for v in pool.values())

    i0 = int(args.i0)
    i1 = int(args.i1)
    seed_base = int(args.seed_base)
    tag = args.tag or 'gen'

    rows_added = {}
    rows_skipped = {}
    n_ok = 0
    n_fail = 0
    errors = []
    t0 = time.time()
    for i in range(i0, i1):
        rng = random.Random(seed_base * 100003 + i)
        try:
            instance = build_random_instance(schema, spec, rng)
            path = unit_path(args.root, args.ds, args.db, i, tag)
            stats = write_instance_sqlite(schema, instance, path, orig=args.orig)
            n_ok += 1
            for t, v in stats['rows_ok'].items():
                rows_added[t] = rows_added.get(t, 0) + v
            for t, v in stats['rows_failed'].items():
                rows_skipped[t] = rows_skipped.get(t, 0) + v
        except Exception as exc:
            n_fail += 1
            if len(errors) < 20:
                errors.append('%s: %s' % (type(exc).__name__, exc))
    wall = time.time() - t0
    summary = {
        'db': args.db,
        'n_ok': n_ok,
        'n_fail': n_fail,
        'wall_s': round(wall, 3),
        'pool_sqls': len(pool_sqls),
        'pool_skipped': 0,
        'pool_values': pool_values,
        'errors': errors,
        'rows_added': rows_added,
        'rows_skipped': rows_skipped,
    }
    print(json.dumps(summary))
    return 0


def _run_legacy(args):
    """Legacy interface: --compact/--out/--instances."""
    schema = load_schema(args.compact)
    raw = load_specification(args.spec)
    spec = build_spec(raw, schema)
    base_seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 31)
    summary = []
    for i in range(args.instances):
        rng = random.Random(base_seed + i)
        instance = build_random_instance(schema, spec, rng)
        path = unit_path(args.out, args.ds, args.db, i, args.tag)
        stats = write_instance_sqlite(schema, instance, path, orig=args.compact)
        summary.append({'instance': i, 'path': path, 'rows_ok': stats['rows_ok'],
                        'rows_failed': stats['rows_failed']})
    print(json.dumps({'seed': base_seed, 'instances': summary}, indent=2))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description='Generate database instances from a compact database.')
    sub = ap.add_subparsers(dest='command')

    g = sub.add_parser('generate', help='harness interface')
    g.add_argument('--db', required=True)
    g.add_argument('--orig', required=True)
    g.add_argument('--ds', required=True)
    g.add_argument('--root', required=True)
    g.add_argument('--pool-sqls', default=None)
    g.add_argument('--i0', type=int, default=0)
    g.add_argument('--i1', type=int, default=1)
    g.add_argument('--seed-base', type=int, default=42)
    g.add_argument('--procs', type=int, default=1)
    g.add_argument('--tag', default='gen')
    g.add_argument('--spec', default=None)

    ap.add_argument('--compact', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--instances', type=int, default=1)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--tag', default='gen')
    ap.add_argument('--spec', default=None)
    ap.add_argument('--db', default=None)
    ap.add_argument('--ds', default=None)

    args = ap.parse_args(argv)
    if args.command == 'generate':
        return _run_generate(args)
    if args.compact and args.out:
        return _run_legacy(args)
    ap.error('either use the "generate" subcommand or pass --compact and --out')


if __name__ == '__main__':
    sys.exit(main())
