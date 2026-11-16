"""Unit writing (sql_util/writedb.py:292-369) adapted to append to a copy of the compact database."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, part: str) -> None:
    """Copy the compact database (schema + rows) to the part file."""
    shutil.copyfile(orig, part)


def _align(instance: dict, schema) -> tuple:
    """Ensure every column of every table has the same length (defensive, spec rule 'shaping')."""
    out = {}
    for t, tm in schema.tables.items():
        cols = instance.get(t, {})
        names = [c.name for c in tm.columns if c.name in cols]
        if not names:
            out[t] = {}
            continue
        n = len(cols[names[0]])
        aligned = {}
        for c in names:
            v = list(cols[c])
            if len(v) < n:
                v += [None] * (n - len(v))
            aligned[c] = v[:n]
        out[t] = aligned
    return out


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy of the compact database + generated rows appended with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    instance = _align(instance, schema)
    if orig is not None:
        _copy_compact(orig, part)
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
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            ok[t] = bad[t] = 0
            if not n:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = [[cols.get(c, [None] * n)[i] for c in names] for i in range(n)]
            try:
                con.executemany(sql, rows)
                ok[t] = n
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
    counts = {'rows_ok': ok, 'rows_failed': bad}
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump(counts, f)
    except OSError:
        pass
    return counts
