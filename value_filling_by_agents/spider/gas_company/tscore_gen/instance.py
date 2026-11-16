"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import (BASE_SIZES, GROUP_SIZE_TARGETS, DUPLICATE_SHARE, TIE_COLUMNS,
                   MIN_DISTINCT, in_range)
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row); first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing_keys), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples: list, existing: dict) -> dict:
    """Drop rows repeating any UNIQUE tuple (single or composite) or colliding with compact rows."""
    for cols in unique_tuples:
        cols = [c for c in cols if c in columns]
        if not cols:
            continue
        seen = set(existing.get(tuple(cols), set()))
        keep = []
        for i in range(len(next(iter(columns.values())))):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, compact_parent: dict, pt: str, pc: str) -> list:
    """Parent values available for FK draws: compact + generated, non-NULL."""
    pv = list(compact_parent.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
    return [v for v in pv if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_parent: dict, only: list = None) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        if only is not None and cm.name not in only:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, compact_parent, pt, pc)
        nullable = not cm.notnull and cm.pk_pos == 0
        vals = []
        null_done = False
        for _ in range(n):
            if nullable and (not null_done or rng.random() < 0.1):
                vals.append(None)
                null_done = True
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Sizes are FIXED at the specification baselines (spec uncertainty note)."""
    return {t: BASE_SIZES.get(t, 10) for t in schema.tables}


def _apply_group_sizes(table: str, column: str, values: list, rng, key_cols: set) -> list:
    """Force group sizes 1, 2 and >= 3 for a column (specification group_sizes target)."""
    if (table, column) not in GROUP_SIZE_TARGETS or not values:
        return values
    n = len(values)
    if n < 6:
        return values
    pool = list(dict.fromkeys(values))
    if len(pool) < 3:
        return values
    a, b, c = rng.sample(pool, 3)
    out = list(values)
    positions = [i for i in range(n) if i not in key_cols]
    if len(positions) < 6:
        positions = list(range(n))
    rng.shuffle(positions)
    out[positions[0]] = a
    out[positions[1]] = b
    out[positions[2]] = b
    for k in range(3, min(n, 6)):
        out[positions[k]] = c
    return out


def _apply_duplicate_share(table: str, column: str, values: list, rng, key_cols: set) -> list:
    """Ensure a 20-50 % duplicate share for DISTINCT patterns (non-key positions only)."""
    if (table, column) not in DUPLICATE_SHARE or len(values) < 4:
        return values
    lo, hi = DUPLICATE_SHARE[(table, column)]
    share = rng.uniform(lo, hi)
    n = len(values)
    n_dup = max(1, int(n * share))
    out = list(values)
    positions = [i for i in range(n) if i not in key_cols]
    if len(positions) < 2:
        positions = list(range(n))
    for _ in range(n_dup):
        i = rng.choice(positions)
        j = rng.choice(positions)
        out[i] = out[j]
    return out


def _apply_ties(table: str, column: str, values: list, rng, key_cols: set) -> list:
    """Introduce tied sort values so ORDER BY ..."""
    if (table, column) not in TIE_COLUMNS or len(values) < 3:
        return values
    out = list(values)
    positions = [i for i in range(len(out)) if i not in key_cols]
    if len(positions) < 2:
        return out
    if rng.random() < 0.5:
        out[positions[1]] = out[positions[0]]
    if rng.random() < 0.3 and len(positions) > 2:
        out[positions[2]] = out[positions[0]]
    return out


def _enforce_min_distinct(table: str, column: str, values: list, rng, key_cols: set) -> list:
    """Ensure >= MIN_DISTINCT distinct non-NULL values (so tie targets are informative)."""
    need = MIN_DISTINCT.get((table, column))
    if not need or not values:
        return values
    out = list(values)
    distinct = {v for v in out if v is not None}
    if len(distinct) >= need:
        return out
    pool = list(distinct)
    if not pool:
        return out
    positions = [i for i in range(len(out)) if i not in key_cols]
    for k, v in enumerate(pool):
        if k < len(positions):
            out[positions[k]] = v
    return out


def _enforce_fk_group_size(table: str, column: str, values: list, parent_pool: list, rng) -> list:
    """Force group sizes 1, 2 and >= 3 for station_company.Company_ID (specification target)."""
    if (table, column) != ('station_company', 'Company_ID') or not values or not parent_pool:
        return values
    out = list(values)
    n = len(out)
    pool = list(dict.fromkeys(parent_pool))
    if len(pool) < 3 or n < 6:
        return out
    a, b, c = rng.sample(pool, 3)
    positions = list(range(n))
    rng.shuffle(positions)
    for i in positions[:3]:
        out[i] = a
    for i in positions[3:5]:
        out[i] = b
    out[positions[5]] = c
    return out


def _revalidate_fk(table: str, column: str, values: list, parent_pool: list, rng) -> list:
    """Replace any FK value not in the parent pool with a drawn parent value (or NULL)."""
    if not parent_pool:
        return [None for _ in values]
    pool_set = set(parent_pool)
    return [v if (v is None or v in pool_set) else rng.choice(parent_pool) for v in values]


def _enforce_location_count_ties(values: list, rng, key_cols: set) -> list:
    """Ensure at least two distinct Location values have equal COUNT(*) (spec tie_on COUNT(*))."""
    if not values or len(values) < 4:
        return values
    out = list(values)
    positions = [i for i in range(len(out)) if i not in key_cols]
    if len(positions) < 4:
        positions = list(range(len(out)))
    distinct = list(dict.fromkeys(v for v in out if v is not None))
    if len(distinct) < 2:
        return out
    a, b = rng.sample(distinct, 2)
    rng.shuffle(positions)
    out[positions[0]] = a
    out[positions[1]] = a
    out[positions[2]] = b
    out[positions[3]] = b
    return out


def _enforce_industry_aggregate_ties(inst: dict, rng) -> None:
    """Ensure at least two Main_Industry values have equal SUM and AVG(Market_Value)."""
    cols = inst.get('company')
    if not cols:
        return
    ind = cols.get('Main_Industry')
    mv = cols.get('Market_Value')
    if not ind or not mv:
        return
    n = len(ind)
    if n < 4:
        return
    industries = list(dict.fromkeys(v for v in ind if v is not None))
    if len(industries) < 2:
        return
    a, b = rng.sample(industries, 2)
    pos_a = [i for i in range(n) if ind[i] == a]
    pos_b = [i for i in range(n) if ind[i] == b]
    if len(pos_a) < 2 or len(pos_b) < 2:
        return
    val = round(rng.uniform(50.0, 200.0), 1)
    for i in pos_a[:2]:
        mv[i] = val
    for i in pos_b[:2]:
        mv[i] = val
    for i in pos_a[2:]:
        mv[i] = 0.0
    for i in pos_b[2:]:
        mv[i] = 0.0


def _sequential_int_pk(table_meta, columns: dict, existing_keys: set, rng) -> dict:
    """Generate sequential int primary keys starting at max(existing)+1 (generic rule)."""
    if not table_meta.primary_key or len(table_meta.primary_key) != 1 or not columns:
        return columns
    pk = table_meta.primary_key[0]
    if pk not in columns:
        return columns
    cm = next((c for c in table_meta.columns if c.name == pk), None)
    if cm is None or 'int' not in (cm.type_str or '').lower():
        return columns
    ints = [k[0] for k in existing_keys if isinstance(k[0], int)]
    start = (max(ints) + 1) if ints else 1
    n = len(columns[pk])
    columns[pk] = [start + i for i in range(n)]
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), specification-aware, appended to compact rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact_parent = {k: list(v) for k, v in schema.original_values.items()}
    existing_pk = {}
    existing_unique = {}
    for t, tm in schema.tables.items():
        if tm.primary_key:
            n = len(schema.original_values.get((t, tm.primary_key[0]), []))
            existing_pk[t] = {tuple(schema.original_values[(t, c)][i] for c in tm.primary_key) for i in range(n)}
        for cols in schema.unique_tuples:
            tt, cc = cols
            if tt != t:
                continue
            n = len(schema.original_values.get((t, cc[0]), []))
            existing_unique.setdefault(tuple(cc), set()).update(
                tuple(schema.original_values[(t, c)][i] for c in cc) for i in range(n))
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                nullable = (not cm.notnull) and cm.pk_pos == 0
                null_share = 0.0
                if nullable:
                    ov = schema.original_values.get((t, cm.name), [])
                    null_share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.0
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), nullable=nullable,
                                                       null_share=null_share)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        key_cols = set(tm.primary_key)
        for tt, cc in schema.unique_tuples:
            if tt == t:
                key_cols.update(cc)
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_group_sizes(t, cm.name, cols[cm.name], rng, key_cols)
                cols[cm.name] = _apply_duplicate_share(t, cm.name, cols[cm.name], rng, key_cols)
                cols[cm.name] = _apply_ties(t, cm.name, cols[cm.name], rng, key_cols)
                cols[cm.name] = _enforce_min_distinct(t, cm.name, cols[cm.name], rng, key_cols)
        if t == 'gas_station' and 'Location' in cols:
            cols['Location'] = _enforce_location_count_ties(cols['Location'], rng, key_cols)
        fk_cols = [cm.name for cm in tm.columns if (t, cm.name) in schema.fks]
        if fk_cols:
            fk_vals = fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_parent)
            for c in fk_cols:
                if c in fk_vals:
                    cols[c] = fk_vals[c]
            for c in fk_cols:
                pt, pc = schema.fks[(t, c)]
                pool = _parent_pool(inst, compact_parent, pt, pc)
                cols[c] = _enforce_fk_group_size(t, c, cols[c], pool, rng)
                cols[c] = _revalidate_fk(t, c, cols[c], pool, rng)
        inst[t] = cols
        cols = _sequential_int_pk(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                  existing_pk.get(t, set()), rng)
        cols = sample_fresh_primary_keys(tm, cols, existing_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols, [c for tt, c in schema.unique_tuples if tt == t],
                                      existing_unique)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    if 'company' in inst:
        _enforce_industry_aggregate_ties(inst, rng)
    return {t: inst[t] for t in schema.tables}
