"""Instance writer: copy the compact database and append generated rows."""
import json
import os
import shutil
import sqlite3


def unit_path(root: str, ds: str, db: str, i: int, tag: str) -> str:
    """Return the instance path for unit i."""
    d = os.path.join(root, ds, '%s__%s_%04d' % (db, tag, i))
    return os.path.join(d, '%s__%s_%04d.sqlite' % (db, tag, i))


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _existing_keys(con, table, cols):
    """Return the set of existing tuples for the given columns (compact rows)."""
    if not cols:
        return set()
    cur = con.cursor()
    cur.execute('SELECT %s FROM %s' % (', '.join(_quote(c) for c in cols), _quote(table)))
    return {tuple(r) for r in cur.fetchall()}


def write_instance_sqlite(schema, inst: dict, path: str, orig: str) -> None:
    """Copy the compact DB to path and append generated rows (one transaction)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    shutil.copyfile(orig, tmp)
    con = sqlite3.connect(tmp)
    rows_ok = {}
    rows_failed = {}
    try:
        con.execute('PRAGMA journal_mode=MEMORY')
        con.execute('PRAGMA synchronous=OFF')
        con.execute('PRAGMA temp_store=MEMORY')
        con.execute('PRAGMA foreign_keys=OFF')
        cur = con.cursor()
        for t, tm in schema.tables.items():
            cols = inst.get(t) or {}
            if not cols:
                rows_ok[t] = 0
                rows_failed[t] = 0
                continue
            colnames = [c.name for c in tm.columns if c.name in cols]
            if not colnames:
                rows_ok[t] = 0
                rows_failed[t] = 0
                continue
            n = len(cols[colnames[0]])
            pk = tm.primary_key
            existing_pk = _existing_keys(con, t, pk) if pk else set()
            existing_uniq = []
            for ucols in tm.unique_sets:
                if all(c in cols for c in ucols):
                    existing_uniq.append((ucols, _existing_keys(con, t, list(ucols))))
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                _quote(t), ', '.join(_quote(c) for c in colnames),
                ', '.join('?' for _ in colnames))
            ok = 0
            failed = 0
            seen_pk = set(existing_pk)
            seen_uniq = [(ucols, set(s)) for (ucols, s) in existing_uniq]
            batch = []
            for i in range(n):
                row = tuple(cols[c][i] for c in colnames)
                if pk:
                    k = tuple(cols[c][i] for c in pk)
                    if k in seen_pk:
                        failed += 1
                        continue
                bad = False
                for (ucols, s) in seen_uniq:
                    uk = tuple(cols[c][i] for c in ucols)
                    if uk in s:
                        bad = True
                        break
                if bad:
                    failed += 1
                    continue
                batch.append(row)
                if pk:
                    seen_pk.add(tuple(cols[c][i] for c in pk))
                for (ucols, s) in seen_uniq:
                    s.add(tuple(cols[c][i] for c in ucols))
            if batch:
                try:
                    cur.executemany(sql, batch)
                    ok = len(batch)
                except sqlite3.IntegrityError:
                    ok = 0
                    for row in batch:
                        try:
                            cur.execute(sql, row)
                            ok += 1
                        except sqlite3.IntegrityError:
                            failed += 1
            rows_ok[t] = ok
            rows_failed[t] = failed
        con.commit()
    finally:
        con.close()
    os.replace(tmp, path)
    with open(path + '.counts.json', 'w') as f:
        json.dump({'rows_ok': rows_ok, 'rows_failed': rows_failed}, f)
