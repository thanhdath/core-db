"""Copy compact DB + append generated rows with executemany in one transaction."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _column_names(con, table: str) -> list:
    return [r[1] for r in con.execute('pragma table_info(%s)' % q(table)).fetchall()]


def _check_method_parameter_fk(con) -> int:
    """Count non-NULL MethodParameter.MethodId strings that do not parse to an existing Method.Id."""
    try:
        rows = con.execute(
            'select "MethodId" from "MethodParameter" where "MethodId" is not null').fetchall()
    except sqlite3.Error:
        return 0
    try:
        method_ids = {r[0] for r in con.execute('select "Id" from "Method"').fetchall()}
    except sqlite3.Error:
        return 0
    bad = 0
    for (v,) in rows:
        try:
            iv = int(str(v).strip())
        except (TypeError, ValueError):
            bad += 1
            continue
        if iv not in method_ids:
            bad += 1
    return bad


def write_instance(schema, orig: str, instance: dict, path: str) -> dict:
    """Copy the compact DB, append rows (executemany, one transaction), atomic replace."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    added = {}
    skipped = {}
    errors: dict = {}
    try:
        con.execute('pragma journal_mode=memory')
        con.execute('pragma synchronous=off')
        con.execute('pragma temp_store=memory')
        con.execute('pragma foreign_keys=off')
        con.execute('begin')
        for t, rows in instance.items():
            if not rows:
                added[t] = 0
                skipped[t] = 0
                continue
            cols = _column_names(con, t)
            sql = 'insert or ignore into %s (%s) values (%s)' % (
                q(t), ','.join(q(c) for c in cols), ','.join('?' * len(cols)))
            data = [[row.get(c) for c in cols] for row in rows]
            before = con.total_changes
            try:
                con.executemany(sql, data)
                inserted = con.total_changes - before
            except (sqlite3.Error, OverflowError):
                inserted = 0
                for r in data:
                    try:
                        con.execute(sql, r)
                        inserted += 1
                    except (sqlite3.Error, OverflowError):
                        pass
            added[t] = inserted
            skipped[t] = len(data) - inserted
            if skipped[t]:
                errors['skipped_%s' % t] = errors.get('skipped_%s' % t, 0) + skipped[t]
        con.commit()
        bad_fk = _check_method_parameter_fk(con)
        if bad_fk:
            errors['methodparameter_fk_violations'] = bad_fk
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'added': added, 'skipped': skipped, 'errors': errors}
