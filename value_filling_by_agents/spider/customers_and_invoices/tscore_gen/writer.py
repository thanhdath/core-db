"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root, ds, db, i, tag='gen'):
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _validate(con, schema, orig_sizes, target_sizes):
    """Post-write validation: compact rows preserved, target counts met, FKs valid, PKs unique."""
    for t in schema.tables:
        n = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
        want = orig_sizes.get(t, 0) + target_sizes.get(t, 0)
        if n != want:
            raise RuntimeError('row count mismatch for %s: %d != %d' % (t, n, want))
        tm = schema.tables[t]
        if tm.primary_key:
            pk = tm.primary_key
            cols = ', '.join(q(c) for c in pk)
            dup = con.execute('select %s, count(*) c from %s group by %s having c > 1 limit 1'
                              % (cols, q(t), cols)).fetchone()
            if dup is not None:
                raise RuntimeError('duplicate PK in %s: %r' % (t, dup))
    for (ct, cc), (pt, pc) in schema.fks.items():
        bad = con.execute('select count(*) from %s c where c.%s is not null and not exists '
                          '(select 1 from %s p where p.%s = c.%s)'
                          % (q(ct), q(cc), q(pt), q(pc), q(cc))).fetchone()[0]
        if bad:
            raise RuntimeError('FK violation %s.%s -> %s.%s: %d rows' % (ct, cc, pt, pc, bad))


def write_instance_sqlite(schema, instance, path, orig=None):
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    target_sizes = {}
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
            target_sizes[t] = n
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = [[cols[c][i] for c in names] for i in range(n)]
            if rows:
                con.executemany(sql, rows)
                ok[t] = len(rows)
        con.commit()
        _validate(con, schema, schema.original_sizes, target_sizes)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
