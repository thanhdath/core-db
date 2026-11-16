"""Unit writing: copy of the compact database + appended generated rows."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _offset_pk(schema, instance: dict) -> dict:
    """Shift generated single-column integer PKs past the compact max so keys stay fresh."""
    out = {}
    for t, cols in instance.items():
        tm = schema.tables.get(t)
        if tm is None or len(tm.primary_key) != 1:
            out[t] = cols
            continue
        pk = tm.primary_key[0]
        if pk not in cols:
            out[t] = cols
            continue
        ov = [v for v in schema.original_values.get((t, pk), []) if isinstance(v, int)]
        base = (max(ov) if ov else 0) + 1
        new = dict(cols)
        new[pk] = [base + i for i in range(len(cols[pk]))]
        out[t] = new
    return out


def _post_checks(con: sqlite3.Connection) -> dict:
    """Verify the specification targets over the final (compact + generated) tables."""
    checks: dict = {}
    try:
        fk = con.execute('pragma foreign_key_check').fetchall()
        checks['fk_ok'] = len(fk) == 0
        rows = con.execute('select enzyme_id, count(*) from medicine_enzyme_interaction '
                           'group by enzyme_id').fetchall()
        sizes = [r[1] for r in rows]
        checks['enzyme_groups_1_2_3'] = (1 in sizes) and (2 in sizes) and any(s >= 3 for s in sizes)
        rows = con.execute('select medicine_id, count(*) from medicine_enzyme_interaction '
                           'group by medicine_id').fetchall()
        sizes = [r[1] for r in rows]
        checks['medicine_groups_1_2_3'] = (1 in sizes) and (2 in sizes) and any(s >= 3 for s in sizes)
        n_types = con.execute('select count(distinct interaction_type) from medicine_enzyme_interaction '
                              'where interaction_type is not null').fetchone()[0]
        checks['both_types'] = n_types == 2
        n_e = con.execute('select count(*) from enzyme where id not in '
                          '(select enzyme_id from medicine_enzyme_interaction '
                          'where enzyme_id is not null)').fetchone()[0]
        n_m = con.execute('select count(*) from medicine where id not in '
                          '(select medicine_id from medicine_enzyme_interaction '
                          'where medicine_id is not null)').fetchone()[0]
        checks['unmatched_enzyme'] = n_e >= 1
        checks['unmatched_medicine'] = n_m >= 1
        n_rows, n_dist = con.execute('select count(enzyme_id), count(distinct enzyme_id) '
                                     'from medicine_enzyme_interaction').fetchone()
        share = (1.0 - n_dist / n_rows) if n_rows else 0.0
        checks['dup_share'] = 0.2 <= share <= 0.5
        checks['dup_share_value'] = round(share, 3)
    except sqlite3.Error:
        checks.setdefault('fk_ok', False)
    return checks


def write_instance_sqlite(schema, instance: dict, path: str, orig: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic replace, mode 0644."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    if orig is not None:
        shutil.copyfile(orig, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    checks: dict = {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        if orig is None:
            for s in schema.ddl:
                try:
                    con.execute(s)
                except sqlite3.Error:
                    pass
        instance = _offset_pk(schema, instance)
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            ok[t] = bad[t] = 0
            batch = []
            for i in range(n):
                batch.append([cols[c][i] for c in names])
            if batch:
                try:
                    con.executemany(sql, batch)
                    ok[t] = len(batch)
                except (sqlite3.Error, OverflowError):
                    for row in batch:
                        try:
                            con.execute(sql, row)
                            ok[t] += 1
                        except (sqlite3.Error, OverflowError):
                            bad[t] += 1
        con.commit()
        checks = _post_checks(con)
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad, 'checks': checks}
