"""Unit writing: instance = copy of the compact database + appended generated rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _has_notnull(con: sqlite3.Connection, table: str) -> set:
    """Names of NOT NULL columns of `table` (for spill repair of planted NULLs)."""
    try:
        info = con.execute('pragma table_info(%s)' % q(table)).fetchall()
    except sqlite3.Error:
        return set()
    return {r[1] for r in info if r[3]}


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows with executemany in one transaction."""
    if orig_path is None:
        orig_path = getattr(schema, 'orig_path', None)
    if not orig_path:
        raise ValueError('write_instance_sqlite needs the compact database path')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig_path, part)
    ok, bad = {}, {}
    try:
        con = sqlite3.connect(part)
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        order = [t for lvl in schema.table_order for t in lvl]
        for t in order:
            if t not in schema.tables:
                continue
            cols = instance.get(t, {})
            tm = schema.tables[t]
            names = [c.name for c in tm.columns]
            if not names or not cols:
                ok[t] = bad[t] = 0
                continue
            n = len(cols.get(names[0], []))
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            notnull = _has_notnull(con, t)
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                row = [cols[c][i] if c in cols else None for c in names]
                for j, c in enumerate(names):
                    if row[j] is None and c in notnull:
                        ca = next((cm for cm in tm.columns if cm.name == c), None)
                        row[j] = _fallback(ca)
                batch.append(row)
            try:
                con.executemany(sql, batch)
                ok[t] = len(batch)
            except sqlite3.Error:
                for row in batch:
                    try:
                        con.execute(sql, row)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
        con.commit()
        con.close()
    finally:
        if os.path.exists(part):
            os.chmod(part, 0o644)
            os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}


def _fallback(col):
    """Last-resort non-NULL value for a NOT NULL column whose sample came out NULL."""
    if col is None:
        return 0
    t = (col.type_str or '').lower()
    if 'int' in t:
        return 0
    if any(k in t for k in ('real', 'float', 'double', 'numeric', 'decimal')):
        return 0.0
    if 'date' in t or 'timestamp' in t:
        return '2008-01-01 00:00:00'
    return ''
