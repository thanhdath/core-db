"""Unit writing (sql_util/writedb.py:292-369), copy-of-compact variant."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _table_columns(schema, t):
    return [c.name for c in schema.tables[t].columns]


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy of the compact database + appended rows; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    src = orig or getattr(schema, 'path', None)
    if src and os.path.exists(src):
        shutil.copyfile(src, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not src or not os.path.exists(src):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t in schema.tables:
            names = _table_columns(schema, t)
            cols = instance.get(t, {})
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            if not names:
                ok[t] = bad[t] = 0
                continue
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (q(t), ','.join(q(c) for c in names),
                                                       ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            batch = []
            for i in range(n):
                batch.append([cols.get(c, [None] * n)[i] if c in cols else None for c in names])
            if batch:
                try:
                    con.executemany(sql, batch)
                    ok[t] = len(batch)
                except (sqlite3.Error, OverflowError):
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
    try:
        with open(path + '.stats', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
