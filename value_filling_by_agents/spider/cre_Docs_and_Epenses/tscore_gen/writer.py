"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _fk_membership_ok(schema, table: str, row: list, names: list, parent_sets: dict) -> bool:
    """True if every non-NULL FK value of the row is a member of the parent PK set."""
    idx = {c: j for j, c in enumerate(names)}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct != table or cc not in idx:
            continue
        v = row[idx[cc]]
        if v is None:
            continue
        if v not in parent_sets.get((pt, pc), set()):
            return False
    return True


def write_instance_sqlite(schema, instance: dict, path: str) -> dict:
    """Copy the compact database, append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    parent_sets: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        s = set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        s |= set(v for v in instance.get(pt, {}).get(pc, []) if v is not None)
        parent_sets[(pt, pc)] = s
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % schema.orig_path, uri=True)
    dst = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        src.backup(dst)
        dst.execute('pragma journal_mode = MEMORY')
        dst.execute('pragma synchronous = OFF')
        dst.execute('pragma temp_store = MEMORY')
        dst.execute('pragma foreign_keys = OFF')
        dst.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(n):
                row = [cols[c][i] for c in names]
                if not _fk_membership_ok(schema, t, row, names, parent_sets):
                    bad[t] += 1
                    continue
                rows.append(row)
            if rows:
                try:
                    dst.executemany(sql, rows)
                    ok[t] = len(rows)
                except (sqlite3.Error, OverflowError):
                    for r in rows:
                        try:
                            dst.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        dst.commit()
    finally:
        dst.close()
        src.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
