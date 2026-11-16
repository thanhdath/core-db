"""Unit writing (sql_util/writedb.py:292-369), adapted: append to a copy of the compact database."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy compact sqlite (if given) then append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        shutil.copy2(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not (orig and os.path.exists(orig)):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            if not names or not cols:
                ok[t] = bad[t] = 0
                continue
            n = len(cols.get(names[0], [])) if names[0] in cols else 0
            if n == 0:
                ok[t] = bad[t] = 0
                continue
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                q(t), ','.join(q(c) for c in names), ','.join('?' * len(names)))
            rows = []
            for i in range(n):
                rows.append(tuple(cols.get(c, [None] * n)[i] for c in names))
            good = []
            for r in rows:
                try:
                    good.append(r)
                except (TypeError, ValueError, OverflowError):
                    continue
            ok[t] = 0
            bad[t] = 0
            try:
                con.executemany(sql, good)
                ok[t] = len(good)
            except sqlite3.IntegrityError:
                ok[t] = 0
                bad[t] = 0
                for r in good:
                    try:
                        con.execute(sql, r)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError):
                        bad[t] += 1
            except (sqlite3.Error, OverflowError):
                ok[t] = 0
                bad[t] = 0
                for r in good:
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
