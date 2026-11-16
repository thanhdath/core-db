"""Unit writing (sql_util/writedb.py:292-369)."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _insert_rows(con, table: str, names: list, cols: dict) -> tuple:
    """Insert generated rows with executemany; returns (ok, failed)."""
    n = len(cols.get(names[0], [])) if names else 0
    if n == 0:
        return 0, 0
    sql = 'INSERT INTO %s VALUES (%s)' % (q(table), ','.join('?' * len(names)))
    rows = [[cols.get(c, [None] * n)[i] for c in names] for i in range(n)]
    ok = 0
    try:
        con.executemany(sql, rows)
        ok = n
    except (sqlite3.Error, OverflowError):
        for r in rows:
            try:
                con.execute(sql, r)
                ok += 1
            except (sqlite3.Error, OverflowError):
                pass
    return ok, n - ok


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact db, append generated rows, atomic replace; returns per-table counts."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not (orig and os.path.exists(orig)):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            ok[t], bad[t] = _insert_rows(con, t, names, cols)
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
