"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _fk_ok(schema, table: str, row_names: list, row: list) -> bool:
    """True if every non-NULL FK value of this row exists in the compact parent column."""
    for cm in schema.tables[table].columns:
        col = (table, cm.name)
        if col not in schema.fks:
            continue
        pt, pc = schema.fks[col]
        try:
            idx = row_names.index(cm.name)
        except ValueError:
            continue
        v = row[idx]
        if v is None:
            continue
        pvals = schema.original_values.get((pt, pc), [])
        if pvals and v not in set(pvals):
            s = str(v).strip()
            if not (s.isdigit() and int(s) > 0):
                return False
    return True


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path is not None:
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if orig_path is None:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n_compact = len(schema.original_values.get((t, names[0]), [])) if names else 0
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n_compact, n):
                r = [cols[c][i] for c in names]
                if not _fk_ok(schema, t, names, r):
                    bad[t] += 1
                    continue
                rows.append(r)
            if not rows:
                continue
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
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
