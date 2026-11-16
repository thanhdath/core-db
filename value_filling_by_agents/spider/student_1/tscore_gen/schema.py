"""Schema introspection of the compact database."""
import sqlite3


class ColumnMeta:
    __slots__ = ('name', 'type_str', 'notnull', 'pk_pos', 'unique', 'checked', 'default')

    def __init__(self, name, type_str='', notnull=False, pk_pos=0, unique=False,
                 checked=False, default=None):
        self.name = name
        self.type_str = type_str or ''
        self.notnull = bool(notnull)
        self.pk_pos = int(pk_pos)
        self.unique = bool(unique)
        self.checked = bool(checked)
        self.default = default

    def __repr__(self):
        return 'ColumnMeta(%r,%r,pk=%d)' % (self.name, self.type_str, self.pk_pos)


class TableMeta:
    __slots__ = ('name', 'columns', 'primary_key', 'fks', 'unique_sets')

    def __init__(self, name):
        self.name = name
        self.columns = []
        self.primary_key = []
        self.fks = {}
        self.unique_sets = []

    def col(self, name):
        for c in self.columns:
            if c.name == name:
                return c
        return None


class Schema:
    def __init__(self):
        self.tables = {}
        self.table_order = []
        self.fks = {}
        self.original_values = {}
        self.unique_indexes = []


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _parse_fk_list(s):
    """Parse '("a", "b")' or 'a' from PRAGMA foreign_key_list."""
    if s is None:
        return None
    s = str(s).strip()
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    parts = [p.strip().strip('"').strip("'") for p in s.split(',')]
    return parts


def read_schema(orig: str) -> Schema:
    """Read the compact database schema and observed values."""
    sc = Schema()
    con = sqlite3.connect(orig)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        names = [r[0] for r in cur.fetchall()]
        for t in names:
            tm = TableMeta(t)
            cur.execute('PRAGMA table_info(%s)' % _quote(t))
            info = cur.fetchall()
            pk_cols = []
            for cid, cname, ctype, notnull, dflt, pk in info:
                cm = ColumnMeta(cname, ctype, notnull=bool(notnull) or bool(pk),
                                pk_pos=int(pk or 0), default=dflt)
                tm.columns.append(cm)
                if pk:
                    pk_cols.append((int(pk), cname))
            pk_cols.sort()
            tm.primary_key = [c for _, c in pk_cols]
            cur.execute('PRAGMA foreign_key_list(%s)' % _quote(t))
            for row in cur.fetchall():
                _id, _seq, ptable, frm, to = row[0], row[1], row[2], row[3], row[4]
                if frm is None:
                    continue
                if to is None:
                    to = frm
                tm.fks[frm] = (ptable, to)
                sc.fks[(t, frm)] = (ptable, to)
            cur.execute('PRAGMA index_list(%s)' % _quote(t))
            for irow in cur.fetchall():
                iname, uniq = irow[1], irow[2]
                if not uniq:
                    continue
                cur.execute('PRAGMA index_info(%s)' % _quote(iname))
                cols = [r[2] for r in cur.fetchall()]
                if not cols:
                    continue
                if len(cols) == 1:
                    cm = tm.col(cols[0])
                    if cm is not None:
                        cm.unique = True
                tm.unique_sets.append(tuple(cols))
                sc.unique_indexes.append((t, tuple(cols)))
            sc.tables[t] = tm
        remaining = set(sc.tables)
        order = []
        while remaining:
            level = []
            for t in list(remaining):
                parents = {pt for (pt, _pc) in sc.tables[t].fks.values() if pt in remaining and pt != t}
                if not parents:
                    level.append(t)
            if not level:
                level = [sorted(remaining)[0]]
            for t in level:
                remaining.discard(t)
            order.append(sorted(level))
        sc.table_order = order
        for t, tm in sc.tables.items():
            try:
                cur.execute('SELECT * FROM %s' % _quote(t))
                rows = cur.fetchall()
            except Exception:
                rows = []
            colnames = [d[0] for d in cur.description] if cur.description else [c.name for c in tm.columns]
            for j, cname in enumerate(colnames):
                vals = []
                seen = set()
                for r in rows:
                    v = r[j]
                    if v is None:
                        continue
                    key = (type(v).__name__, v)
                    if key in seen:
                        continue
                    seen.add(key)
                    vals.append(v)
                sc.original_values[(t, cname)] = vals
    finally:
        con.close()
    return sc
