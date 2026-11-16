"""Unit writing: copy the compact DB and append generated rows with executemany inside one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB and append generated rows with executemany inside one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
        presetup = True
    else:
        con = sqlite3.connect(part)
        presetup = False
    ok, bad = {t: 0 for t in schema.tables}, {t: 0 for t in schema.tables}
    try:
        con.execute('pragma foreign_keys = ON')
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        if not presetup:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            if not names:
                continue
            n = len(cols.get(names[0], [])) if names[0] in cols else 0
            if n == 0:
                continue
            rows = []
            for i in range(n):
                try:
                    rows.append(tuple(cols[c][i] if c in cols and i < len(cols[c]) else None for c in names))
                except IndexError:
                    bad[t] += 1
            if rows:
                sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
                try:
                    con.executemany(sql, rows)
                    ok[t] += len(rows)
                except (sqlite3.IntegrityError, sqlite3.Error, OverflowError):
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
    return {'rows_ok': ok, 'rows_failed': bad}
