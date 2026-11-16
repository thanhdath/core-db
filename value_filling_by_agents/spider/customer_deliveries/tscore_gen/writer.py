"""Unit writing (sql_util/writedb.py:292-369)."""
import json
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, part: str) -> None:
    """Copy the compact database (read-only source) to the part file."""
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    dst = sqlite3.connect(part)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB (if given) + append generated rows; failing rows skipped and counted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        _copy_compact(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    fk_violations = 0
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        if not (orig and os.path.exists(orig)):
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
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            batch = []
            for i in range(n):
                batch.append([cols[c][i] for c in names])
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
        try:
            fk_violations = len(con.execute('pragma foreign_key_check').fetchall())
        except sqlite3.Error:
            fk_violations = -1
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_violations}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_violations}
