"""Unit writing (sql_util/writedb.py:292-369) adapted to append-only instances."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, part: str) -> None:
    """Copy the compact database (read-only source) to the part file."""
    shutil.copyfile(orig, part)


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy compact DB + append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        _copy_compact(orig, part)
        con = sqlite3.connect(part)
    else:
        con = sqlite3.connect(part)
        for s in schema.ddl:
            try:
                con.execute(s)
            except sqlite3.Error:
                pass
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
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
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
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    stats = {'rows_ok': ok, 'rows_failed': bad}
    try:
        with open(path + '.stats.json', 'w') as f:
            json.dump(stats, f)
    except OSError:
        pass
    return stats
