"""Unit writing: copy of the compact database + appended generated rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _existing_keys(con, table: str, columns: list) -> set:
    """Key tuples already present in the compact copy (PK or UNIQUE columns)."""
    if not columns:
        return set()
    try:
        rows = con.execute('select %s from %s' % (', '.join(q(c) for c in columns), q(table))).fetchall()
    except sqlite3.Error:
        return set()
    return {tuple(r) for r in rows}


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic replace; returns row counts."""
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
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            pk = list(tm.primary_key)
            uniq = [c.name for c in tm.columns if c.unique and c.name not in pk]
            seen_pk = _existing_keys(con, t, pk) if pk else set()
            seen_u = {c: _existing_keys(con, t, [c]) for c in uniq}
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                if pk:
                    k = tuple(row[names.index(c)] for c in pk)
                    if k in seen_pk:
                        bad[t] += 1
                        continue
                dup = False
                for c in uniq:
                    v = row[names.index(c)]
                    if v is not None and (v,) in seen_u[c]:
                        dup = True
                        break
                if dup:
                    bad[t] += 1
                    continue
                batch.append(row)
                if pk:
                    seen_pk.add(tuple(row[names.index(c)] for c in pk))
                for c in uniq:
                    v = row[names.index(c)]
                    if v is not None:
                        seen_u[c].add((v,))
            if batch:
                try:
                    con.executemany(sql, batch)
                    ok[t] = len(batch)
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
