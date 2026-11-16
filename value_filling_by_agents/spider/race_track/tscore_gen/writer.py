"""Unit writing (sql_util/writedb.py:292-369) + append-only copy of the compact DB."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _dry_run_ok(con, sql: str, row: list) -> bool:
    """Validate one row inside a savepoint; always roll back so nothing is inserted."""
    con.execute('savepoint rowcheck')
    try:
        con.execute(sql, row)
        ok = True
    except (sqlite3.Error, OverflowError):
        ok = False
    finally:
        con.execute('rollback to rowcheck')
        con.execute('release rowcheck')
    return ok


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB (if given) + append generated rows with executemany; failing rows skipped."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig:
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not orig:
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
            good_rows = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                if _dry_run_ok(con, sql, row):
                    ok[t] += 1
                    good_rows.append(row)
                else:
                    bad[t] += 1
            if good_rows:
                con.executemany(sql, good_rows)
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
