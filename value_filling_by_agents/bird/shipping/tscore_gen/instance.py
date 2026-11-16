"""Instance construction: sample rows table by table, resolve dependencies in memory."""
import random

from .values import _init_sampler, spec_column_values, _date_range_from_formula


def _compact_null_share(schema, table, column):
    vals = schema.original_values.get(table, {}).get(column, [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / float(len(vals))


def _fresh_pk_values(schema, table, column, n, rng, type_str):
    """Draw n fresh PK values not present in the compact rows or in already generated rows."""
    existing = set(v for v in schema.original_values.get(table, {}).get(column, []) if v is not None)
    is_int = 'int' in (type_str or '').lower()
    if is_int:
        lo = (max(existing) + 1) if existing else 1
        return [lo + i for i in range(n)]
    tag = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(4))
    return ['%s_%d' % (tag, i) for i in range(n)]


def _choose_table_sizes(spec, rng):
    sizes = {}
    for t, base in (spec.get('sizes') or {}).items():
        sizes[t] = max(0, int(base + rng.randint(-2, 2)))
    return sizes


def _parent_rows(schema, table):
    """Return the compact parent rows as a list of dicts (kept in memory for lookups)."""
    tm = schema.tables[table]
    cols = schema.original_values.get(table, {})
    n = schema.row_counts.get(table, 0)
    rows = []
    for i in range(n):
        rows.append({c.name: cols.get(c.name, [None] * n)[i] for c in tm.columns})
    return rows


def _pool_for_column(spec, table, column):
    """Literal pool routed to (table, COLUMN) or (None, COLUMN)."""
    pool = spec.get('literal_pool') or {}
    out = list(pool.get((table, column), []))
    out += list(pool.get((None, column.upper()), []))
    return out


def _build_table(schema, spec, table, n, rng, generated, violations):
    """Sample n rows for one table; dependent columns are resolved from generated parents."""
    tm = schema.tables[table]
    cols = {}
    for cm in tm.columns:
        spec_col = spec['columns'].get((table, cm.name), {})
        original = schema.original_values.get(table, {}).get(cm.name, [])
        compact_share = _compact_null_share(schema, table, cm.name)
        is_null_target = (table, cm.name) in spec.get('null_targets', set())
        if cm.pk_pos > 0:
            vals = _fresh_pk_values(schema, table, cm.name, n, rng, cm.type_str)
        else:
            date_range = _date_range_from_formula(spec_col, cm.type_str)
            literal_pool = _pool_for_column(spec, table, cm.name)
            sampler = _init_sampler(cm, literal_pool, original, 0.2, rng, 0, date_range=date_range)
            vals = spec_column_values(cm, spec_col, n, rng, sampler, original,
                                      is_null_target=is_null_target,
                                      compact_null_share=compact_share)
            formula = spec_col.get('formula')
            if formula is not None:
                bad = sum(1 for v in vals if v is not None and not formula(v))
                if bad:
                    violations[(table, cm.name)] = violations.get((table, cm.name), 0) + bad
        cols[cm.name] = vals
    return cols


def _fill_foreign_keys(schema, spec, table, cols, n, rng, generated):
    """Resolve FK columns from generated parent rows (kept in memory)."""
    for fk in schema.foreign_keys:
        if fk['child'] != table:
            continue
        child_col = fk['child_column']
        parent = fk['parent']
        parent_col = fk['parent_column']
        parent_rows = generated.get(parent)
        if not parent_rows:
            continue
        parent_vals = [r[parent_col] for r in parent_rows if r.get(parent_col) is not None]
        if not parent_vals:
            continue
        is_null_target = (table, child_col) in spec.get('null_targets', set())
        compact_share = _compact_null_share(schema, table, child_col)
        if is_null_target:
            share = compact_share if compact_share > 0 else 0.1
        else:
            share = compact_share
        n_null = int(round(n * share))
        if is_null_target and n_null == 0 and n > 0:
            n_null = 1
        n_null = min(n_null, n)
        idx = list(range(n))
        rng.shuffle(idx)
        null_set = set(idx[:n_null])
        vals = []
        for i in range(n):
            if i in null_set:
                vals.append(None)
            else:
                vals.append(rng.choice(parent_vals))
        cols[child_col] = vals


def build_random_instance(schema, spec, rng: random.Random) -> dict:
    """Build one instance: sample rows table by table, resolving dependencies in memory."""
    sizes = _choose_table_sizes(spec, rng)
    generated = {}
    violations = {}
    order = _topological_order(schema)
    for table in order:
        n = sizes.get(table, 0)
        cols = _build_table(schema, spec, table, n, rng, generated, violations)
        _fill_foreign_keys(schema, spec, table, cols, n, rng, generated)
        generated[table] = _rows_from_cols(schema.tables[table], cols, n)
    out = {t: _cols_from_rows(schema.tables[t], generated[t]) for t in generated}
    out['__violations__'] = violations
    return out


def _rows_from_cols(tm, cols, n):
    rows = []
    for i in range(n):
        rows.append({c.name: cols.get(c.name, [None] * n)[i] for c in tm.columns})
    return rows


def _cols_from_rows(tm, rows):
    cols = {c.name: [] for c in tm.columns}
    for r in rows:
        for c in tm.columns:
            cols[c.name].append(r.get(c.name))
    return cols


def _topological_order(schema):
    """Order tables so that parents precede children."""
    tables = list(schema.tables.keys())
    deps = {t: set() for t in tables}
    for fk in schema.foreign_keys:
        if fk['parent'] in deps and fk['child'] in deps and fk['parent'] != fk['child']:
            deps[fk['child']].add(fk['parent'])
    order = []
    seen = set()
    while len(order) < len(tables):
        progressed = False
        for t in tables:
            if t in seen:
                continue
            if deps[t] <= seen:
                order.append(t)
                seen.add(t)
                progressed = True
        if not progressed:
            for t in tables:
                if t not in seen:
                    order.append(t)
                    seen.add(t)
            break
    return order
