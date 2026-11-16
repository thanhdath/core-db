"""Random instance construction (fuzz/fuzz.py:83-196), adapted for compact-DB copy + append."""
import datetime as dt

from .specification import (AGGREGATE_BOUNDARY, BOUNDARY_LITERALS, DUPLICATE_SHARE, ENUM_POOLS,
                            GROUP_SIZE_TARGETS, NULLABLE, TABLE_SIZES, TIE_TARGETS, row_rule_ok)
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _next_int_pk(schema, table):
    """Next integer PK value above the compact max (fresh against compact rows)."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) != 1:
        return 1
    col = next(c for c in tm.columns if c.name == pk[0])
    if 'int' not in (col.type_str or '').lower():
        return 1
    vals = [v for v in schema.original_values.get((table, pk[0]), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _next_char_pk(schema, table, n):
    """Fresh CHAR PK values above the compact max (numeric suffix bump) for reference tables."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) != 1:
        return None
    col = next(c for c in tm.columns if c.name == pk[0])
    if 'char' not in (col.type_str or '').lower() and 'text' not in (col.type_str or '').lower():
        return None
    existing = [str(v) for v in schema.original_values.get((table, pk[0]), []) if v is not None]
    max_num = 0
    prefix = 'Z'
    for v in existing:
        i = len(v)
        while i > 0 and v[i - 1].isdigit():
            i -= 1
        if i < len(v):
            try:
                max_num = max(max_num, int(v[i:]))
                prefix = v[:i] or 'Z'
            except ValueError:
                pass
    out = []
    for k in range(n):
        out.append('%s%d' % (prefix, max_num + 1 + k))
    return out


def _parent_key_pool(schema, instance, pt, pc):
    """Parent key pool = compact values + generated values held in memory."""
    pool = list(schema.original_values.get((pt, pc), []))
    gen = instance.get(pt, {}).get(pc, [])
    pool.extend([v for v in gen if v is not None])
    return pool


def _null_share_for(schema, col_key):
    """Derive the NULL share from the compact DB's actual null_rate for this column."""
    vals = schema.original_values.get(col_key, [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / float(len(vals))


def _apply_boundary(rng, col_key, values):
    """Plant boundary literals (case variants) into a sample of values."""
    lits = BOUNDARY_LITERALS.get(col_key)
    if not lits or not values:
        return values
    n = len(values)
    k = max(1, n // 4)
    for j in range(k):
        idx = rng.randrange(n)
        values[idx] = rng.choice(lits)
    return values


def _apply_duplicates(rng, col_key, values, is_pk=False):
    """Plant near-duplicate variants (20-50% share) on DISTINCT-targeted non-PK columns."""
    if is_pk:
        return values
    share = DUPLICATE_SHARE.get(col_key)
    if share is None or len(values) < 2:
        return values
    n = len(values)
    k = max(1, int(n * share))
    for _ in range(k):
        src = rng.randrange(n)
        dst = rng.randrange(n)
        v = values[src]
        if v is None:
            continue
        u = rng.random()
        if isinstance(v, str):
            if u < 0.4:
                values[dst] = v.upper() if v.lower() == v else v.lower()
            elif u < 0.7:
                values[dst] = v + ' '
            else:
                values[dst] = ' ' + v
        else:
            values[dst] = v
    return values


def _apply_ties(rng, col_key, values):
    """Plant >=2 rows sharing rank-1 value for ORDER-targeted columns."""
    if not TIE_TARGETS.get(col_key) or len(values) < 2:
        return values
    v = values[0]
    values[1] = v
    return values


def _apply_group_and_aggregate(rng, col_key, values):
    """Jointly shape group sizes {1,2,>=3} and aggregate counts {2,3,4} on one column."""
    g_targets = GROUP_SIZE_TARGETS.get(col_key)
    a_targets = AGGREGATE_BOUNDARY.get(col_key)
    if not g_targets and not a_targets:
        return values
    distinct = list(dict.fromkeys([v for v in values if v is not None]))
    if not distinct:
        return values
    n = len(values)
    out = []
    if a_targets:
        for t in a_targets:
            v = rng.choice(distinct)
            out.extend([v] * t)
    if g_targets:
        for t in g_targets:
            v = rng.choice(distinct)
            size = t if t < 3 else 3
            out.extend([v] * size)
    while len(out) < n:
        out.append(rng.choice(distinct))
    rng.shuffle(out)
    return out[:n]


def _apply_nulls(rng, col_key, values, schema):
    """NULL rule: at least one NULL row per nullable column; share follows compact null_rate."""
    if col_key not in NULLABLE:
        return values
    share = _null_share_for(schema, col_key)
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idxs = list(range(n))
    rng.shuffle(idxs)
    for j in idxs[:k]:
        values[j] = None
    return values


def _apply_enum(rng, col_key, values):
    """Force enum columns to draw from the enum pool (case-insensitive check)."""
    pool = ENUM_POOLS.get(col_key[1])
    if pool is None:
        return values
    pool_upper = {str(p).upper() for p in pool}
    for i, v in enumerate(values):
        if v is None:
            continue
        if str(v).upper() not in pool_upper:
            values[i] = rng.choice(pool)
    return values


def _apply_semantic_rules(table, columns):
    """Replace values failing row-level rules with a valid alternative."""
    n = len(next(iter(columns.values()))) if columns else 0
    for i in range(n):
        row = {c: columns[c][i] for c in columns}
        if row_rule_ok(table, row):
            continue
        for (t, c), pred in _rules_for(table):
            if c in row and row[c] is not None and not pred(row[c]):
                cands = [v for v in columns[c] if v is not None and pred(v)]
                if cands:
                    columns[c][i] = cands[0]
    return columns


def _rules_for(table):
    from .specification import SEMANTIC_RULES
    return [(k, p) for k, p in SEMANTIC_RULES.items() if k[0] == table]


def _fix_date_order(table, columns):
    """Enforce Date_in_Locaton_To >= Date_in_Location_From and Actual >= Planned."""
    n = len(next(iter(columns.values()))) if columns else 0
    if table == 'Document_Locations':
        for i in range(n):
            f = columns.get('Date_in_Location_From', [None] * n)[i]
            to = columns.get('Date_in_Locaton_To', [None] * n)[i]
            if f is not None and to is not None and str(to) < str(f):
                columns['Date_in_Locaton_To'][i] = f
    if table == 'Documents_to_be_Destroyed':
        for i in range(n):
            p = columns.get('Planned_Destruction_Date', [None] * n)[i]
            a = columns.get('Actual_Destruction_Date', [None] * n)[i]
            if p is not None and a is not None and str(a) < str(p):
                columns['Actual_Destruction_Date'][i] = p
    return columns


def sample_fresh_primary_keys(table_meta, columns: dict, compact_keys: list) -> dict:
    """Drop rows whose PK tuple repeats a compact key or an earlier generated key."""
    if not table_meta.primary_key or not columns:
        return columns
    seen = set(compact_keys)
    n = len(next(iter(columns.values())))
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's key pool (compact + generated); empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_key_pool(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Use the specification's table sizes per instance."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = TABLE_SIZES.get(t, 0)
    return sizes


def _build_table(schema, instance, table, n, samplers, rng):
    """Build one table's columns with all spec rules applied."""
    tm = schema.tables[table]
    cols = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks:
            continue
        s = samplers.get(key)
        if s is None:
            continue
        vals = [s.sample() for _ in range(n)]
        col_key = (table, cm.name)
        vals = _apply_enum(rng, col_key, vals)
        vals = _apply_boundary(rng, col_key, vals)
        vals = _apply_duplicates(rng, col_key, vals, is_pk=(cm.pk_pos > 0))
        vals = _apply_ties(rng, col_key, vals)
        vals = _apply_group_and_aggregate(rng, col_key, vals)
        vals = _apply_nulls(rng, col_key, vals, schema)
        cols[cm.name] = vals
    if len(tm.primary_key) == 1:
        pk = tm.primary_key[0]
        col = next(c for c in tm.columns if c.name == pk)
        if 'int' in (col.type_str or '').lower() and pk in cols:
            start = _next_int_pk(schema, table)
            cols[pk] = list(range(start, start + n))
        else:
            fresh = _next_char_pk(schema, table, n)
            if fresh is not None and pk in cols:
                cols[pk] = fresh
    fk_cols = fill_foreign_keys_consistently(instance, schema, table, n, rng)
    cols.update(fk_cols)
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks and key in NULLABLE:
            cols[cm.name] = _apply_nulls(rng, key, cols[cm.name], schema)
    cols = _apply_semantic_rules(table, cols)
    cols = _fix_date_order(table, cols)
    cols = sample_fresh_primary_keys(tm, cols, schema.compact_keys.get(table, []))
    cols = drop_unique_duplicates(tm, cols)
    for cm in tm.columns:
        pt, pc = schema.fks.get((table, cm.name), (None, None))
        if pt == table and pc in cols:
            final = cols[pc]
            fs = set(final)
            cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                             for v in cols[cm.name]]
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), appended to compact rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        n = int(size.get(t, 0))
        inst[t] = _build_table(schema, inst, t, n, samplers, rng)
    return {t: inst[t] for t in schema.tables}
