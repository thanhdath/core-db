"""Unit writing (sql_util/writedb.py:292-369)."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _table_order(schema) -> list:
    """Foreign-key order: parents before children (schema.table_order levels)."""
    out = []
    for lvl in schema.table_order:
        out.extend(lvl)
    seen = set(out)
    for t in schema.tables:
        if t not in seen:
            out.append(t)
    return out


def _fk_violations(con, schema) -> int:
    """Count orphan rows for every FK (generated rows only)."""
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
    """Copy the compact DB, append generated rows with executemany, atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig_path:
        shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not orig_path:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t in _table_order(schema):
            tm = schema.tables[t]
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n_compact = int(schema.original_sizes.get(t, 0))
            n_total = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n_total <= n_compact:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = [[cols[c][i] for c in names] for i in range(n_compact, n_total)]
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
        fk_viol = _fk_violations(con, schema)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_viol}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_viol}
