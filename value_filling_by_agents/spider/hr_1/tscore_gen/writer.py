"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _violations(con: sqlite3.Connection, schema) -> set:
    """Set of (kind, table, detail) integrity violations in a connection."""
    out: set = set()
    try:
        con.execute('pragma foreign_keys = ON')
        for row in con.execute('pragma foreign_key_check').fetchall():
            out.add(('fk', str(row[0]), str(row[2])))
    except sqlite3.Error:
        pass
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.notnull:
                try:
                    n = con.execute('select count(*) from %s where %s is null' % (q(t), q(cm.name))).fetchone()[0]
                except sqlite3.Error:
                    n = 0
                if n:
                    out.add(('notnull', t, cm.name))
        if tm.primary_key:
            cols = ', '.join(q(c) for c in tm.primary_key)
            try:
                n = con.execute('select count(*) from (select %s from %s group by %s having count(*) > 1)'
                                % (cols, q(t), cols)).fetchone()[0]
            except sqlite3.Error:
                n = 0
            if n:
                out.add(('pk', t, ','.join(tm.primary_key)))
    return out


def _integrity_ok(con: sqlite3.Connection, schema, orig_path: str) -> bool:
    """Fail only on NEW violations introduced by generated rows."""
    new = _violations(con, schema)
    if not new:
        return True
    if not (orig_path and os.path.exists(orig_path)):
        return False
    try:
        ocon = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig_path, uri=True)
        try:
            old = _violations(ocon, schema)
        finally:
            ocon.close()
    except sqlite3.Error:
        return False
    return new <= old


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
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
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                rows.append(tuple(cols[c][i] for c in names))
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
        if not _integrity_ok(con, schema, orig_path):
            raise RuntimeError('post-write integrity check failed (new violations)')
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
