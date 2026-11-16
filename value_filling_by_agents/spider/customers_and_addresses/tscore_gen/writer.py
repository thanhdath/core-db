"""Unit writing (sql_util/writedb.py:292-369): compact DB copy + appended rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root, ds, db, i, tag='gen'):
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def write_instance_sqlite(schema, instance, path, compact_path=None):
    """Start from a copy of the compact DB and append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if compact_path:
        shutil.copyfile(compact_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma foreign_keys = OFF')
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        if not compact_path:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        order = [t for lvl in schema.table_order for t in lvl]
        for t in order:
            tm = schema.tables[t]
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            good_rows = []
            existing_pk = set()
            if tm.primary_key:
                try:
                    sel = 'select %s from %s' % (','.join(q(c) for c in tm.primary_key), q(t))
                    existing_pk = {tuple(r) for r in con.execute(sel).fetchall()}
                except sqlite3.Error:
                    existing_pk = set()
            seen_pk = set()
            for i in range(n):
                key = tuple(cols[c][i] for c in tm.primary_key) if tm.primary_key else None
                if key is not None:
                    if key in existing_pk or key in seen_pk:
                        bad[t] += 1
                        continue
                    seen_pk.add(key)
                good_rows.append([cols[c][i] for c in names])
            try:
                con.executemany(sql, good_rows)
                ok[t] += len(good_rows)
            except (sqlite3.Error, OverflowError):
                for row in good_rows:
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
