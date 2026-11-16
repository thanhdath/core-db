"""Unit writing (sql_util/writedb.py:292-369) + patch 64: copy compact DB + append rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig_path: str, path: str) -> None:
    """Copy the compact DB to a new file."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    shutil.copyfile(orig_path, path)


def write_instance_sqlite(schema, instance: dict, path: str, rng=None, orig_path: str = None) -> dict:
    """Copy compact DB + append generated rows (patch 64)."""
    if orig_path and os.path.exists(orig_path):
        _copy_compact(orig_path, path)
    else:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        con = sqlite3.connect(path)
        try:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
            con.commit()
        finally:
            con.close()
    con = sqlite3.connect(path)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode=memory')
        con.execute('pragma synchronous=off')
        con.execute('pragma temp_store=memory')
        con.execute('pragma foreign_keys=on')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = 0
            bad[t] = 0
            rows = []
            for i in range(n):
                rows.append([cols[c][i] for c in names])
            if rows:
                try:
                    con.executemany(sql, rows)
                    ok[t] = len(rows)
                except (sqlite3.Error, OverflowError):
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
    finally:
        con.close()
    return {'rows_ok': ok, 'rows_failed': bad}
