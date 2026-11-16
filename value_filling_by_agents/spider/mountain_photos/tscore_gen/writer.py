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


def _insert_rows(con, schema, instance: dict) -> dict:
    """Insert generated rows with executemany; a failing row is skipped and counted."""
    ok, bad = {}, {}
    for t, tm in schema.tables.items():
        cols = instance.get(t, {})
        names = [c.name for c in tm.columns]
        n = len(cols.get(names[0], [])) if names else 0
        ok[t] = bad[t] = 0
        if n == 0:
            continue
        sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
        rows = [[cols[c][i] for c in names] for i in range(n)]
        try:
            con.executemany(sql, rows)
            ok[t] = n
        except (sqlite3.Error, OverflowError):
            for r in rows:
                try:
                    con.execute(sql, r)
                    ok[t] += 1
                except (sqlite3.Error, OverflowError):
                    bad[t] += 1
    return {'rows_ok': ok, 'rows_failed': bad}


def _compact_counts(con, schema) -> dict:
    out = {}
    for t in schema.tables:
        try:
            out[t] = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
        except sqlite3.Error:
            out[t] = -1
    return out


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic replace, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
        try:
            con.execute('pragma journal_mode = MEMORY')
            con.execute('pragma synchronous = OFF')
            con.execute('pragma temp_store = MEMORY')
            con.execute('pragma foreign_keys = OFF')
            before = _compact_counts(con, schema)
            con.execute('begin')
            counts = _insert_rows(con, schema, instance)
            con.commit()
            after = _compact_counts(con, schema)
            counts['compact_preserved'] = all(after.get(t, -1) >= before.get(t, 0) for t in schema.tables)
        finally:
            con.close()
    else:
        con = sqlite3.connect(part)
        counts = {'rows_ok': {}, 'rows_failed': {}}
        try:
            con.execute('pragma journal_mode = MEMORY')
            con.execute('pragma synchronous = OFF')
            con.execute('pragma temp_store = MEMORY')
            con.execute('pragma foreign_keys = OFF')
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
            con.execute('begin')
            counts = _insert_rows(con, schema, instance)
            con.commit()
        finally:
            con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump(counts, f)
    except OSError:
        pass
    return counts
