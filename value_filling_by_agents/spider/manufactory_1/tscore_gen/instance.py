"""Append-only instance construction (spec-driven, over the compact DB copy)."""
from . import spec
from .values import make_column_sampler


def _is_primary_key(col):
    return col.pk_pos > 0


def _is_foreign_key(schema, col):
    return (col.table, col.name) in schema.fks


def _compact_share(schema, table, column):
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _append_count(schema, table):
    """Number of genuinely new rows: target total minus compact rows (>= 0)."""
    target = spec.TABLE_SIZES.get(table, 0)
    compact = schema.original_sizes.get(table, 0)
    return max(0, target - compact)


def _fresh_primary_key(schema, table, existing, n, rng):
    """Sequential primary keys: the next integer after the largest existing value."""
    pk = schema.tables[table].primary_key
    if len(pk) != 1:
        return None
    col = pk[0]
    vals = [v for v in existing.get(col, []) if isinstance(v, (int, float))]
    start = int(max(vals)) + 1 if vals else 1
    return [start + i for i in range(n)]


def _build_numeric_prefix(boundaries, tie_min, tie_max):
    """Deterministic prefix: every boundary once, plus TIE_MIN copies of the min and TIE_MAX copies of the max
    (ties_for_order_limit rank 1)."""
    prefix = []
    if boundaries:
        prefix.extend(boundaries)
        gmin = min(boundaries)
        gmax = max(boundaries)
        prefix.extend([gmin] * tie_min)
        prefix.extend([gmax] * tie_max)
    return prefix


def _sample_numeric(schema, table, col, rng, n):
    """Numeric column: deterministic prefix (boundaries + ties) first, then uniform fill."""
    key = (table, col.name)
    lo, hi, is_int, _ = spec.RANGES.get(key, (0, 100, True, 1))
    boundaries = list(spec.BOUNDARIES.get(key, []))
    prefix = _build_numeric_prefix(boundaries, spec.TIE_MIN, spec.TIE_MAX)
    if len(prefix) > n:
        ties = []
        if boundaries:
            ties = [min(boundaries)] * spec.TIE_MIN + [max(boundaries)] * spec.TIE_MAX
        prefix = (ties + boundaries)[:n]
    out = list(prefix)
    while len(out) < n:
        if is_int:
            out.append(rng.randint(int(lo), int(hi)))
        else:
            out.append(rng.uniform(lo, hi))
    rng.shuffle(out)
    return out


def _sample_string(schema, table, col, rng, n):
    """VARCHAR column: base literal + every near-variant at least once, then pool fill."""
    key = (table, col.name)
    base = list(spec.VALUE_POOLS.get(key, []))
    variants = list(spec.LIKE_VARIANTS.get(key, []))
    out = []
    if base:
        out.append(base[0])
    for v in variants:
        if len(out) < n:
            out.append(v)
    pool = base + variants if variants else base
    while len(out) < n:
        if pool:
            out.append(rng.choice(pool))
        else:
            out.append('')
    out = out[:n]
    rng.shuffle(out)
    return out


def _sample_column(schema, table, col, rng, n, pool, compact):
    """Generate n values for one column (non-PK, non-FK)."""
    key = (table, col.name)
    if key in spec.RANGES:
        return _sample_numeric(schema, table, col, rng, n)
    if key in spec.VALUE_POOLS or key in spec.LIKE_VARIANTS:
        return _sample_string(schema, table, col, rng, n)
    s = make_column_sampler(col, list(pool.get(key, [])), 0.2, 1e9, rng)
    return [s.sample() for _ in range(n)]


def _apply_null_rule(schema, table, col, values, rng):
    """Apply the NULL rule to a nullable column (at least one NULL, share follows compact)."""
    key = (table, col.name)
    if key not in spec.NULLABLE:
        return values
    share = _compact_share(schema, table, col.name)
    n = len(values)
    if n == 0:
        return values
    n_null = max(1, int(round(share * n)))
    n_null = min(n_null, n)
    idx = rng.sample(range(n), n_null)
    for i in idx:
        values[i] = None
    return values


def _apply_fresh_share(schema, table, col, values, rng):
    """Inject fresh in-domain values on DISTINCT-targeted columns (20-50% share)."""
    key = (table, col.name)
    if key not in spec.DISTINCT_COLUMNS:
        return values
    n = len(values)
    if n == 0:
        return values
    lo, hi = spec.FRESH_SHARE
    n_fresh = max(1, int(round(rng.uniform(lo, hi) * n)))
    n_fresh = min(n_fresh, n)
    fresh_pool = spec.FRESH_STRINGS.get(key)
    for i in rng.sample(range(n), n_fresh):
        v = values[i]
        if fresh_pool:
            values[i] = rng.choice(fresh_pool)
        elif isinstance(v, str):
            pool = spec.VALUE_POOLS.get(key, [])
            if pool:
                values[i] = rng.choice(pool)
    return values


def _sample_fk(schema, table, col, parent_vals, n, rng):
    """Draw n FK values from the parent's rows (compact + generated)."""
    if not parent_vals:
        raise ValueError('no parent values for FK %s.%s' % (table, col.name))
    out = []
    if n >= len(parent_vals):
        out.extend(parent_vals)
        while len(out) < n:
            out.append(rng.choice(parent_vals))
    else:
        chosen = rng.sample(parent_vals, n)
        out.extend(chosen)
    rng.shuffle(out)
    return out


def build_instance(schema, literal_pool, rng):
    """Build the instance dict of *new* rows: {table: {column: [values]}}."""
    instance = {}
    order = [t for lvl in schema.table_order for t in lvl]
    for t in order:
        tm = schema.tables[t]
        cols = schema.original_values
        n = _append_count(schema, t)
        table_cols = {}
        pk = tm.primary_key
        if len(pk) == 1:
            new_pk = _fresh_primary_key(schema, t, {pk[0]: list(cols.get((t, pk[0]), []))}, n, rng)
            table_cols[pk[0]] = new_pk
        for c in tm.columns:
            if (t, c.name) in schema.fks:
                pt, pc = schema.fks[(t, c.name)]
                parent_vals = list(instance.get(pt, {}).get(pc, []))
                parent_vals += [v for v in cols.get((pt, pc), []) if v is not None]
                seen = set()
                parent_vals = [v for v in parent_vals if not (v in seen or seen.add(v))]
                table_cols[c.name] = _sample_fk(schema, t, c, parent_vals, n, rng)
        for c in tm.columns:
            if _is_primary_key(c) or _is_foreign_key(schema, c):
                continue
            new = _sample_column(schema, t, c, rng, n, literal_pool, table_cols)
            new = _apply_null_rule(schema, t, c, new, rng)
            new = _apply_fresh_share(schema, t, c, new, rng)
            table_cols[c.name] = new
        instance[t] = table_cols
    return instance
