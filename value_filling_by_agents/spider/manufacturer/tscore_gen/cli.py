"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import shutil
import sqlite3
import sys
import time

from .instance import build_random_instance
from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _copy_compact(orig: str, path: str) -> None:
    """Copy the compact database to ``path`` (atomic via .part + replace)."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    dst = sqlite3.connect(part)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(part, 0o644)
    os.replace(part, path)


def _one(i: int) -> str:
    """Build and write unit i; returns '' on success or the exception type name."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    if os.path.exists(p):
        return ''
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = _build(orig=G_ORIG, schema=G_SCHEMA, p=inst_placeholder, seed=G_SEED)
        return ''
    except Exception as e:  # pragma: no cover - reported, never silent
        return type(e).__name__


def _generate_one(orig, schema, p, seed):
    """Generate one database file at ``p`` from the compact database ``orig``."""
    rng = random.Random(seed)
    inst = build_random_instance(schema, _G.get('pool', {}), None, rng)
    _copy_compact(orig, p)
    con = sqlite3.connect(p)
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('PRAGMA foreign_keys=OFF')
        stats = _insert_rows(con, schema, inst)
    finally:
        con.close()
    return stats


def _worker(payload):
    orig, schema, path, seed = payload
    try:
        st = _generate_one(orig, schema, path, seed)
        return ('', st)
    except Exception as e:  # pragma: no cover
        print('unit %s failed: %r' % (path, e), file=sys.stderr)
        return (type(e).__name__, None)


def _insert_rows(con, schema, inst):
    """Insert generated rows with executemany inside one transaction; count ok/skipped per table."""
    from .schema import q
    ok, bad = {}, {}
    con.execute('begin')
    for t, tm in schema.tables.items():
        cols = inst.get(t, {})
        names = [c.name for c in tm.columns]
        n = len(cols.get(names[0], [])) if names else 0
        ok[t] = bad[t] = 0
        if n == 0:
            continue
        sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
        rows = [[cols[c][i] for c in names] for i in range(n)]
        try:
            con.executemany(sql, rows)
            ok[t] = n
        except (sqlite3.Error, OverflowError):
            for r in rows:
                try:
                    con.execute(sql, r)
                    ok[t] += 1
                except (sqlite3.Error, OverflowError):
                    bad[t] += 1
    con.commit()
    return {'rows_ok': ok, 'rows_failed': bad}


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
    idx = list(range(a.i0, a.i1))
    payloads = []
    for i in idx:
        p = unit_path(a.root, a.ds, a.db, i, a.tag)
        if os.path.exists(p):
            continue
        payloads.append((a.orig, schema, p, a.seed_base * 100003 + i))
    if a.procs <= 1 or len(payloads) < 50:
        res = [_worker(pl) for pl in payloads]
    else:
        with mp.Pool(a.procs) as P:
            res = P.map(_worker, payloads, chunksize=max(1, len(payloads) // (a.procs * 4)))
    errs: dict = {}
    rows_added, rows_skipped = {}, {}
    for r, st in res:
        if r:
            errs[r] = errs.get(r, 0) + 1
        if st:
            for t, v in st['rows_ok'].items():
                rows_added[t] = rows_added.get(t, 0) + v
            for t, v in st['rows_failed'].items():
                rows_skipped[t] = rows_skipped.get(t, 0) + v
    n_ok = sum(1 for r, _ in res if not r)
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped}))


if __name__ == '__main__':
    main()
