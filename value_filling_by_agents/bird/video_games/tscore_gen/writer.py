"""Unit writing: copy compact database, append generated rows inside one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, compact_exists: bool = True,
                          orig_path: str = None) -> dict:
    """Copy compact database then append rows; failing rows skipped and counted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    src = orig_path if (orig_path and os.path.exists(orig_path)) else None
    if src is None and os.path.exists(path):
        src = path
    if src is None:
        raise FileNotFoundError('no compact database to copy for %s' % path)
    shutil.copyfile(src, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            if not n:
                continue
            rows = [[cols[c][i] for c in names] for i in range(n)]
            for row in rows:
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
    return {'rows_ok': ok, 'rows_failed': bad}
