"""Unit writing (sql_util/writedb.py:292-369) adapted for "copy compact DB + append rows"."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy compact DB, then append generated rows with executemany."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    added, skipped = {}, {}
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not orig_path:
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
            if n == 0:
                added[t] = skipped[t] = 0
                continue
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            ok = bad = 0
            rows = [[cols[c][i] for c in names] for i in range(n)]
            try:
                con.executemany(sql, rows)
                ok = n
            except (sqlite3.Error, OverflowError):
                con.rollback()
                con.execute('begin')
                for row in rows:
                    try:
                        con.execute(sql, row)
                        ok += 1
                    except (sqlite3.Error, OverflowError):
                        bad += 1
            added[t], skipped[t] = ok, bad
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_added': added, 'rows_skipped': skipped}
