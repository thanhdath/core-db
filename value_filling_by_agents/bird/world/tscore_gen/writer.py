"""Unit writing (compact-copy + append, sql_util/writedb.py:292-369 adapted)."""
import os
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _pragma(con):
    con.execute('pragma journal_mode=MEMORY')
    con.execute('pragma synchronous=OFF')
    con.execute('pragma temp_store=MEMORY')


def check_foreign_keys(path: str) -> int:
    """Re-open the written DB with FK enforcement and count violations (0 expected)."""
    try:
        con = sqlite3.connect(path)
        try:
            con.execute('pragma foreign_keys = ON')
            rows = con.execute('pragma foreign_key_check').fetchall()
            return len(rows)
        finally:
            con.close()
    except sqlite3.Error:
        return -1


def write_copy_with_appends(schema, orig_path: str, rows: dict, path: str) -> dict:
    """Copy the compact DB, then append generated rows table by table (FK order) and commit once."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    src = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig_path, uri=True)
    con = sqlite3.connect(part)
    okc: dict = {}
    badc: dict = {}
    dropped_parent_keys: dict = {}
    try:
        _pragma(con)
        con.execute('pragma foreign_keys = OFF')
        for ty, name, sql in src.execute(
                "select type,name,sql from sqlite_master where sql is not null order by rowid").fetchall():
            if str(name).startswith('sqlite_'):
                continue
            try:
                con.execute(sql)
            except sqlite3.Error:
                pass
        con.execute('begin')
        for t in schema.tables:
            cols = [c.name for c in schema.tables[t].columns]
            try:
                srows = src.execute('select %s from %s' % (', '.join(q(c) for c in cols), q(t))).fetchall()
            except sqlite3.Error:
                srows = []
            ins = 'INSERT INTO %s (%s) VALUES (%s)' % (q(t), ','.join(q(c) for c in cols), ','.join('?' * len(cols)))
            if srows:
                con.executemany(ins, srows)
        existing: dict = {}
        for t, tm in schema.tables.items():
            cols = [c.name for c in tm.columns]
            sel = 'select %s from %s' % (', '.join(q(c) for c in cols), q(t))
            try:
                cur = con.execute(sel)
                existing[t] = [tuple(r) for r in cur.fetchall()]
            except sqlite3.Error:
                existing[t] = []

        def key_sets(t, tm):
            sets = []
            pk = [c for c in tm.primary_key]
            if pk:
                sets.append(('pk', pk))
            for cm in tm.columns:
                if getattr(cm, 'unique', False) and cm.name not in pk:
                    sets.append(('u:' + cm.name, [cm.name]))
            for (tt, cc) in getattr(schema, 'unique_from_index', []):
                if tt == t and cc not in pk and not any(cm.name == cc and cm.unique for cm in tm.columns):
                    sets.append(('u:' + cc, [cc]))
            return sets

        for t in [x for lvl in schema.table_order for x in lvl if x in schema.tables]:
            tm = schema.tables[t]
            colnames = [c.name for c in tm.columns]
            body = rows.get(t, {})
            n = len(body.get(colnames[0], [])) if colnames else 0
            if n == 0:
                okc[t] = okc.get(t, 0) + 0
                badc[t] = badc.get(t, 0) + 0
                continue
            seen_pk = set()
            seen_u: dict = {}
            if tm.primary_key:
                idx = {c: k for k, c in enumerate(colnames)}
                for er in existing[t]:
                    seen_pk.add(tuple(er[idx[c]] for c in tm.primary_key))
            for tag, kcols in key_sets(t, tm):
                if tag == 'pk':
                    continue
                idx = {c: k for k, c in enumerate(colnames)}
                s = set()
                for er in existing[t]:
                    s.add(tuple(er[idx[c]] for c in kcols))
                seen_u[tag] = s
            ins = 'INSERT INTO %s (%s) VALUES (%s)' % (q(t), ','.join(q(c) for c in colnames),
                                                       ','.join('?' * len(colnames)))
            batch = []
            ok, bad = 0, 0
            dropped = set()
            for i in range(n):
                row = [body[c][i] for c in colnames]
                rm = dict(zip(colnames, row))
                if tm.primary_key:
                    kt = tuple(rm.get(c) for c in tm.primary_key)
                    if kt in seen_pk:
                        bad += 1
                        dropped.add(kt)
                        continue
                dup = False
                for tag, kcols in key_sets(t, tm):
                    if tag == 'pk':
                        continue
                    kt = tuple(rm.get(c) for c in kcols)
                    if kt in seen_u.get(tag, set()):
                        dup = True
                        break
                if dup:
                    bad += 1
                    if tm.primary_key:
                        dropped.add(tuple(rm.get(c) for c in tm.primary_key))
                    continue
                batch.append(row)
                if tm.primary_key:
                    seen_pk.add(tuple(rm.get(c) for c in tm.primary_key))
                for tag, kcols in key_sets(t, tm):
                    if tag == 'pk':
                        continue
                    seen_u.setdefault(tag, set()).add(tuple(rm.get(c) for c in kcols))
            try:
                if batch:
                    con.executemany(ins, batch)
                ok = len(batch)
            except (sqlite3.Error, OverflowError):
                ok = 0
                for row in batch:
                    try:
                        con.execute(ins, row)
                        ok += 1
                    except (sqlite3.Error, OverflowError):
                        bad += 1
                        if tm.primary_key:
                            rm = dict(zip(colnames, row))
                            dropped.add(tuple(rm.get(c) for c in tm.primary_key))
            okc[t] = okc.get(t, 0) + ok
            badc[t] = badc.get(t, 0) + bad
            if dropped:
                dropped_parent_keys[t] = dropped
        con.commit()
    finally:
        con.close()
        src.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'ok': okc, 'bad': badc, 'dropped_parent_keys': dropped_parent_keys}
