"""Unit writing (sql_util/writedb.py:292-369) adapted for the compact-DB copy."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, rows: dict, path: str, orig_path: str) -> tuple:
    """Copy the compact DB, append generated rows via executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig_path, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.execute('begin')
        for t, tm in schema.tables.items():
            names = [c.name for c in tm.columns]
            cols = rows.get(t, {})
            if not cols or not names:
                ok[t] = bad[t] = 0
                continue
            n = len(cols.get(names[0], []))
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                batch.append(tuple(cols[c][i] if c in cols else None for c in names))
            ok[t], skipped_here = _insert_batch(con, sql, batch)
            bad[t] = skipped_here
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return ok, bad


def _insert_batch(con, sql, batch) -> tuple:
    """Insert a whole batch with executemany; if it fails fallback to row-by-row to count skips."""
    if not batch:
        return 0, 0
    try:
        con.executemany(sql, batch)
        return len(batch), 0
    except sqlite3.Error:
        good = 0
        skipped = 0
        for row in batch:
            try:
                con.execute(sql, row)
                good += 1
            except (sqlite3.Error, OverflowError):
                skipped += 1
        return good, skipped
