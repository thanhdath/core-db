"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _compact_counts(con, schema) -> dict:
    out = {}
    for t in schema.tables:
        try:
            out[t] = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
        except sqlite3.Error:
            out[t] = 0
    return out


def _classify(err: str) -> str:
    """Map a sqlite error message to a skip reason."""
    e = err.lower()
    if 'unique constraint failed' in e:
        if 'primary key' in e:
            return 'pk'
        return 'unique'
    if 'foreign key constraint failed' in e:
        return 'fk'
    if 'not null constraint failed' in e:
        return 'notnull'
    if 'check constraint failed' in e:
        return 'check'
    return 'other'


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB, append generated rows (executemany, one transaction), atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad, reasons = {}, {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        if orig is None:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        base = _compact_counts(con, schema)
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            if not names:
                ok[t] = bad[t] = 0
                continue
            n_base = base.get(t, 0)
            n_total = max((len(cols.get(c, [])) for c in names), default=0)
            n_gen = max(0, n_total - n_base)
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            reasons[t] = {}
            if n_gen <= 0:
                continue
            rows = []
            for i in range(n_gen):
                row = []
                for c in names:
                    vals = cols.get(c, [])
                    j = n_base + i
                    row.append(vals[j] if j < len(vals) else None)
                rows.append(row)
            try:
                con.executemany(sql, rows)
                ok[t] += len(rows)
            except (sqlite3.Error, OverflowError):
                for r in rows:
                    try:
                        con.execute(sql, r)
                        ok[t] += 1
                    except (sqlite3.Error, OverflowError) as e:
                        bad[t] += 1
                        why = _classify(str(e))
                        reasons[t][why] = reasons[t].get(why, 0) + 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad, 'reasons': reasons}
