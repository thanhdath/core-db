"""Unit writing (sql_util/writedb.py:292-369) with the program-interface batching rules."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _count_rows(con, tables) -> dict:
    out = {}
    for t in tables:
        try:
            out[t] = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
        except sqlite3.Error:
            out[t] = 0
    return out


def write_instance_sqlite(schema, instance: dict, path: str) -> dict:
    """Copy the compact database, append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    src = getattr(schema, 'source_path', None)
    if src and os.path.exists(src):
        shutil.copyfile(src, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    tables = list(schema.tables.keys())
    compact_before = _count_rows(con, tables)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not (src and os.path.exists(src)):
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
            ok[t] = 0
            bad[t] = 0
            rows = [[cols[c][i] for c in names] for i in range(n)]
            if rows:
                try:
                    con.executemany(sql, rows)
                    ok[t] = len(rows)
                except (sqlite3.Error, OverflowError):
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
        compact_after = _count_rows(con, tables)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad,
            'compact_before': compact_before, 'compact_after': compact_after}
