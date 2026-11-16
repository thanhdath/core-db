"""Unit writing (sql_util/writedb.py:292-369) adapted: copy compact DB, append rows with executemany."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig: str) -> dict:
    """Copy compact DB to the unit path, then append generated rows in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.execute('begin immediate')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else (
                len(next(iter(cols.values()))) if cols else 0)
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            rows = [tuple(cols[c][i] if c in cols else None for c in names) for i in range(n)]
            con.execute('savepoint t')
            try:
                con.executemany(sql, rows)
                ok[t] = len(rows)
                con.execute('release t')
            except (sqlite3.Error, OverflowError):
                con.execute('rollback to t')
                con.execute('release t')
                for r in rows:
                    con.execute('savepoint r')
                    try:
                        con.execute(sql, r)
                        ok[t] += 1
                        con.execute('release r')
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
                        con.execute('rollback to r')
                        con.execute('release r')
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
