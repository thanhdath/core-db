"""Unit writing (sql_util/writedb.py:292-369), append-only to a copy of the compact database."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def define_fks(schema, con) -> None:
    """Re-affirm FKs by using the original DDL; also ensure schema-shaped tables exist."""
    try:
        con.execute('pragma foreign_keys = OFF')
    except sqlite3.Error:
        pass


def _insert_all(con, schema, instance: dict) -> dict:
    """Insert every table's rows with executemany inside the caller's transaction."""
    ok, bad = {}, {}
    for t, tm in schema.tables.items():
        cols = instance.get(t, {})
        names = [c.name for c in tm.columns]
        n = len(cols.get(names[0], [])) if names else 0
        if n == 0:
            ok[t] = bad[t] = 0
            continue
        rows = []
        for i in range(n):
            try:
                rows.append(tuple(cols[c][i] for c in names))
            except IndexError:
                bad[t] = bad.get(t, 0) + 1
        sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
        ok[t] = 0
        bad.setdefault(t, 0)
        try:
            con.executemany(sql, rows)
            ok[t] = len(rows)
        except sqlite3.IntegrityError:
            ok[t] = 0
            for r in rows:
                try:
                    con.execute(sql, r)
                    ok[t] += 1
                except (sqlite3.Error, OverflowError):
                    bad[t] += 1
        except (sqlite3.Error, OverflowError):
            ok[t] = 0
            for r in rows:
                try:
                    con.execute(sql, r)
                    ok[t] += 1
                except (sqlite3.Error, OverflowError):
                    bad[t] += 1
    for t, v in (instance.get('__rows_failed__') or {}).items():
        bad[t] = bad.get(t, 0) + v
    return {'rows_ok': ok, 'rows_failed': bad}


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy compact DB, append rows batch-wise inside one transaction; counts ok/skip."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path is not None and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
        try:
            con.execute('pragma foreign_keys = OFF')
            con.execute('pragma journal_mode = MEMORY')
            con.execute('pragma synchronous = OFF')
            con.execute('pragma temp_store = MEMORY')
            con.execute('begin')
            stats = _insert_all(con, schema, instance)
            con.commit()
        finally:
            con.close()
        try:
            os.chmod(part, 0o644)
        except OSError:
            pass
        os.replace(part, path)
        return stats

    con = sqlite3.connect(part)
    try:
        con.execute('pragma foreign_keys = OFF')
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        for s in schema.ddl:
            try:
                con.execute(s)
            except sqlite3.Error:
                pass
        con.execute('begin')
        stats = _insert_all(con, schema, instance)
        con.commit()
    finally:
        con.close()
    try:
        os.chmod(part, 0o644)
    except OSError:
        pass
    os.replace(part, path)
    return stats
