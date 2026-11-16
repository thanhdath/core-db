"""Unit writing (sql_util/writedb.py:292-369) + append model over the compact database."""
import os
import sqlite3

from .schema import copy_compact_db, q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy compact DB + append rows via executemany in one transaction (append model)."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path is None:
        raise ValueError('write_instance_sqlite needs the compact database path to copy')
    copy_compact_db(orig_path, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT OR IGNORE INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            rows = [[cols[c][i] for c in names] for i in range(n)]
            done_before = con.total_changes
            try:
                con.executemany(sql, rows)
                ok[t] += con.total_changes - done_before
            except sqlite3.Error:
                for r in rows:
                    try:
                        con.execute(sql, r)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
            inserted = con.total_changes - done_before
            if inserted < n:
                bad[t] += n - inserted
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
