"""Unit writing (sql_util/writedb.py:292-369) + appended rows to a copy of the compact database."""
import json
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _stats_path(root: str, ds: str, db: str, tag: str) -> str:
    return os.path.join(root, ds, '%s__%s_stats.json' % (db, tag))


def _bump_stats(root: str, ds: str, db: str, tag: str, ok: dict, bad: dict) -> None:
    """Accumulate rows_added / rows_skipped per table across instances (best effort)."""
    p = _stats_path(root, ds, db, tag)
    try:
        with open(p) as f:
            st = json.load(f)
    except Exception:
        st = {'rows_added': {}, 'rows_skipped': {}}
    for t, v in ok.items():
        st['rows_added'][t] = st['rows_added'].get(t, 0) + v
    for t, v in bad.items():
        st['rows_skipped'][t] = st['rows_skipped'].get(t, 0) + v
    try:
        with open(p, 'w') as f:
            json.dump(st, f)
    except Exception:
        pass


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows with executemany in one transaction."""
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
            if not rows:
                continue
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
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    root = os.path.dirname(os.path.dirname(path))
    ds = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))
    base = os.path.basename(path)
    unit_dir = os.path.basename(os.path.dirname(path))
    if '__' in unit_dir:
        db, tag = unit_dir.split('__', 1)
        tag = tag.rsplit('_', 1)[0]
        _bump_stats(root, ds, db, tag, ok, bad)
    return {'rows_ok': ok, 'rows_failed': bad}
