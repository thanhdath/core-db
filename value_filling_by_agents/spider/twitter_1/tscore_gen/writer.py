"""Unit writing (sql_util/writedb.py:292-369), adapted for round 1."""
import json
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, part: str) -> None:
    """Copy the compact database to the part file (schema + compact rows preserved)."""
    if os.path.exists(part):
        os.remove(part)
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    dst = sqlite3.connect(part)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _existing_keys(con, table: str, pk_cols: list) -> set:
    """Existing PK tuples in the (copied) compact database, so generated rows never collide."""
    if not pk_cols:
        return set()
    sel = 'select %s from %s' % (', '.join(q(c) for c in pk_cols), q(table))
    try:
        return {tuple(r) for r in con.execute(sel).fetchall()}
    except sqlite3.Error:
        return set()


def _fk_violations(con, schema) -> int:
    """Count non-NULL FK values that do not exist in the parent table (post-write check)."""
    bad = 0
    for (ct, cc), (pt, pc) in schema.fks.items():
        try:
            n = con.execute(
                'select count(*) from %s c where c.%s is not null and not exists '
                '(select 1 from %s p where p.%s = c.%s)' % (q(ct), q(cc), q(pt), q(pc), q(cc))
            ).fetchone()[0]
            bad += int(n)
        except sqlite3.Error:
            pass
    return bad


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany in one transaction; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if orig is None:
        if os.path.exists(part):
            os.remove(part)
        con = sqlite3.connect(part)
        try:
            con.execute('pragma foreign_keys = OFF')
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
            con.commit()
        finally:
            con.close()
    else:
        _copy_compact(orig, part)
    ok, bad = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            existing = _existing_keys(con, t, tm.primary_key)
            rows = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                if tm.primary_key:
                    k = tuple(row[names.index(c)] for c in tm.primary_key)
                    if k in existing:
                        bad[t] += 1
                        continue
                    existing.add(k)
                rows.append(row)
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
        con.commit()
        viol = _fk_violations(con, schema)
    finally:
        con.close()
    if viol:
        try:
            os.remove(part)
        except OSError:
            pass
        raise RuntimeError('fk_violations=%d' % viol)
    os.chmod(part, 0o644)
    os.replace(part, path)
    counts = {'rows_ok': ok, 'rows_failed': bad}
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump(counts, f)
    except OSError:
        pass
    return counts
