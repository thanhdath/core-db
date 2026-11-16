"""Unit writing: copy compact DB, append generated rows with executemany in one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, orig_path: str, path: str) -> dict:
    """Copy compact db to path.part, append generated rows with executemany, atomic rename."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    try:
        shutil.copyfile(orig_path, part)
    except Exception:
        shutil.copy(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        order = [t for lvl in schema.table_order for t in lvl]
        for t in order:
            if t not in schema.tables:
                continue
            tm = schema.tables[t]
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            batch = [[cols[c][i] for c in names] for i in range(n)]
            try:
                con.executemany(sql, batch)
                ok[t] = len(batch)
            except (sqlite3.Error, OverflowError):
                for row in batch:
                    try:
                        con.executemany(sql, [row])
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
