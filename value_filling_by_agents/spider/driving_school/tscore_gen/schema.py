"""Schema reading: column types, PKs, FKs (inline refs), UNIQUE (incl. composite/index), CHECK."""
import re
import sqlite3


def q(name: str) -> str:
    """Quote an identifier."""
    return '"%s"' % name.replace('"', '""')


class Column:
    def __init__(self, table, name, type_str, notnull, pk_pos):
        self.table = table
        self.name = name
        self.type_str = type_str or ''
        self.notnull = notnull
        self.pk_pos = pk_pos
        self.checked = False

    @property
    def nullable(self):
        return not self.notnull and self.pk_pos == 0


class Table:
    def __init__(self, name):
        self.name = name
        self.columns = []
        self.pk = []
        self.fks = []
        self.uniques = []
        self.checks = []

    def col(self, name):
        for c in self.columns:
            if c.name == name:
                return c
        return None


class Schema:
    def __init__(self):
        self.tables = {}
        self.ddl = []
        self.order = []


def _split_defs(body: str):
    """Split a CREATE TABLE body on top-level commas."""
    out, depth, cur = [], 0, []
    for ch in body:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append(''.join(cur).strip())
    return [d for d in out if d]


def _parse_create(sql: str, schema: Schema):
    m = re.search(r'CREATE\s+TABLE\s+[`"\[]?(\w+)[`"\]]?\s*\((.*)\)\s*$', sql, re.S | re.I)
    if not m:
        return
    tname, body = m.group(1), m.group(2)
    t = Table(tname)
    pk_cols = []
    for d in _split_defs(body):
        up = d.upper()
        if up.startswith('PRIMARY KEY'):
            cm = re.search(r'\((.*?)\)', d)
            if cm:
                pk_cols = [x.strip().strip('`"[]') for x in cm.group(1).split(',')]
            continue
        if up.startswith('FOREIGN KEY'):
            cm = re.search(r'\((.*?)\)\s*REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(?(.*?)\)?$', d, re.I)
            if cm:
                child = cm.group(1).strip().strip('`"[]')
                pt = cm.group(2)
                pc = cm.group(3).strip().strip('`"[]') or child
                t.fks.append((child, pt, pc))
            continue
        if up.startswith('UNIQUE'):
            cm = re.search(r'\((.*?)\)', d)
            if cm:
                t.uniques.append(tuple(x.strip().strip('`"[]') for x in cm.group(1).split(',')))
            continue
        if up.startswith('CHECK'):
            t.checks.append(d)
            continue
        cm = re.match(r'[`"\[]?(\w+)[`"\]]?\s+([A-Za-z0-9_()]+)(.*)$', d, re.S)
        if not cm:
            continue
        name, typ, rest = cm.group(1), cm.group(2), cm.group(3)
        notnull = bool(re.search(r'\bNOT\s+NULL\b', rest, re.I))
        is_pk = bool(re.search(r'\bPRIMARY\s+KEY\b', rest, re.I))
        col = Column(tname, name, typ, notnull, 0)
        if is_pk:
            pk_cols = [name]
        if re.search(r'\bUNIQUE\b', rest, re.I):
            t.uniques.append((name,))
        if re.search(r'\bCHECK\b', rest, re.I):
            t.checks.append(rest)
        t.columns.append(col)
    for i, cn in enumerate(pk_cols):
        c = t.col(cn)
        if c:
            c.pk_pos = i + 1
            c.notnull = True
    t.pk = pk_cols
    schema.tables[tname] = t


def _parse_index(sql: str, schema: Schema):
    m = re.search(r'CREATE\s+UNIQUE\s+INDEX\s+\S+\s+ON\s+[`"\[]?(\w+)[`"\]]?\s*\((.*?)\)', sql, re.I)
    if m:
        t = schema.tables.get(m.group(1))
        if t:
            cols = tuple(x.strip().strip('`"[]').split()[0] for x in m.group(2).split(','))
            t.uniques.append(cols)


def _fk_order(schema: Schema):
    """Topological order of tables by FK dependencies."""
    deps = {t: set() for t in schema.tables}
    for tn, t in schema.tables.items():
        for (_c, pt, _p) in t.fks:
            if pt in schema.tables and pt != tn:
                deps[tn].add(pt)
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for d in deps.get(n, ()):
            visit(d)
        order.append(n)

    for n in schema.tables:
        visit(n)
    schema.order = order


def read_schema(path: str) -> Schema:
    """Read schema from a compact sqlite database."""
    schema = Schema()
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL").fetchall()
        for (sql,) in rows:
            if sql and sql.strip().upper().startswith('CREATE TABLE'):
                _parse_create(sql, schema)
                schema.ddl.append(sql)
        idx = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
        for (sql,) in idx:
            _parse_index(sql, schema)
    finally:
        con.close()
    _fk_order(schema)
    return schema
