"""Unit writing (sql_util/writedb.py:292-369)."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _insert_rows(con, schema, instance, ok, bad):
    for t in schema.table_order:
        for tt in (t if isinstance(t, list) else [t]):
            tm = schema.tables.get(tt)
            if tm is None:
                continue
            cols = instance.get(tt, {})
            names = [c.name for c in tm.columns]
            n = min(len(cols.get(c, [])) for c in names) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(tt), ','.join('?' * len(names)))
            ok[tt] = bad[tt] = 0
            rows = [[cols[c][i] for c in names] for i in range(n)]
            if rows:
                try:
                    con.executemany(sql, rows)
                    ok[tt] = len(rows)
                except (sqlite3.Error, OverflowError):
                    for r in rows:
                        try:
                            con.execute(sql, r)
                            ok[tt] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[tt] += 1


def _validate_fks(con, schema, ok, bad):
    """Remove generated rows with dangling non-NULL FKs; compact rows are untouched."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in schema.tables or pt not in schema.tables:
            continue
        parent_rows = schema.original_rows.get(pt, [])
        pnames = [c.name for c in schema.tables[pt].columns]
        try:
            pidx = pnames.index(pc)
        except ValueError:
            continue
        compact_pks = {r[pidx] for r in parent_rows if r[pidx] is not None}
        gen_pks = set()
        gen_parent = ok.get(pt, 0)
        if gen_parent:
            try:
                for row in con.execute('select %s from %s' % (q(pc), q(pt))):
                    if row[0] is not None:
                        gen_pks.add(row[0])
            except sqlite3.Error:
                pass
        valid = compact_pks | gen_pks
        if not valid:
            continue
        try:
            compact_child = len(schema.original_rows.get(ct, []))
            bad_rows = []
            sql = 'select rowid, %s from %s where rowid > ?' % (q(cc), q(ct))
            for rid, v in con.execute(sql, (compact_child,)):
                if v is not None and v not in valid:
                    bad_rows.append(rid)
            if bad_rows:
                con.executemany('delete from %s where rowid = ?' % q(ct), [(r,) for r in bad_rows])
                bad[ct] = bad.get(ct, 0) + len(bad_rows)
                ok[ct] = max(0, ok.get(ct, 0) - len(bad_rows))
        except sqlite3.Error:
            pass


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact DB, append generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    ok, bad = {}, {}
    if orig_path and os.path.exists(orig_path):
        shutil.copyfile(orig_path, part)
        con = sqlite3.connect(part)
        try:
            con.execute('pragma journal_mode=MEMORY')
            con.execute('pragma synchronous=OFF')
            con.execute('pragma temp_store=MEMORY')
            con.execute('pragma foreign_keys = OFF')
            con.execute('begin')
            _insert_rows(con, schema, instance, ok, bad)
            con.commit()
            _validate_fks(con, schema, ok, bad)
            con.commit()
        finally:
            con.close()
    else:
        con = sqlite3.connect(part)
        try:
            con.execute('pragma journal_mode=MEMORY')
            con.execute('pragma synchronous=OFF')
            con.execute('pragma temp_store=MEMORY')
            con.execute('pragma foreign_keys = OFF')
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
            con.execute('begin')
            _insert_rows(con, schema, instance, ok, bad)
            con.commit()
        finally:
            con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad}
