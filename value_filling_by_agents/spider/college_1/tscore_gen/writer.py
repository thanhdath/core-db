"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _compact_max_rowid(orig: str, tables) -> dict:
    """Maximum rowid of each compact table (0 when empty); used to scope the FK check."""
    out = {}
    if not orig:
        return out
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    try:
        for t in tables:
            try:
                r = con.execute('select max(rowid) from %s' % q(t)).fetchone()
                out[t] = int(r[0]) if r and r[0] is not None else 0
            except sqlite3.Error:
                out[t] = 0
    finally:
        con.close()
    return out


def _fk_check_generated(con, schema, compact_max: dict) -> None:
    """Raise only if a *generated* row violates a foreign key."""
    for t, tm in schema.tables.items():
        base = compact_max.get(t, 0)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            sql = ('select count(*) from %s c where c.rowid > ? and c.%s is not null '
                   'and not exists (select 1 from %s p where p.%s = c.%s)'
                   % (q(t), q(cm.name), q(pt), q(pc), q(cm.name)))
            try:
                n = con.execute(sql, (base,)).fetchone()[0]
            except sqlite3.Error:
                continue
            if n:
                raise sqlite3.IntegrityError(
                    'generated foreign key violation: %s.%s -> %s.%s (%d rows)'
                    % (t, cm.name, pt, pc, n))


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB, append generated rows, return {'rows_ok': ..., 'rows_failed': ...}."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig:
        shutil.copyfile(orig, part)
    compact_max = _compact_max_rowid(orig, list(schema.tables)) if orig else {}
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                try:
                    rows.append([cols[c][i] for c in names])
                except Exception:
                    bad[t] += 1
            if rows:
                try:
                    con.executemany(sql, rows)
                    ok[t] += len(rows)
                except Exception:
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
        _fk_check_generated(con, schema, compact_max)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
