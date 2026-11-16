"""Schema reading: column types, primary keys, foreign keys, UNIQUE, CHECK, DDL."""
import re
import sqlite3


def q(name: str) -> str:
    """Quote an identifier."""
    return '"%s"' % name.replace('"', '""')


class ColumnMeta:
    """One column's metadata."""

    def __init__(self, name, type_str, notnull, pk_pos, unique, default, checked):
        self.name = name
        self.type_str = type_str or ''
        self.notnull = notnull
        self.pk_pos = pk_pos
        self.unique = unique
        self.default = default
        self.checked = checked

    def __repr__(self):
        return 'ColumnMeta(%r,%r,pk=%d,uniq=%r)' % (self.name, self.type_str, self.pk_pos, self.unique)


class TableMeta:
    """One table's metadata."""

    def __init__(self, name):
        self.name = name
        self.columns = []
        self.primary_key = []
        self.uniques = []
        self.checks = []
        self.ddl = ''

    def col(self, name):
        for c in self.columns:
            if c.name == name:
                return c
        return None


class Schema:
    """Whole schema: tables, foreign keys, table order, original values."""

    def __init__(self):
        self.tables = {}
        self.fks = {}
        self.table_order = []
        self.ddl = []
        self.original_values = {}


def _parse_create(sql: str):
    """Parse a CREATE TABLE statement into TableMeta (best-effort, regex-based)."""
    m = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`"\[]?)(\w+)\1\s*\((.*)\)\s*;?\s*$',
                  sql, re.S | re.I)
    if not m:
        return None
    tname = m.group(2)
    body = m.group(3)
    tm = TableMeta(tname)
    tm.ddl = sql
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    pk_cols = []
    for part in parts:
        low = part.lower()
        if low.startswith('primary key'):
            mm = re.search(r'\(([^)]*)\)', part)
            if mm:
                pk_cols = [c.strip().strip('`"[]') for c in mm.group(1).split(',')]
            continue
        if low.startswith('unique'):
            mm = re.search(r'\(([^)]*)\)', part)
            if mm:
                tm.uniques.append(tuple(c.strip().strip('`"[]') for c in mm.group(1).split(',')))
            continue
        if low.startswith('check'):
            tm.checks.append(part)
            continue
        if low.startswith('foreign key') or low.startswith('constraint'):
            continue
        cm = re.match(r'([`"\[]?)(\w+)\1\s+([A-Za-z0-9_() ]*?)(?:\s+(.*))?$', part, re.S)
        if not cm:
            continue
        cname = cm.group(2)
        ctype = (cm.group(3) or '').strip()
        rest = (cm.group(4) or '').lower()
        notnull = 'not null' in rest
        pk_pos = 0
        if 'primary key' in rest:
            pk_pos = 1
            pk_cols = [cname]
        unique = 'unique' in rest
        checked = 'check' in rest
        default = None
        dm = re.search(r'default\s+(\S+)', rest)
        if dm:
            default = dm.group(1)
        tm.columns.append(ColumnMeta(cname, ctype, notnull, pk_pos, unique, default, checked))
    for c in tm.columns:
        if c.name in pk_cols:
            c.pk_pos = pk_cols.index(c.name) + 1
            c.notnull = True
    tm.primary_key = pk_cols
    return tm


def _read_fks(con, tname):
    """Read foreign keys via PRAGMA foreign_key_list; inline refs name the parent's same-name col."""
    out = []
    try:
        rows = con.execute('PRAGMA foreign_key_list(%s)' % q(tname)).fetchall()
    except sqlite3.Error:
        return out
    for r in rows:
        parent, frm, to = r[2], r[3], r[4]
        if to is None:
            to = frm
        out.append((frm, parent, to))
    return out


def _read_unique_indexes(con, tname):
    """Read CREATE UNIQUE INDEX constraints."""
    out = []
    try:
        rows = con.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                           (tname,)).fetchall()
    except sqlite3.Error:
        return out
    for name, sql in rows:
        if 'unique' in (sql or '').lower():
            mm = re.search(r'\(([^)]*)\)', sql)
            if mm:
                out.append(tuple(c.strip().strip('`"[]') for c in mm.group(1).split(',')))
    return out


def _read_original_values(con, schema):
    """Read compact rows into original_values[(table, col)] -> list."""
    for t, tm in schema.tables.items():
        try:
            rows = con.execute('SELECT %s FROM %s' % (','.join(q(c.name) for c in tm.columns), q(t))).fetchall()
        except sqlite3.Error:
            rows = []
        for j, cm in enumerate(tm.columns):
            schema.original_values[(t, cm.name)] = [r[j] for r in rows]


def _topo_order(schema):
    """Order tables by FK dependency (parents first); cycles broken by name."""
    deps = {t: set() for t in schema.tables}
    for (t, _c), (pt, _pc) in schema.fks.items():
        if t != pt:
            deps[t].add(pt)
    order, done = [], set()
    remaining = set(schema.tables)
    while remaining:
        ready = sorted(t for t in remaining if deps[t] <= done)
        if not ready:
            ready = sorted(remaining)
        order.append(ready)
        done |= set(ready)
        remaining -= set(ready)
    return order


def read_schema(path: str) -> Schema:
    """Read the compact database's schema and original values."""
    schema = Schema()
    con = sqlite3.connect(path)
    try:
        rows = con.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for name, sql in rows:
            tm = _parse_create(sql or '')
            if tm is None:
                tm = TableMeta(name)
                tm.ddl = sql or ''
                try:
                    for r in con.execute('PRAGMA table_info(%s)' % q(name)).fetchall():
                        tm.columns.append(ColumnMeta(r[1], r[2], bool(r[3]), r[5], False, r[4], False))
                        if r[5]:
                            tm.primary_key.append(r[1])
                except sqlite3.Error:
                    pass
            schema.tables[name] = tm
            schema.ddl.append(sql or '')
        for t, tm in schema.tables.items():
            for frm, parent, to in _read_fks(con, t):
                schema.fks[(t, frm)] = (parent, to)
            for u in _read_unique_indexes(con, t):
                if u not in tm.uniques:
                    tm.uniques.append(u)
        _read_original_values(con, schema)
    finally:
        con.close()
    schema.table_order = _topo_order(schema)
    return schema
