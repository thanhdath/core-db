"""Unit writing (sql_util/writedb.py:292-369): copy the compact db, append generated rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _check_row_ok(con, table, names, row, schema, pk_names):
    """Python-side guard: NOT NULL / PK nullness (real constraints enforced by SQLite insert)."""
    for j, c in enumerate(names):
        if row[j] is None and (schema.tables[table].columns[j].notnull
                               or c in pk_names
                               or (table, c) in schema.fks):
            return False
    return True


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None, stats: dict = None) -> dict:
    """Copy the compact db, append generated rows with executemany; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys = OFF')
        existing = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        for s in schema.ddl:
            try:
                con.execute(s)
            except sqlite3.Error:
                pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            pk_names = set(tm.primary_key)
            batch_ok, batch_bad = [], 0
            if n:
                for i in range(n):
                    row = [cols[c][i] for c in names]
                    if _check_row_ok(con, t, names, row, schema, pk_names):
                        batch_ok.append(tuple(row))
                    else:
                        batch_bad += 1
            ok[t] = 0
            if batch_ok:
                try:
                    con.executemany(sql, batch_ok)
                    ok[t] = len(batch_ok)
                except sqlite3.Error:
                    ok[t] = 0
                    for row in batch_ok:
                        try:
                            con.execute(sql, row)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            batch_bad += 1
            bad[t] = batch_bad
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    if stats is not None:
        stats.setdefault('rows_added', {}).update(ok)
        stats.setdefault('rows_skipped', {}).update(bad)
    return {'rows_ok': ok, 'rows_failed': bad}
