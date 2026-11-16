"""Schema introspection for the compact database (sqlite3)."""
import sqlite3


def q(name: str) -> str:
    """Quote an identifier for SQLite."""
    return '"%s"' % str(name).replace('"', '""')


class ColumnMeta:
    __slots__ = ('name', 'type_str', 'notnull', 'pk_pos', 'table')

    def __init__(self, name, type_str, notnull, pk_pos, table):
        self.name = name
        self.type_str = type_str or ''
        self.notnull = bool(notnull)
        self.pk_pos = int(pk_pos or 0)
        self.table = table

    @property
    def checked(self):
        return self.pk_pos > 0 or self.notnull

    def __repr__(self):
        return 'ColumnMeta(%s.%s %s)' % (self.table, self.name, self.type_str)


class TableMeta:
    def __init__(self, name):
        self.name = name
        self.columns = []
        self.column_names = []
        self.pk = []

    def col(self, name):
        for c in self.columns:
            if c.name == name:
                return c
        return None


class Schema:
    def __init__(self):
        self.tables = {}
        self.ddl = []
        self.original_values = {}
        self.row_counts = {}
        self.foreign_keys = []
        self.fks = {}

    def table(self, name):
        return self.tables.get(name)


def _read_original_values(con, schema):
    for t, tm in schema.tables.items():
        cols = {}
        for c in tm.columns:
            cols[c.name] = []
        try:
            cur = con.execute('SELECT %s FROM %s' % (','.join(q(c.name) for c in tm.columns), q(t)))
        except sqlite3.Error:
            schema.original_values[t] = cols
            schema.row_counts[t] = 0
            continue
        n = 0
        for row in cur:
            n += 1
            for c, v in zip(tm.columns, row):
                cols[c.name].append(v)
        schema.original_values[t] = cols
        schema.row_counts[t] = n


def load_schema(path: str) -> Schema:
    """Read tables, columns, PKs, FKs and original values from the compact database."""
    schema = Schema()
    con = sqlite3.connect(path)
    try:
        for (name, sql) in con.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            tm = TableMeta(name)
            schema.tables[name] = tm
            if sql:
                schema.ddl.append(sql)
            for cid, cname, ctype, notnull, dflt, pk in con.execute('PRAGMA table_info(%s)' % q(name)):
                cm = ColumnMeta(cname, ctype, notnull, pk, name)
                tm.columns.append(cm)
                tm.column_names.append(cname)
                if pk:
                    tm.pk.append(cname)
            for fk in con.execute('PRAGMA foreign_key_list(%s)' % q(name)):
                schema.foreign_keys.append({
                    'child': name, 'child_column': fk[3], 'parent': fk[2], 'parent_column': fk[4],
                })
                schema.fks[(name, fk[3])] = (fk[2], fk[4])
        _read_original_values(con, schema)
    finally:
        con.close()
    return schema
