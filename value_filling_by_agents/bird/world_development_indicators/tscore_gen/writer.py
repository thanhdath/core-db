"""Unit writing (sql_util/writedb.py:292-369), adapted: copy the compact database, append rows."""
import os
import shutil
import sqlite3

from .instance import build_random_instance
from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _insert_rows(con, schema, instance: dict) -> tuple:
    """Insert generated rows with executemany in topological order; returns (ok, bad) per table."""
    ok, bad = {}, {}
    order = [t for lvl in schema.table_order for t in lvl]
    for t in order:
        tm = schema.tables[t]
        cols = instance.get(t, {})
        names = [c.name for c in tm.columns]
        present = [c for c in names if c in cols]
        n = len(cols[present[0]]) if present else 0
        ok[t] = bad[t] = 0
        if n == 0:
            continue
        for c in present:
            v = cols[c]
            if len(v) < n:
                cols[c] = list(v) + [None] * (n - len(v))
            elif len(v) > n:
                cols[c] = list(v)[:n]
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
        rows = [[cols.get(c, [None] * n)[i] for c in names] for i in range(n)]
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
    return ok, bad


def _integrity_ok(con, schema) -> bool:
    """Run PRAGMA foreign_key_check and reject the instance if any violation remains."""
    try:
        bad = con.execute('pragma foreign_key_check').fetchall()
    except sqlite3.Error:
        return False
    return not bad


def write_instance_sqlite(schema, literal_pool: dict, spec: dict, path: str, rng) -> dict:
    """Copy the compact database, append generated rows, atomic replace, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(schema.orig_path, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        instance = build_random_instance(schema, literal_pool, spec, None, rng)
        con.execute('begin')
        ok, bad = _insert_rows(con, schema, instance)
        if _integrity_ok(con, schema):
            con.commit()
        else:
            con.rollback()
            con.execute('begin')
            ok, bad = _insert_rows(con, schema, instance)
            if _integrity_ok(con, schema):
                con.commit()
            else:
                con.rollback()
                for t in schema.tables:
                    bad[t] = bad.get(t, 0) + ok.get(t, 0)
                    ok[t] = 0
                con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
