"""Unit writing (sql_util/writedb.py:292-369)."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _compact_rows(schema, con, table):
    """Read the compact rows of a table (read-only)."""
    tm = schema.tables[table]
    names = [c.name for c in tm.columns]
    sel = 'select %s from %s' % (', '.join(q(c) for c in names), q(table))
    return con.execute(sel).fetchall()


def _insert_rows(con, table, names, rows, ok, bad):
    """Insert rows with executemany; fall back to row-by-row to count failures."""
    sql = 'INSERT INTO %s VALUES (%s)' % (q(table), ','.join('?' * len(names)))
    if not rows:
        return
    try:
        con.executemany(sql, rows)
        ok[table] = len(rows)
    except (sqlite3.Error, OverflowError):
        for r in rows:
            try:
                con.execute(sql, r)
                ok[table] += 1
            except (sqlite3.Error, OverflowError):
                bad[table] += 1


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic write, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    ok, bad = {}, {}
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
        try:
            con.execute('pragma journal_mode=MEMORY')
            con.execute('pragma synchronous=OFF')
            con.execute('pragma temp_store=MEMORY')
            con.execute('pragma foreign_keys = OFF')
            con.execute('begin')
            for t, tm in schema.tables.items():
                names = [c.name for c in tm.columns]
                compact = _compact_rows(schema, con, t)
                n_compact = len(compact)
                cols = instance.get(t, {})
                n_total = len(cols.get(names[0], [])) if names else 0
                n_gen = max(0, n_total - n_compact)
                ok[t] = bad[t] = 0
                rows = [[cols[c][i] for c in names] for i in range(n_compact, n_compact + n_gen)]
                _insert_rows(con, t, names, rows, ok, bad)
            con.commit()
        finally:
            con.close()
    else:
        con = sqlite3.connect(part)
        try:
            con.execute('pragma journal_mode=MEMORY')
            con.execute('pragma synchronous=OFF')
            con.execute('pragma temp_store=MEMORY')
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
                ok[t] = bad[t] = 0
                rows = [[cols[c][i] for c in names] for i in range(n)]
                _insert_rows(con, t, names, rows, ok, bad)
            con.commit()
        finally:
            con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except Exception:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
