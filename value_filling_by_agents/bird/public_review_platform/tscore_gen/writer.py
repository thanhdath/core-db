"""Unit writing (sql_util/writedb.py:292-369), adapted to append to a copy of the compact database."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _insert_rows(con, table: str, names: list, cols: dict, n: int) -> tuple:
    """Insert n rows with executemany; rows failing a constraint are skipped and counted."""
    sql = 'INSERT INTO %s VALUES (%s)' % (q(table), ','.join('?' * len(names)))
    rows = [[cols[c][i] for c in names] for i in range(n)]
    ok = 0
    bad = 0
    good_rows = []
    for r in rows:
        good_rows.append(r)
    try:
        con.executemany(sql, good_rows)
        ok = len(good_rows)
    except (sqlite3.Error, OverflowError):
        ok = 0
        bad = 0
        for r in good_rows:
            try:
                con.execute(sql, r)
                ok += 1
            except (sqlite3.Error, OverflowError):
                bad += 1
    return ok, bad


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic replace (mode 0644)."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        if not orig_path or not os.path.exists(orig_path):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t], bad[t] = _insert_rows(con, t, names, cols, n)
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
