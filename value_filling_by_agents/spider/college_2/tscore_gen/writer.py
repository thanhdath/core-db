"""Unit writing (sql_util/writedb.py:292-369), adapted for round 1."""
import os
import shutil
import sqlite3

from .schema import q


def unit_path(root: str, ds: str, db: str, i: int, tag: str = 'gen') -> str:
    """<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite."""
    name = '%s__%s_%04d' % (db, tag, i)
    return os.path.join(root, ds, name, name + '.sqlite')


def _fk_ok(schema, table: str, row: dict, parent_sets: dict) -> bool:
    """Python FK check: every non-NULL FK value must exist in the parent set."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        v = row.get(cm.name)
        if v is None:
            continue
        pt, pc = schema.fks[key]
        if v not in parent_sets.get((pt, pc), set()):
            return False
    return True


def _composite_fk_ok(schema, table: str, row: dict, parent_tuples: dict) -> bool:
    """Python composite-FK check: the tuple is fully NULL or a valid parent tuple."""
    groups: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct == table:
            groups.setdefault(pt, []).append(cc)
    for pt, child_cols in groups.items():
        if len(child_cols) < 2:
            continue
        vals = tuple(row.get(c) for c in child_cols)
        if all(v is None for v in vals):
            continue
        if any(v is None for v in vals):
            return False
        if vals not in parent_tuples.get(pt, set()):
            return False
    return True


def _final_parent_sets(schema, instance: dict) -> tuple:
    """Parent value sets and composite tuples from the FINAL written rows."""
    parent_sets: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        s = parent_sets.setdefault((pt, pc), set())
        s.update(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        s.update(v for v in instance.get(pt, {}).get(pc, []) if v is not None)
    parent_tuples: dict = {}
    groups: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        groups.setdefault((ct, pt), []).append(cc)
    for (ct, pt), child_cols in groups.items():
        if len(child_cols) < 2:
            continue
        pcs = tuple(schema.fks[(ct, c)][1] for c in child_cols)
        idx = {c: i for i, c in enumerate(pcs)}
        s = parent_tuples.setdefault(pt, set())
        for row in schema.original_rows.get(pt, []):
            tup = tuple(row[idx[pc]] for pc in pcs)
            if all(v is not None for v in tup):
                s.add(tup)
        gen = instance.get(pt, {})
        if all(pc in gen for pc in pcs):
            n = min(len(gen[pc]) for pc in pcs)
            for i in range(n):
                tup = tuple(gen[pc][i] for pc in pcs)
                if all(v is not None for v in tup):
                    s.add(tup)
    return parent_sets, parent_tuples


def write_instance_sqlite(schema, instance: dict, path: str, orig_path: str = None) -> dict:
    """Copy the compact database, append generated rows, atomic replace."""
    if not orig_path or not os.path.exists(orig_path):
        raise FileNotFoundError('compact database not found: %r' % (orig_path,))
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    part = path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig_path, part)
    con = sqlite3.connect(part)
    ok, bad = {}, {}
    try:
        con.execute('pragma journal_mode = MEMORY')
        con.execute('pragma synchronous = OFF')
        con.execute('pragma temp_store = MEMORY')
        con.execute('pragma foreign_keys = ON')
        parent_sets, parent_tuples = _final_parent_sets(schema, instance)
        con.execute('begin')
        for t, tm in schema.tables.items():
            cols = instance.get(t, {})
            names = [c.name for c in tm.columns]
            n = len(cols.get(names[0], [])) if names else 0
            ok[t] = bad[t] = 0
            if n == 0:
                continue
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            rows = []
            for i in range(n):
                row = {c: cols[c][i] for c in names}
                if not _fk_ok(schema, t, row, parent_sets):
                    bad[t] += 1
                    continue
                if not _composite_fk_ok(schema, t, row, parent_tuples):
                    bad[t] += 1
                    continue
                rows.append([row[c] for c in names])
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
        fk_violations = 0
        try:
            fk_violations = len(con.execute('pragma foreign_key_check').fetchall())
        except sqlite3.Error:
            fk_violations = -1
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, path)
    return {'rows_ok': ok, 'rows_failed': bad, 'fk_violations': fk_violations}
