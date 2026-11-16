"""Unit writing: compact DB copy + appended generated rows (round 1)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def copy_compact_db(orig: str, dst: str) -> None:
    """Copy the compact database file to dst (atomic replacement done by caller)."""
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    shutil.copyfile(orig, dst)


def _row_count(con, table: str) -> int:
    try:
        return int(con.execute('select count(*) from %s' % q(table)).fetchone()[0])
    except sqlite3.Error:
        return 0


def write_generated_rows(path: str, schema, instance: dict) -> dict:
    """Append the generated rows with executemany, inside one transaction, skipping failed rows."""
    con = sqlite3.connect(path)
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
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            insert_sql = 'INSERT OR IGNORE INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows_ok = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                rows_ok.append(row)
            before = _row_count(con, t)
            try:
                con.executemany(insert_sql, rows_ok)
            except sqlite3.Error:
                for row in rows_ok:
                    try:
                        con.execute(insert_sql, row)
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
            after = _row_count(con, t)
            ok[t] = max(0, after - before - (bad[t] if 'bad' in dir() else 0))
            ok[t] = max(0, n - bad[t])
        con.commit()
    finally:
        con.close()
    return {'rows_ok': ok, 'rows_failed': bad}
