"""Copy the compact database and append generated rows with executemany in one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    else:
        con0 = sqlite3.connect(part)
        try:
            for s in schema.ddl:
                try:
                    con0.execute(s)
                except sqlite3.Error:
                    pass
            con0.commit()
        finally:
            con0.close()
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            ok[t] = bad[t] = 0
            if not cols:
                continue
            names = [c.name for c in tm.columns]
            lens = [len(cols.get(nm, [])) if nm in cols else 0 for nm in names]
            n = min(lens) if lens else 0
            if n <= 0:
                continue
            sql = 'INSERT OR IGNORE INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(nm) for nm in names), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                batch.append([cols.get(nm, [None] * n)[i] for nm in names])
            try:
                con.executemany(sql, batch)
                ok[t] = n
            except (sqlite3.Error, OverflowError):
                for row in batch:
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
