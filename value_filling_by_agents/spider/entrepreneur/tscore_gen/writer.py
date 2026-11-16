"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _check_integrity(con, schema) -> None:
    """Assert every non-NULL child FK resolves and PK tuples are unique (in-memory check)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in schema.tables or pt not in schema.tables:
            continue
        bad = con.execute(
            'select count(*) from %s c where c.%s is not null and not exists '
            '(select 1 from %s p where p.%s = c.%s)' % (q(ct), q(cc), q(pt), q(pc), q(cc))).fetchone()[0]
        if bad:
            raise RuntimeError('fk violation %s.%s -> %s.%s: %d rows' % (ct, cc, pt, pc, bad))
    for t, tm in schema.tables.items():
        if not tm.primary_key:
            continue
        cols = ', '.join(q(c) for c in tm.primary_key)
        dup = con.execute('select count(*) from (select %s from %s group by %s having count(*) > 1)'
                          % (cols, q(t), cols)).fetchone()[0]
        if dup:
            raise RuntimeError('pk duplicate in %s: %d groups' % (t, dup))


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
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
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                rows.append([cols[c][i] for c in names])
            if rows:
                try:
                    con.executemany(sql, rows)
                    ok[t] += len(rows)
                except (sqlite3.Error, OverflowError):
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
        _check_integrity(con, schema)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
