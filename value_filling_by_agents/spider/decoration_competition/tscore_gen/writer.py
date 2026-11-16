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


def _compact_n(schema, t: str) -> int:
    return int(schema.original_sizes.get(t, 0))


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy compact DB, append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path is None:
        orig_path = getattr(schema, 'orig_path', None)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not (orig_path and os.path.exists(orig_path)):
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
            start = _compact_n(schema, t)
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            batch = []
            for i in range(start, n):
                batch.append([cols[c][i] for c in names])
            if batch:
                try:
                    con.executemany(sql, batch)
                    ok[t] = len(batch)
                except (sqlite3.Error, OverflowError):
                    ok[t] = 0
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
        with open(path + '.stats.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
