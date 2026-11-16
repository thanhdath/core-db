"""Unit writing (sql_util/writedb.py:292-369) + round-1 copy-of-compact semantics."""
import json
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _copy_compact(orig: str, dest: str) -> None:
    """Copy the compact database to dest (schema + rows) using the backup API."""
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy compact DB + append generated rows; failing rows skipped and counted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        _copy_compact(orig, part)
        con = sqlite3.connect(part)
    else:
        con = sqlite3.connect(part)
        con.execute('pragma foreign_keys = OFF')
        for s in schema.ddl:
            try:
                con.execute(s)
            except sqlite3.Error:
                pass
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        con.execute('begin')
        order = [t for lvl in schema.table_order for t in lvl]
        for t in order:
            tm = schema.tables[t]
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
                    ok[t] = len(rows)
                except (sqlite3.Error, OverflowError):
                    ok[t] = 0
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    counts = {'rows_ok': ok, 'rows_failed': bad}
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump(counts, f)
    except OSError:
        pass
    return counts
