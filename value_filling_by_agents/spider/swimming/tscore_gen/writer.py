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


def _insert_rows(con, table: str, names: list, rows: list) -> tuple:
    """executemany inside the open transaction; per-row fallback to count failures."""
    if not rows:
        return 0, 0
    sql = 'INSERT INTO %s VALUES (%s)' % (q(table), ','.join('?' * len(names)))
    try:
        con.executemany(sql, rows)
        return len(rows), 0
    except (sqlite3.Error, OverflowError):
        ok = bad = 0
        for r in rows:
            try:
                con.execute(sql, r)
                ok += 1
            except (sqlite3.Error, OverflowError):
                bad += 1
        return ok, bad


def _post_checks(con, schema, orig_sizes: dict) -> dict:
    """Read-only checks on the written instance (compact rows preserved, PK pairs unique)."""
    checks = {'compact_preserved': True, 'dup_pk_pairs': {}, 'null_share': {}}
    for t, tm in schema.tables.items():
        try:
            n = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
        except sqlite3.Error:
            continue
        if n < int(orig_sizes.get(t, 0)):
            checks['compact_preserved'] = False
        if len(tm.primary_key) > 1:
            cols = ', '.join(q(c) for c in tm.primary_key)
            try:
                d = con.execute('select count(*) from (select %s from %s group by %s having count(*) > 1)'
                                % (cols, q(t), cols)).fetchone()[0]
                checks['dup_pk_pairs'][t] = int(d)
            except sqlite3.Error:
                pass
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            try:
                nn = con.execute('select count(*) from %s where %s is null' % (q(t), q(cm.name))).fetchone()[0]
                checks['null_share']['%s.%s' % (t, cm.name)] = round(nn / float(n), 4) if n else 0.0
            except sqlite3.Error:
                pass
    return checks


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None,
                          dropped: dict = None) -> dict:
    """Copy the compact DB, append generated rows, atomic replace, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig and os.path.exists(orig):
        shutil.copyfile(orig, part)
        con = sqlite3.connect(part)
        created = False
    else:
        con = sqlite3.connect(part)
        created = True
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = OFF')
        if created:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names and names[0] in cols else 0
            rows = [[cols[c][i] for c in names] for i in range(n)]
            ok[t], bad[t] = _insert_rows(con, t, names, rows)
            if dropped and dropped.get(t):
                bad[t] += int(dropped[t])
        con.commit()
        checks = _post_checks(con, schema, schema.original_sizes)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad, 'checks': checks}, f)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad, 'checks': checks}
