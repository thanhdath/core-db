"""Unit writing (sql_util/writedb.py:292-369) adapted to copy the compact database."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, part: str) -> None:
    """Copy the compact database file to the part path."""
    shutil.copyfile(orig, part)


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = '') -> dict:
    """Copy compact DB, append generated rows with executemany in one transaction; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        _copy_compact(orig, part)
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
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = []
            for i in range(n):
                rows.append(tuple(cols[c][i] for c in names))
            try:
                con.executemany(sql, rows)
                ok[t] = len(rows)
            except (sqlite3.Error, OverflowError):
                for row in rows:
                    try:
                        con.execute(sql, row)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
