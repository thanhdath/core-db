"""Schema reading (upstream sql_util/dbinfo.py) + specification loading."""
import json
import math
import os
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
    unique_tuples: list = field(default_factory=list)
    spec: dict = field(default_factory=dict)
    spec_pools: dict = field(default_factory=dict)
    spec_ranges: dict = field(default_factory=dict)
    spec_enums: dict = field(default_factory=dict)
    spec_sizes: dict = field(default_factory=dict)
    spec_null: set = field(default_factory=set)
    spec_dup: dict = field(default_factory=dict)


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
    """Column and table topological levels (sql_util/dbinfo.py:122-176)."""
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


def _parse_unique_tuples(create_sql: str, low: dict) -> list:
    """Composite UNIQUE(...) / PRIMARY KEY(...) column tuples from a CREATE TABLE statement."""
    out = []
    s = create_sql.lower()
    for kw in ('unique', 'primary key'):
        i = 0
        while True:
            j = s.find(kw, i)
            if j < 0:
                break
            k = s.find('(', j)
            if k < 0:
                break
            e = s.find(')', k)
            if e < 0:
                break
            inner = s[k + 1:e]
            cols = [c.strip().strip('"`[]') for c in inner.split(',')]
            if len(cols) > 1 and all(c in low for c in cols):
                out.append(tuple(low[c] for c in cols))
            i = e + 1
    return out


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
        unique_tuples = []
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
                    elif len(cols) > 1 and all(c[2] for c in cols):
                        unique_tuples.append((t, tuple(c[2] for c in cols)))
            for tup in _parse_unique_tuples(create[t], low):
                unique_tuples.append((t, tup))
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
    return Schema(tables, fks, ddl, torder, corder, ov, sizes, from_index, unique_tuples)


_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December']


def _is_num(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _typo(s: str) -> str:
    """One-character typo variant (drop or duplicate a char)."""
    if not s:
        return s
    i = len(s) // 2
    return s[:i] + s[i + 1:] if len(s) > 1 else s + s[-1]


def _like_variants(lit: str) -> list:
    """For a LIKE literal '%X%' (or X) produce X, X+' x', typo(X), lower(X)."""
    body = lit
    if body.startswith('%'):
        body = body[1:]
    if body.endswith('%'):
        body = body[:-1]
    out = [body, body + ' x', _typo(body), body.lower(), body.upper()]
    return out


def _boundary_variants(vals: list) -> list:
    """For each literal L: L, lower(L), upper(L), one-char typo; numbers get +-1 / +-2."""
    out = []
    for v in vals:
        if _is_num(v):
            f = float(v)
            out += [f, f - 1, f + 1, f - 2, f + 2]
        else:
            s = str(v)
            out += [s, s.lower(), s.upper(), _typo(s)]
    return out


def _find_spec(root: str) -> str:
    """Locate specification.json next to the package or in the working directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, 'specification.json'),
              os.path.join(os.getcwd(), 'tscore_gen', 'specification.json'),
              os.path.join(os.getcwd(), 'specification.json')):
        if os.path.exists(p):
            return p
    return ''


def load_specification(schema: Schema, spec: dict = None) -> Schema:
    """Fill schema.spec_* from the generation specification (by construction, no SQL)."""
    if spec is None:
        p = _find_spec('')
        if p:
            with open(p) as f:
                spec = json.load(f)
        else:
            spec = {}
    schema.spec = spec or {}
    tlow = {t.lower(): t for t in schema.tables}
    clow = {(t.lower(), c.name.lower()): c.name for t in schema.tables for c in schema.tables[t].columns}

    def key(tn, cn):
        t = tlow.get(str(tn).lower())
        if t is None:
            return None
        c = clow.get((t.lower(), str(cn).lower()))
        return (t, c) if c is not None else None

    for t, n in (schema.spec.get('table_sizes_per_instance') or {}).items():
        tt = tlow.get(str(t).lower())
        if tt is not None:
            schema.spec_sizes[tt] = int(n)

    for x in schema.spec.get('null_targets') or []:
        if '.' in x:
            tn, cn = x.split('.', 1)
            k = key(tn, cn)
            if k:
                schema.spec_null.add(k)

    for exc in schema.spec.get('per_column_exceptions') or []:
        pat = exc.get('pattern')
        for col, tgt in (exc.get('targets') or {}).items():
            k = key(*col.split('.', 1)) if '.' in col else None
            if k is None:
                continue
            if pat == 'comparison_boundary' and isinstance(tgt, list):
                schema.spec_pools.setdefault(k, []).extend(_boundary_variants(tgt))
            elif pat == 'like_near_variant' and isinstance(tgt, list):
                for lit in tgt:
                    schema.spec_pools.setdefault(k, []).extend(_like_variants(lit))
            elif pat == 'duplicates_for_distinct':
                schema.spec_dup[k] = (0.20, 0.50)

    for rule in schema.spec.get('semantic_rules_and_formulas') or []:
        k = key(rule.get('table'), rule.get('column'))
        if k is None:
            continue
        f = str(rule.get('formula', ''))
        lo = f.lower()
        if 'between' in lo and ' and ' in lo:
            try:
                a, b = lo.split('between', 1)[1].split(' and ', 1)
                schema.spec_ranges[k] = (float(a.strip()), float(b.strip()))
            except Exception:
                pass
        elif ' in (' in lo:
            inner = f[f.find('(') + 1:f.rfind(')')]
            vals = [x.strip().strip("'\"") for x in inner.split(',')]
            schema.spec_enums[k] = vals
        elif '>=' in f:
            try:
                schema.spec_ranges[k] = (float(f.split('>=')[1].strip()), None)
            except Exception:
                pass
        elif '> 0' in f:
            schema.spec_ranges[k] = (1.0, None)

    for t in schema.tables:
        for c in schema.tables[t].columns:
            if c.name.lower() == 'month' and (t, c.name) not in schema.spec_enums:
                schema.spec_enums[(t, c.name)] = list(_MONTHS)
    return schema
