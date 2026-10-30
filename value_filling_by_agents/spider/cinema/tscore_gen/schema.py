"""Schema reading (upstream sql_util/dbinfo.py)."""
import math
import sqlite3
import warnings
from dataclasses import dataclass, field


@dataclass
class ColumnMeta:
    table: str
    name: str
    type_str: str
    notnull: bool
    default: object
    pk_pos: int
    unique: bool
    checked: bool


@dataclass
class TableMeta:
    name: str
    columns: list
    primary_key: list


@dataclass
class Schema:
    tables: dict
    fks: dict
    ddl: list
    table_order: list
    column_order: list
    original_values: dict = field(default_factory=dict)
    original_sizes: dict = field(default_factory=dict)
    unique_from_index: list = field(default_factory=list)


def q(name: str) -> str:
    """Double-quote an SQL identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def _levels(items: list, deps: dict) -> list:
    """Topological levels; deterministic cycle breaking by smallest remaining item."""
    remaining = sorted(set(items))
    known = set(items)
    placed: set = set()
    out = []
    while remaining:
        lvl = [x for x in remaining if all(d == x or d in placed or d not in known for d in sorted(deps.get(x, ())))]
        if not lvl:
            lvl = [remaining[0]]
        out.append(sorted(lvl))
        placed.update(lvl)
        remaining = [x for x in remaining if x not in placed]
    return out


def process_order(schema_fks: dict, all_columns: list) -> tuple:
    """Column and table topological levels (sql_util/dbinfo.py:122-176). Returns (column_order, table_order)."""
    cdeps: dict = {}
    tdeps: dict = {}
    for (ct, cc), (pt, pc) in sorted(schema_fks.items()):
        if (ct, cc) != (pt, pc):
            cdeps.setdefault((ct, cc), set()).add((pt, pc))
        if ct != pt:
            tdeps.setdefault(ct, set()).add(pt)
    tables = sorted({t for t, _ in all_columns})
    return _levels(list(all_columns), cdeps), _levels(tables, tdeps)


def _first_token(line: str) -> str:
    toks = line.strip().split()
    return toks[0].strip('"`[](),') if toks else ''


def read_schema(orig_path: str, max_rows_per_table: int = 300000) -> Schema:
    """Read tables, columns, keys, FKs and original values read-only (sql_util/dbinfo.py:28-109, 185-233)."""
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig_path, uri=True)
    try:
        master = con.execute("select type, name, sql from sqlite_master where sql is not null order by rowid").fetchall()
        ddl = [s for ty, n, s in master if not str(n).startswith('sqlite_')]
        tnames = [n for ty, n, s in master if ty == 'table' and not str(n).startswith('sqlite_')]
        create = {n: s for ty, n, s in master if ty == 'table'}
        tables: dict = {}
        from_index = []
        for t in tnames:
            info = con.execute('pragma table_info(%s)' % q(t)).fetchall()
            low = {r[1].lower(): r[1] for r in info}
            uniq, chk = set(), set()
            for line in create[t].split('\n'):
                ll = line.lower()
                tok = _first_token(line).lower()
                if 'unique' in ll and tok in low:
                    uniq.add(tok)
                if ('check (' in ll or 'check(' in ll) and tok in low:
                    chk.add(tok)
            for idx in con.execute('pragma index_list(%s)' % q(t)).fetchall():
                if idx[2]:
                    cols = con.execute('pragma index_info(%s)' % q(idx[1])).fetchall()
                    if len(cols) == 1 and cols[0][2] and cols[0][2].lower() not in uniq:
                        uniq.add(cols[0][2].lower())
                        from_index.append((t, cols[0][2]))
            cols = [ColumnMeta(t, r[1], r[2] or '', bool(r[3]), r[4], r[5], r[1].lower() in uniq, r[1].lower() in chk)
                    for r in info]
            pk = [c.name for c in sorted([c for c in cols if c.pk_pos > 0], key=lambda c: c.pk_pos)]
            tables[t] = TableMeta(t, cols, pk)
        tlow = {t.lower(): t for t in tables}
        fks: dict = {}
        for t in tnames:
            for r in con.execute('pragma foreign_key_list(%s)' % q(t)).fetchall():
                pt = tlow.get(str(r[2]).lower())
                child = next((c.name for c in tables[t].columns if c.name.lower() == str(r[3]).lower()), None)
                pcol_name = r[4] if r[4] is not None else r[3]
                pc = None
                if pt is not None:
                    pc = next((c.name for c in tables[pt].columns if c.name.lower() == str(pcol_name).lower()), None)
                if pt is None or pc is None or child is None:
                    warnings.warn('dropping dangling FK %s.%s -> %s.%s' % (t, r[3], r[2], pcol_name))
                    continue
                fks[(t, child)] = (pt, pc)
        all_cols = [(t, c.name) for t in tnames for c in tables[t].columns]
        corder, torder = process_order(fks, all_cols)
        ov, sizes = {}, {}
        for t in tnames:
            n = con.execute('select count(*) from %s' % q(t)).fetchone()[0]
            sizes[t] = n
            sel = 'select %s from %s' % (', '.join(q(c.name) for c in tables[t].columns), q(t))
            try:
                if n > max_rows_per_table:
                    k = math.ceil(n / max_rows_per_table)
                    rows = con.execute(sel + ' where rowid %% %d = 0 order by rowid' % k).fetchall()
                else:
                    rows = con.execute(sel + ' order by rowid').fetchall()
            except sqlite3.Error:
                rows = con.execute(sel + ' limit %d' % max_rows_per_table).fetchall()
            for j, c in enumerate(tables[t].columns):
                ov[(t, c.name)] = [r[j] for r in rows]
    finally:
        con.close()
    return Schema(tables, fks, ddl, torder, corder, ov, sizes, from_index)
