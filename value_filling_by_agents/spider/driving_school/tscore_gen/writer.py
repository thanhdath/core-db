"""Unit writing: copy compact DB, append generated rows with executemany; atomic."""
import os
import sqlite3

from .schema import q


def unit_path(root, ds, db, i, tag='gen'):
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _compact_pks(con, schema):
    """Read compact PK values per table (for superset assertion)."""
    out = {}
    for t, tm in schema.tables.items():
        if not tm.pk:
            continue
        try:
            rows = con.execute('SELECT %s FROM %s' % (
                ','.join(q(c) for c in tm.pk), q(t))).fetchall()
            out[t] = set(rows)
        except sqlite3.Error:
            out[t] = set()
    return out


def _copy_compact(orig_path, part):
    """Consistent copy of the compact DB via the sqlite3 backup API."""
    src = sqlite3.connect('file:%s?mode=ro' % orig_path, uri=True)
    dst = sqlite3.connect(part)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def write_instance_sqlite(schema, instance, path, orig_path=None):
    """Copy the compact DB, append generated rows; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path and os.path.exists(orig_path):
        _copy_compact(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        if not (orig_path and os.path.exists(orig_path)):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        compact_pks = _compact_pks(con, schema)
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = []
            for i in range(n):
                rows.append([cols[c][i] if c in cols else None for c in names])
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
        viol = con.execute('PRAGMA foreign_key_check').fetchall()
        if viol:
            raise RuntimeError('foreign_key_check violations: %r' % (viol[:5],))
        for t, tm in schema.tables.items():
            if not tm.pk or t not in compact_pks:
                continue
            try:
                rows = con.execute('SELECT %s FROM %s' % (
                    ','.join(q(c) for c in tm.pk), q(t))).fetchall()
                final = set(rows)
            except sqlite3.Error:
                continue
            if not compact_pks[t].issubset(final):
                raise RuntimeError('compact PKs of %s not preserved' % t)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
