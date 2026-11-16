"""Unit writing (sql_util/writedb.py:292-369) adapted for appended spec rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _check_fks(con, schema) -> None:
    """Explicit FK validation over the whole database (compact + generated rows)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        sql = ('SELECT COUNT(*) FROM %s c WHERE c.%s IS NOT NULL AND NOT EXISTS '
               '(SELECT 1 FROM %s p WHERE p.%s = c.%s)'
               % (q(ct), q(cc), q(pt), q(pc), q(cc)))
        bad = con.execute(sql).fetchone()[0]
        if bad:
            raise RuntimeError('FK violation %s.%s -> %s.%s: %d rows' % (ct, cc, pt, pc, bad))


def write_spec_instance(schema, rows: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, then INSERT the generated rows inside one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode=MEMORY')
        con.execute('pragma synchronous=OFF')
        con.execute('pragma temp_store=MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = rows.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            if n == 0:
                ok[t] = bad[t] = 0
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            payload = [[cols[c][i] if c in cols else None for c in names] for i in range(n)]
            if payload:
                try:
                    con.executemany(sql, payload)
                    ok[t], bad[t] = len(payload), 0
                except sqlite3.Error:
                    good = 0
                    errored = 0
                    for row in payload:
                        try:
                            con.execute(sql, row)
                            good += 1
                        except (sqlite3.Error, OverflowError):
                            errored += 1
                    ok[t], bad[t] = good, errored
        _check_fks(con, schema)
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
