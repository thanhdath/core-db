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


def _compact_sizes(orig: str) -> dict:
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    try:
        names = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()]
        return {t: con.execute('select count(*) from %s' % q(t)).fetchone()[0] for t in names}
    finally:
        con.close()


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if not (orig and os.path.exists(orig)):
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        base = _compact_sizes(orig) if (orig and os.path.exists(orig)) else {}
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            start = base.get(t, 0)
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            rows = []
            for i in range(start, n):
                rows.append([cols[c][i] for c in names])
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
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    stats = {'rows_ok': ok, 'rows_failed': bad}
    try:
        with open(path + '.stats.json', 'w') as f:
            json.dump(stats, f)
    except OSError:
        pass
    return stats
