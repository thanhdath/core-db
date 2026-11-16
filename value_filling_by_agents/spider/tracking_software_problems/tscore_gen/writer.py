"""Unit writing (sql_util/writedb.py:292-369), Round 1 adapted."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _insert_rows(con, table: str, tm, cols: dict) -> tuple:
    """Insert generated rows with executemany; return (ok, failed)."""
    names = [c.name for c in tm.columns]
    if not names or not cols:
        return 0, 0
    n = len(cols.get(names[0], []))
    if n == 0:
        return 0, 0
    rows = []
    for i in range(n):
        rows.append(tuple((cols[c][i] if c in cols and i < len(cols[c]) else None) for c in names))
    sql = 'INSERT INTO %s VALUES (%s)' % (q(table), ','.join('?' * len(names)))
    ok = 0
    bad = 0
    try:
        con.executemany(sql, rows)
        ok = len(rows)
    except sqlite3.Error:
        for r in rows:
            try:
                con.execute(sql, r)
                ok += 1
            except (sqlite3.Error, OverflowError):
                bad += 1
    return ok, bad


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy compact DB, append generated rows atomically; failing rows skipped and counted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
    else:
        con = sqlite3.connect(part)
        con.execute('pragma foreign_keys = OFF')
        for s in schema.ddl:
            try:
                con.execute(s)
            except sqlite3.Error:
                pass
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            o, b = _insert_rows(con, t, tm, cols)
            ok[t] = o
            bad[t] = b
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
