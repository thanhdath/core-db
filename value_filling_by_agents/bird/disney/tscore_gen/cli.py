"""Command-line entry point for the tscore_gen generator."""
import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time

from . import schema as schema_mod
from . import samplers as samplers_mod
from . import literals as literals_mod


def _q(name):
    return '"%s"' % name.replace('"', '""')


def _instance_dir(root, ds, db, tag, idx):
    return os.path.join(root, ds, "%s__%s_%04d" % (db, tag, idx))


def _instance_path(root, ds, db, tag, idx):
    d = _instance_dir(root, ds, db, tag, idx)
    return os.path.join(d, "%s__%s_%04d.sqlite" % (db, tag, idx))


def _copy_compact(compact_path, dest_path):
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    part = dest_path + ".part"
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(compact_path, part)
    os.chmod(part, 0o644)
    os.replace(part, dest_path)


def _existing_rows(compact_path, table):
    con = sqlite3.connect(compact_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute("SELECT * FROM %s" % _q(table))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def _existing_keys(compact_path, table, key_cols):
    con = sqlite3.connect(compact_path)
    try:
        cur = con.execute(
            "SELECT %s FROM %s" % (",".join(_q(c) for c in key_cols), _q(table))
        )
        return set(tuple(r) for r in cur.fetchall())
    finally:
        con.close()


def _append_rows(dest_path, rows_by_table, schema):
    """Append generated rows in one transaction; skip rows failing a constraint."""
    con = sqlite3.connect(dest_path)
    ok, bad = {}, {}
    try:
        con.execute("pragma journal_mode = MEMORY")
        con.execute("pragma synchronous = OFF")
        con.execute("pragma temp_store = MEMORY")
        con.execute("pragma foreign_keys = OFF")
        con.execute("begin")
        for table in schema.table_order_flat():
            rows = rows_by_table.get(table) or []
            ok[table] = bad[table] = 0
            if not rows:
                continue
            tm = schema.tables[table]
            cols = [c.name for c in tm.columns]
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (
                _q(table),
                ",".join(_q(c) for c in cols),
                ",".join("?" * len(cols)),
            )
            params = [[r.get(c) for c in cols] for r in rows]
            try:
                con.executemany(sql, params)
                ok[table] = len(params)
            except (sqlite3.Error, OverflowError):
                ok[table] = bad[table] = 0
                for p in params:
                    try:
                        con.execute(sql, p)
                        ok[table] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[table] += 1
        con.commit()
    finally:
        con.close()
    return ok, bad


def generate_one(compact_path, dest_path, seed, schema, pool_values):
    rng = random.Random(seed)

    compact = {}
    for t in schema.tables:
        compact[t] = _existing_rows(compact_path, t)

    used = {}
    for t, tm in schema.tables.items():
        used[t] = _existing_keys(compact_path, t, tm.primary_key)

    generated = samplers_mod.generate_all(schema, compact, used, rng, pool_values)

    _copy_compact(compact_path, dest_path)
    ok, bad = _append_rows(dest_path, generated, schema)
    return ok, bad


def _load_pool_sqls(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (ValueError, OSError):
        pass
    return []


def _build_pool_values(sqls, schema):
    """Route pool-SQL literals to columns (never executed)."""
    try:
        return literals_mod.seed_literal_pool_from_queries(sqls, schema)
    except Exception:
        return {}


def _run_generate(args):
    t0 = time.time()
    schema = schema_mod.SCHEMA
    compact = args.orig
    if not os.path.exists(compact):
        sys.stderr.write("compact database not found: %s\n" % compact)
        return 2

    sqls = _load_pool_sqls(args.pool_sqls)
    pool_values = _build_pool_values(sqls, schema)

    n_ok = n_fail = 0
    rows_added = {t: 0 for t in schema.tables}
    rows_skipped = {t: 0 for t in schema.tables}
    errors = []
    for i in range(args.i0, args.i1):
        seed = args.seed_base * 100003 + i
        dest = _instance_path(args.root, args.ds, args.db, args.tag, i)
        try:
            ok, bad = generate_one(compact, dest, seed, schema, pool_values)
        except Exception as e:  # pragma: no cover - defensive
            n_fail += 1
            errors.append("%d: %s" % (i, e))
            continue
        n_ok += 1
        for t in schema.tables:
            rows_added[t] += ok.get(t, 0)
            rows_skipped[t] += bad.get(t, 0)

    out = {
        "db": args.db,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "wall_s": round(time.time() - t0, 3),
        "pool_sqls": len(sqls),
        "pool_skipped": 0,
        "pool_values": sum(len(v) for v in pool_values.values()),
        "errors": errors,
        "rows_added": rows_added,
        "rows_skipped": rows_skipped,
    }
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")

    g = sub.add_parser("generate")
    g.add_argument("--db", required=True)
    g.add_argument("--orig", required=True)
    g.add_argument("--ds", required=True)
    g.add_argument("--root", required=True)
    g.add_argument("--pool-sqls", default=None)
    g.add_argument("--i0", type=int, default=0)
    g.add_argument("--i1", type=int, default=1)
    g.add_argument("--seed-base", type=int, default=42)
    g.add_argument("--procs", type=int, default=1)
    g.add_argument("--tag", default="gen")

    args = ap.parse_args(argv)
    if args.cmd == "generate":
        return _run_generate(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
