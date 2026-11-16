"""Unit writing (sql_util/writedb.py:292-369) plus append-to-copy support."""
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str) -> dict:
    """Empty DDL clone + row-by-row insert, failing rows skipped (writedb.py:292-319); atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma foreign_keys = OFF')
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
            for i in range(n):
                try:
                    con.execute(sql, [cols[c][i] for c in names])
                    ok[t] += 1
                except (sqlite3.Error, OverflowError):
                    bad[t] += 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}


def append_rows_sqlite(schema, rows: dict, path: str) -> dict:
    """Append generated rows to an existing compact-DB copy using executemany in one transaction."""
    con = sqlite3.connect(path)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = rows.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                batch.append([cols[c][i] for c in names])
            try:
                con.executemany(sql, batch)
                ok[t] = len(batch)
            except sqlite3.Error:
                for row in batch:
                    try:
                        con.execute(sql, row)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
        con.commit()
    finally:
        con.close()
    return {'rows_ok': ok, 'rows_failed': bad}
