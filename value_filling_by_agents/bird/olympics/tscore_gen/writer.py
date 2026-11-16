"""Unit writing (sql_util/writedb.py:292-369) + appended-row instance writer."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig_path: str, part: str) -> None:
    """Copy the compact database to the part file (schema + compact rows preserved)."""
    shutil.copyfile(orig_path, part)


def _count_fk_violations(con, schema) -> int:
    """Count generated rows whose FK value is not NULL and not present in the parent column."""
    total = 0
    for (ct, cc), (pt, pc) in schema.fks.items():
        try:
            n = con.execute(
                'SELECT COUNT(*) FROM %s c WHERE c.%s IS NOT NULL AND NOT EXISTS '
                '(SELECT 1 FROM %s p WHERE p.%s = c.%s)' % (q(ct), q(cc), q(pt), q(pc), q(cc))
            ).fetchone()[0]
            total += int(n)
        except sqlite3.Error:
            pass
    return total


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path is not None:
        _copy_compact(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    null_counts: dict = {}
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
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            for c in names:
                if c in cols:
                    null_counts[(t, c)] = sum(1 for v in cols[c] if v is None)
            rows = []
            for i in range(n):
                rows.append([cols[c][i] for c in names])
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
        fk_bad = _count_fk_violations(con, schema)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_bad, 'null_counts': null_counts}
