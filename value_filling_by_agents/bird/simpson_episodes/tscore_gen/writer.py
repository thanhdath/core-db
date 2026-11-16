"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _fk_ok(con, schema, t: str, row: dict) -> bool:
    """Validate every FK of the row against the current database (parent rows present)."""
    for cm in schema.tables[t].columns:
        key = (t, cm.name)
        if key not in schema.fks:
            continue
        v = row.get(cm.name)
        if v is None:
            continue
        pt, pc = schema.fks[key]
        r = con.execute('select 1 from %s where %s = ? limit 1' % (q(pt), q(pc)), (v,)).fetchone()
        if r is None:
            return False
    return True


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact database, append generated rows with executemany, atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if orig is None:
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
                rows.append([cols[c][i] for c in names])
            if not rows:
                continue
            valid = []
            for r in rows:
                row = dict(zip(names, r))
                if _fk_ok(con, schema, t, row):
                    valid.append(r)
                else:
                    bad[t] += 1
            if not valid:
                continue
            try:
                con.executemany(sql, valid)
                ok[t] += len(valid)
            except (sqlite3.Error, OverflowError):
                for r in valid:
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
