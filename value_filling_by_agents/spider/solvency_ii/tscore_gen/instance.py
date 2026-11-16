"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
from .values import _init_sampler

_PK_SHIFT_BASE = {}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    if not columns:
        return 0
    return len(next(iter(columns.values())))


def _max_pk(schema, table: str) -> int:
    """Largest compact primary-key value (first single-column PK part) or 0."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 0
    vals = [v for v in schema.original_values.get((table, tm.primary_key[0]), [])
            if isinstance(v, int)]
    return max(vals) if vals else 0


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes (table_sizes_per_instance); small jitter keeps instances distinct."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 15)
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, base + jitter)
    return sizes


def finalize_single_pk(schema, table: str, cols: dict, start: int) -> int:
    """Replace a single-column PK with fresh sequential values above the compact max."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return start
    pk = tm.primary_key[0]
    n = _n_rows(cols)
    vals = list(range(start, start + n))
    cols[pk] = vals
    return start + n


def fill_foreign_keys(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's *final* PK values (compact+generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if pv:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
        else:
            out[cm.name] = [None] * n
    return out


def remap_dangling_fks(instance: dict, schema, rng) -> None:
    """Ensure every non-NULL child FK value still exists in the parent column."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        child = instance.get(ct, {}).get(cc)
        if child is None:
            continue
        parent = instance.get(pt, {}).get(pc) or []
        pset = set(v for v in parent if v is not None)
        for i, v in enumerate(child):
            if v is None:
                continue
            if v not in pset:
                child[i] = rng.choice(parent) if parent else None


def dedup_primary_keys(table_meta, columns: dict, rng=None) -> int:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return 0
    n = _n_rows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    dropped = n - len(keep)
    if dropped:
        for c in list(columns):
            columns[c] = [columns[c][i] for i in keep]
    return dropped


def drop_unique_duplicates(table_meta, columns: dict) -> int:
    """Drop rows repeating any single-column UNIQUE value."""
    total = 0
    for cm in table_meta.columns:
        if cm.unique and cm.pk_pos == 0 and cm.name in columns:
            seen, keep = set(), []
            vals = columns[cm.name]
            for i, v in enumerate(vals):
                if v is not None and v in seen:
                    continue
                if v is not None:
                    seen.add(v)
                keep.append(i)
            dropped = len(vals) - len(keep)
            if dropped:
                total += dropped
                for c in list(columns):
                    columns[c] = [columns[c][i] for i in keep]
    return total


def _plant_nulls(values: list, rng, share: float = spec.NULL_SHARE) -> list:
    """NULL rule: at least one NULL, share ~= share, never overwrites an existing NULL differently."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _nullable_columns(schema) -> list:
    """All nullable non-primary-key columns (spec list plus schema-derived)."""
    out = set(spec.NULLABLE_COLUMNS)
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.pk_pos == 0 and not cm.notnull:
                out.add((t, cm.name))
    return sorted(out)


def _plant_price_patterns(schema, values: list, rng) -> list:
    """Ensure >= PRICE_DISTINCT_MIN distinct non-NULL values and PRICE_TIE_ROWS non-NULL rows tied at the *global
    maximum* of the non-NULL prices."""
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    non_null_idx = [i for i, v in enumerate(out) if v is not None]
    if len(non_null_idx) < spec.PRICE_TIE_ROWS:
        null_idx = [i for i, v in enumerate(out) if v is None]
        rng.shuffle(null_idx)
        need = spec.PRICE_TIE_ROWS - len(non_null_idx)
        for i in null_idx[:need]:
            out[i] = round(rng.uniform(spec.PRICE_LO, spec.PRICE_HI), spec.PRICE_DECIMALS)
            non_null_idx.append(i)
    if not non_null_idx:
        return out
    distinct = {out[i] for i in non_null_idx}
    while len(distinct) < spec.PRICE_DISTINCT_MIN:
        v = round(rng.uniform(spec.PRICE_LO, spec.PRICE_HI), spec.PRICE_DECIMALS)
        if v not in distinct:
            distinct.add(v)
            free = [i for i in non_null_idx if i not in _tie_slots(out, rng)]
            if free:
                out[free[0]] = v
    gmax = max(out[i] for i in non_null_idx)
    tied = [i for i in non_null_idx if out[i] == gmax]
    while len(tied) < spec.PRICE_TIE_ROWS:
        cand = [i for i in non_null_idx if out[i] != gmax]
        if not cand:
            break
        i = rng.choice(cand)
        out[i] = gmax
        tied.append(i)
    return out


def _tie_slots(values: list, rng) -> set:
    """Indices currently tied at the non-NULL max (helper used while planting price distribution)."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return set()
    gmax = max(non_null)
    return {i for i, v in enumerate(values) if v == gmax}


def _plant_type_code_duplicates(values: list, rng) -> list:
    n = len(values)
    if n == 0:
        return values
    pool = spec.ENUMS[('Products', 'Product_Type_Code')]
    out = list(values)
    non_null = [i for i, v in enumerate(out) if v is not None]
    target = max(1, int(round(n * spec.TYPE_CODE_DUP_SHARE)))
    if not non_null:
        return out
    anchor = rng.choice(pool)
    slots = list(non_null)
    rng.shuffle(slots)
    for i in slots[:target]:
        out[i] = anchor
    return out


def _plant_group_sizes(values: list, rng, pool=None) -> list:
    """Ensure groups of size 1, 2 and >= 3 exist (group_sizes pattern)."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    src = pool if pool is not None else sorted(
        {v for v in out if v is not None}, key=lambda x: str(x))
    if len(src) < 3:
        src = list(src) + [('grp_%d' % i) for i in range(3)]
    a, b, c = src[0], src[1], src[2]
    slots = list(range(n))
    rng.shuffle(slots)
    out[slots[0]] = a
    out[slots[1]] = b
    out[slots[2]] = b
    out[slots[3]] = c
    out[slots[4]] = c
    out[slots[5]] = c
    return out


def _plant_unmatched_parents(instance: dict, schema, table: str, rng) -> None:
    """Ensure at least one parent row (final PK value) has no children."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return
    pk = tm.primary_key[0]
    pvals = [v for v in (instance.get(table, {}).get(pk) or []) if v is not None]
    if not pvals:
        return
    children = [(ct, cc) for (ct, cc), (pt, pc) in schema.fks.items() if pt == table]
    if not children:
        return
    used = set()
    for ct, cc in children:
        used |= {v for v in (instance.get(ct, {}).get(cc) or []) if v is not None}
    if any(v not in used for v in pvals):
        return
    victim = rng.choice(pvals)
    others = [x for x in pvals if x != victim]
    for ct, cc in children:
        col = instance.get(ct, {}).get(cc)
        if col is None:
            continue
        for i, v in enumerate(col):
            if v == victim:
                col[i] = rng.choice(others) if others else None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance with specification patterns planted, in FK-safe order."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)

    inst: dict = {}
    next_pk = {}

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        start = _max_pk(schema, t) + 1
        next_pk[t] = finalize_single_pk(schema, t, cols, start)

    for t in order:
        n = int(size.get(t, 0))
        fk = fill_foreign_keys(inst, schema, t, n, rng)
        inst[t].update(fk)

    for t in order:
        tm = schema.tables[t]
        if len(tm.primary_key) <= 1:
            continue
        dedup_primary_keys(tm, inst[t])
        inst[t].update(fill_foreign_keys(inst, schema, t, _n_rows(inst[t]), rng))

    nullable = _nullable_columns(schema)
    for (t, c) in nullable:
        if t in inst and c in inst[t]:
            inst[t][c] = _plant_nulls(inst[t][c], rng)

    if 'Products' in inst and 'Product_Price' in inst['Products']:
        inst['Products']['Product_Price'] = _plant_price_patterns(
            schema, inst['Products']['Product_Price'], rng)

    if 'Products' in inst and 'Product_Type_Code' in inst['Products']:
        inst['Products']['Product_Type_Code'] = _plant_type_code_duplicates(
            inst['Products']['Product_Type_Code'], rng)

    for (t, c) in spec.GROUP_SIZE_COLUMNS:
        if t in inst and c in inst[t]:
            if c in schema.tables[t].primary_key:
                continue
            pool = None
            if (t, c) in spec.ENUMS:
                pool = list(spec.ENUMS[(t, c)])
            inst[t][c] = _plant_group_sizes(inst[t][c], rng, pool=pool)

    for t in ('Products', 'Events'):
        if t in inst:
            _plant_unmatched_parents(inst, schema, t, rng)

    for t in order:
        tm = schema.tables[t]
        dedup_primary_keys(tm, inst[t])
        drop_unique_duplicates(tm, inst[t])
    remap_dangling_fks(inst, schema, rng)

    return {t: inst[t] for t in schema.tables}
