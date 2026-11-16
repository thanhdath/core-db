"""Unit writing (sql_util/writedb.py:292-369), adapted to append over a compact copy."""
import os
import shutil
import sqlite3

from . import spec
from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _check_copy_rules(instance: dict) -> int:
    """Count generated child rows whose copied column is NULL while the parent value is not."""
    bad = 0
    for (ct, cc), (pt, pc, copied) in spec.COPY_RULES.items():
        cols = instance.get(ct, {})
        fk_vals = cols.get(cc)
        if fk_vals is None:
            continue
        parent = instance.get(pt, {})
        pkey = parent.get(pc, [])
        by_key = {}
        for i, k in enumerate(pkey):
            by_key.setdefault(k, i)
        for child_col in copied:
            cv = cols.get(child_col)
            if cv is None:
                continue
            pcol = parent.get(child_col, [])
            for fk, v in zip(fk_vals, cv):
                if fk is None or v is not None:
                    continue
                pi = by_key.get(fk)
                if pi is not None and pi < len(pcol) and pcol[pi] is not None:
                    bad += 1
    return bad


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
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
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = []
            for i in range(n):
                rows.append(tuple(cols[c][i] for c in names))
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
        copy_violations = _check_copy_rules(instance)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad, 'copy_violations': copy_violations}
