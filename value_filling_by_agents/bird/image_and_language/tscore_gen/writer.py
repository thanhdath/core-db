"""Unit writing: copy the compact database, then append rows with executemany in one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def append_rows(schema, orig: str, rows: dict, path: str) -> dict:
    """Copy the compact database to `path`, then append `rows` with executemany inside one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig, part)
    added: dict = {}
    skipped: dict = {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.isolation_level = None
        con.execute('begin')
        for t in _insert_order(schema):
            data = rows.get(t) or []
            tm = schema.tables[t]
            names = [c.name for c in tm.columns]
            if not data:
                added[t] = 0
                skipped[t] = 0
                continue
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ', '.join(q(c) for c in names), ', '.join('?' * len(names)))
            batch_ok = [tuple(r.get(c) for c in names) for r in data]
            batch_bad = 0
            if batch_ok:
                try:
                    con.executemany(sql, batch_ok)
                    added[t] = len(batch_ok)
                except sqlite3.Error:
                    ok = 0
                    for row in batch_ok:
                        try:
                            con.execute(sql, row)
                            ok += 1
                        except (sqlite3.Error, OverflowError):
                            batch_bad += 1
                    added[t] = ok
            else:
                added[t] = 0
            skipped[t] = batch_bad
        con.execute('commit')
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_added': added, 'rows_skipped': skipped}


def _insert_order(schema) -> list:
    """Tables in foreign-key topological order (children after parents)."""
    return [t for lvl in schema.table_order for t in lvl]
