"""Unit writing: copy the compact DB and append generated rows (writedb.py adapted)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, orig_path: str, instance: dict, path: str) -> dict:
    """Atomic copy of the compact DB + appended generated rows, executemany in one transaction."""
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
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            if not names:
                ok[t] = bad[t] = 0
                continue
            n = min([len(cols[c]) for c in names if c in cols] or [0])
            rows = []
            for i in range(n):
                row = []
                for c in names:
                    v = cols.get(c)
                    row.append(None if v is None or i >= len(v) else v[i])
                rows.append(row)
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            good = 0
            for r in rows:
                try:
                    con.execute(sql, r)
                    good += 1
                except (sqlite3.Error, OverflowError):
                    pass
            ok[t], bad[t] = good, len(rows) - good
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
