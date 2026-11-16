"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _inserted_keys(con, table: str, pk_cols: list) -> set:
    """Keys of ``table`` present in the written database (compact + generated)."""
    if not pk_cols:
        return set()
    sel = 'select %s from %s' % (', '.join(q(c) for c in pk_cols), q(table))
    return {tuple(r) for r in con.execute(sel).fetchall()}


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows with executemany; atomic, mode 0644."""
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
        con.execute('pragma foreign_keys = ON')
        if not (orig_path and os.path.exists(orig_path)):
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
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                rows.append([cols[c][i] for c in names])
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
            if tm.primary_key:
                keys = _inserted_keys(con, t, tm.primary_key)
                for ct, ctm in schema.tables.items():
                    if ct == t:
                        continue
                    for cm in ctm.columns:
                        if schema.fks.get((ct, cm.name)) == (t, tm.primary_key[0]) and cm.name in instance.get(ct, {}):
                            vals = instance[ct][cm.name]
                            if not keys:
                                continue
                            key_list = sorted(keys)
                            instance[ct][cm.name] = [
                                v if v is None or (v,) in keys else key_list[0][0]
                                for v in vals]
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
