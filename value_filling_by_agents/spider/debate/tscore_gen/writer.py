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


def _compact_rows(con, table: str, columns: list) -> list:
    sel = 'select %s from %s order by rowid' % (', '.join(q(c) for c in columns), q(table))
    return con.execute(sel).fetchall()


def _check_compact_preserved(orig_path: str, path: str, schema) -> dict:
    """Compare compact rows in the generated instance against the original compact DB."""
    if not orig_path or not os.path.exists(orig_path):
        return {'ok': True, 'note': 'no original'}
    try:
        o = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig_path, uri=True)
        g = sqlite3.connect('file:%s?mode=ro&immutable=1' % path, uri=True)
        try:
            res = {}
            ok = True
            for t, tm in schema.tables.items():
                cols = [c.name for c in tm.columns]
                n_orig = o.execute('select count(*) from %s' % q(t)).fetchone()[0]
                orig_rows = _compact_rows(o, t, cols)
                gen_rows = g.execute('select %s from %s order by rowid limit %d'
                                     % (', '.join(q(c) for c in cols), q(t), n_orig)).fetchall()
                same = orig_rows == gen_rows
                res[t] = {'n_orig': n_orig, 'same': same}
                ok = ok and same
            return {'ok': ok, 'tables': res}
        finally:
            o.close()
            g.close()
    except Exception as e:
        return {'ok': False, 'error': repr(e)}


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany; atomic, mode 0644."""
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
    try:
        with open(path + '.counts.json', 'w') as f:
            json.dump({'rows_ok': ok, 'rows_failed': bad}, f)
    except OSError:
        pass
    try:
        pres = _check_compact_preserved(orig_path, path, schema)
        checks = instance.get('_checks', {})
        checks['compact_preserved'] = pres
        with open(path + '.checks.json', 'w') as f:
            json.dump({str(k): v for k, v in checks.items()}, f, default=str)
    except OSError:
        pass
    return {'rows_ok': ok, 'rows_failed': bad}
