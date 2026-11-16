"""Random instance construction (fuzz/fuzz.py:83-196), adapted to append to a compact database."""
from . import specification as S
from .values import spec_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_key_column(schema, table: str, column: str) -> bool:
    """True for primary-key or foreign-key columns (exempt from duplicate/tie/group planting)."""
    tm = schema.tables.get(table)
    if tm is not None and column in tm.primary_key:
        return True
    return (table, column) in schema.fks


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """All parent key values (compact + generated) for FK lookups."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes, jittered per instance (0-230 rows or level x4 up to 2500)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = S.TABLE_SIZES.get(t)
            if base is None:
                base = int(30 * rng.random() + rng.random() * 200)
            jitter = rng.randint(-max(1, base // 10), max(1, base // 10))
            sizes[t] = max(0, min(2500, base + jitter))
    return sizes


def _plant_nulls(table: str, column: str, values: list, rng) -> list:
    """NULL rule: plant NULL in a share of generated rows (at least one) for nullable columns."""
    share = S.NULL_SHARE.get((table, column))
    if share is None or not values:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _plant_duplicates(table: str, column: str, values: list, rng) -> list:
    """duplicates_for_distinct: repeat 20-50% of values so COUNT(col) < COUNT(DISTINCT col)."""
    if (table, column) not in S.DISTINCT_COLUMNS or len(values) < 3:
        return values
    n = len(values)
    k = max(1, int(round(rng.uniform(0.2, 0.5) * n)))
    out = list(values)
    for _ in range(k):
        i = rng.randrange(n)
        j = rng.randrange(n)
        if out[j] is not None:
            out[i] = out[j]
    return out


def _plant_ties(table: str, column: str, values: list, rng) -> list:
    """ties_for_order_limit: at least two rows share the rank-1 value."""
    if (table, column) not in S.TIE_COLUMNS or len(values) < 2:
        return values
    non_null = [v for v in values if v is not None]
    if not non_null:
        return values
    top = max(non_null) if all(isinstance(v, (int, float)) for v in non_null) else non_null[0]
    out = list(values)
    idx = [i for i, v in enumerate(out) if v is not None]
    if len(idx) >= 2:
        out[idx[0]] = top
        out[idx[1]] = top
    return out


def _plant_group_sizes(table: str, column: str, values: list, rng) -> list:
    """group_sizes: ensure groups of size 1, 2 and >= 3 exist for the grouping column."""
    if (table, column) not in S.GROUP_COLUMNS or len(values) < 6:
        return values
    non_null = [v for v in values if v is not None]
    if not non_null:
        return values
    a = non_null[0]
    b = non_null[1] if len(non_null) > 1 else a
    out = list(values)
    idx = [i for i, v in enumerate(out) if v is not None]
    if len(idx) >= 6:
        out[idx[0]] = a
        out[idx[1]] = b
        out[idx[2]] = b
        out[idx[3]] = a
        out[idx[4]] = a
        out[idx[5]] = a
    return out


def _plant_different_values(table: str, column: str, values: list, rng) -> list:
    """rows_with_different_values: >= 2 qualifying rows with different values per group."""
    if (table, column) not in S.DIFFERENT_VALUES or len(values) < 2:
        return values
    out = list(values)
    idx = [i for i, v in enumerate(out) if v is not None]
    if len(idx) >= 2 and out[idx[0]] == out[idx[1]]:
        v = out[idx[1]]
        if isinstance(v, (int, float)):
            out[idx[1]] = v + 1
        elif isinstance(v, str):
            out[idx[1]] = v + 'x'
    return out


def _apply_spec(schema, table: str, columns: dict, rng) -> dict:
    """Apply the per-column specification rules to the generated columns of one table."""
    for col, vals in list(columns.items()):
        vals = _plant_nulls(table, col, vals, rng)
        if not _is_key_column(schema, table, col):
            vals = _plant_duplicates(table, col, vals, rng)
            vals = _plant_ties(table, col, vals, rng)
            vals = _plant_group_sizes(table, col, vals, rng)
            vals = _plant_different_values(table, col, vals, rng)
        columns[col] = vals
    return columns


def _remap_fks(schema, table: str, columns: dict, instance: dict, rng) -> dict:
    """Re-validate every FK value against the parent pool; remap orphans to a valid parent key."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in columns:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        if not pv:
            columns[cm.name] = [None] * len(columns[cm.name])
            continue
        pset = set(pv)
        columns[cm.name] = [v if (v is None or v in pset) else rng.choice(pv)
                            for v in columns[cm.name]]
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as generated rows appended to the compact database."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = spec_sampler(
                    t, cm.name, cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), rng, len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = _apply_spec(schema, t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        inst[t] = _remap_fks(schema, t, inst[t], inst, rng)
    return {t: inst[t] for t in schema.tables}
