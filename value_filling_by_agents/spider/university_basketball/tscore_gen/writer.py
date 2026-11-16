"""Unit writing (sql_util/writedb.py:292-369) with append-only semantics for patch 64."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def append_instance_sqlite(schema, instance: dict, orig_path: str, path: str) -> dict:
    """Copy compact DB -> <path>.part, open with the required pragmas, insert generated rows in one txn."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig_path, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('PRAGMA journal_mode=MEMORY')
        con.execute('PRAGMA synchronous=OFF')
        con.execute('PRAGMA temp_store=MEMORY')
        con.execute('PRAGMA foreign_keys = ON')
        order = [t for lvl in schema.table_order for t in lvl]
        ok = {t: 0 for t in schema.tables}
        bad = {t: 0 for t in schema.tables}
        con.execute('begin')
        for t in order:
            tm = schema.tables[t]
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            if not names or not cols or not cols.get(names[0]):
                continue
            n = len(cols[names[0]])
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                row = tuple(cols[c][i] for c in names)
                batch.append(row)
            if not batch:
                continue
            try:
                con.executemany(sql, batch)
                ok[t] += len(batch)
            except (sqlite3.IntegrityError, OverflowError):
                for row in batch:
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
    return {'rows_added': ok, 'rows_skipped': bad}
