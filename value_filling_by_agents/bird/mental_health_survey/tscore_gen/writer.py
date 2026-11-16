"""Unit writing (sql_util/writedb.py:292-369)."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _existing_keys(con, table: str, pk_cols: list) -> set:
    """PK tuples already present in the compact copy (so generated keys stay fresh)."""
    if not pk_cols:
        return set()
    try:
        rows = con.execute('select %s from %s' % (', '.join(q(c) for c in pk_cols), q(table))).fetchall()
    except sqlite3.Error:
        return set()
    return {tuple(r) for r in rows}


def _existing_unique(con, table: str, tm) -> dict:
    """UNIQUE single-column value sets already present in the compact copy."""
    out = {}
    for cm in tm.columns:
        if cm.unique:
            try:
                rows = con.execute('select %s from %s' % (q(cm.name), q(table))).fetchall()
                out[cm.name] = {r[0] for r in rows}
            except sqlite3.Error:
                out[cm.name] = set()
    return out


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact database, append generated rows with executemany, atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        shutil.copyfile(orig, part)
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
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            existing = _existing_keys(con, t, tm.primary_key)
            unique_seen = _existing_unique(con, t, tm)
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            batch = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                if tm.primary_key:
                    k = tuple(row[names.index(c)] for c in tm.primary_key)
                    if k in existing:
                        bad[t] += 1
                        continue
                    existing.add(k)
                skip_row = False
                for cname, vals in unique_seen.items():
                    v = row[names.index(cname)]
                    if v in vals:
                        skip_row = True
                        break
                    vals.add(v)
                if skip_row:
                    bad[t] += 1
                    continue
                batch.append(row)
            if batch:
                try:
                    con.executemany(sql, batch)
                    ok[t] += len(batch)
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
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except Exception:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
