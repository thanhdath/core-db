"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, append: bool = False) -> dict:
    """Append generated rows to the (copied) compact database; failing rows skipped and counted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    con = sqlite3.connect(path)
    ok, bad, errors = {}, {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not append:
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
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                rows.append([cols.get(c, [None] * n)[i] for c in names])
            if rows:
                con.execute('savepoint sp')
                try:
                    con.executemany(sql, rows)
                    con.execute('release sp')
                    ok[t] = len(rows)
                except (sqlite3.Error, OverflowError) as e:
                    con.execute('rollback to sp')
                    con.execute('release sp')
                    errors[t] = '%s: %s' % (t, e)
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
    finally:
        con.close()
    return {'rows_ok': ok, 'rows_failed': bad, 'errors': errors}
