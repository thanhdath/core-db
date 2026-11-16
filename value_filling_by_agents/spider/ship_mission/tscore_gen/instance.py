"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append-only generation."""
from .spec import column_rules, table_sizes
from .values import _init_sampler, make_column_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


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


def _next_pk_start(schema, table: str) -> int:
    """First integer above every compact PK value (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 1
    vals = schema.original_values.get((table, tm.primary_key[0]), [])
    nums = [v for v in vals if isinstance(v, int)]
    return (max(nums) + 1) if nums else 1


def _pk_columns(schema, table: str) -> list:
    return list(schema.tables[table].primary_key)


def _fill_primary_keys(schema, table: str, n: int, rng) -> dict:
    """Sequential integers starting at 1 above the compact maximum, unique, never NULL."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if not pk:
        return {}
    start = _next_pk_start(schema, table)
    out = {}
    if len(pk) == 1:
        out[pk[0]] = list(range(start, start + n))
    else:
        for j, c in enumerate(pk):
            out[c] = [start + i for i in range(n)]
    return out


def _fk_parent_pool(instance: dict, schema, table: str, col: str) -> list:
    """Parent key values: compact rows plus generated rows (in memory)."""
    pt, pc = schema.fks[(table, col)]
    vals = list(schema.original_values.get((pt, pc), []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _null_share_for(schema, rules, table: str, col: str, cm, rng) -> float:
    """NULL share: explicit target, else compact share, else 0.10; NOT NULL -> 0."""
    if cm.notnull or cm.pk_pos > 0:
        return 0.0
    r = rules.get((table, col)) or {}
    if r.get('not_null'):
        return 0.0
    nr = r.get('null_range')
    if nr is not None:
        lo, hi = nr
        return rng.uniform(lo, hi) if hi > lo else lo
    ov = schema.original_values.get((table, col), [])
    if ov:
        share = sum(1 for v in ov if v is None) / float(len(ov))
        return share
    return 0.10


def _plant_nulls(values: list, share: float, rng) -> list:
    """NULL is a value: at least one NULL when share > 0; never replaces a planted NULL."""
    if share <= 0.0 or not values:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _group_plan(n: int, sizes: list, rng) -> list:
    """Assign group labels so that group sizes follow the target list (1, 2, >=3)."""
    if not sizes or n <= 0:
        return [0] * n
    labels = []
    g = 0
    while len(labels) < n:
        sz = sizes[g % len(sizes)]
        labels.extend([g] * min(sz, n - len(labels)))
        g += 1
    rng.shuffle(labels)
    return labels


def _apply_enum_groups(values: list, enum: list, sizes: list, rng) -> list:
    """Distribute enum values over groups of the requested sizes (group_sizes target)."""
    if not enum or not sizes:
        return values
    n = len(values)
    plan = _group_plan(n, sizes, rng)
    out = list(values)
    for i in range(n):
        out[i] = enum[plan[i] % len(enum)]
    return out


def _apply_duplicates(values: list, share: float, rng) -> list:
    """20-50 % duplicate share for DISTINCT targets: repeat earlier values."""
    if not values or share <= 0:
        return values
    n = len(values)
    k = int(round(share * n))
    if k <= 0:
        return values
    idx = rng.sample(range(n), min(k, n))
    for i in idx:
        j = rng.randrange(n)
        if j != i:
            values[i] = values[j]
    return values


def _apply_boundary(values: list, boundary: list, rng) -> list:
    """Include boundary values and one step outside when a comparison_boundary target exists."""
    if not boundary or not values:
        return values
    pool = list(boundary)
    for b in boundary:
        pool += [b - 1, b + 1]
    n = len(values)
    k = min(n, max(1, n // 2))
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = rng.choice(pool)
    return values


def _apply_max_tie(values: list, rng) -> list:
    """rows_with_different_values: at least two rows share the maximum, others differ."""
    if len(values) < 2:
        return values
    nums = [v for v in values if isinstance(v, int)]
    if not nums:
        return values
    mx = max(nums)
    positions = [i for i, v in enumerate(values) if v == mx]
    if len(positions) < 2:
        i = rng.randrange(len(values))
        values[i] = mx
    return values


def _apply_positive(values: list, lo, hi, rng) -> list:
    """Keep values inside the declared range (formula by construction)."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if lo is not None and v < lo:
            v = lo + rng.randint(0, 3)
        if hi is not None and v > hi:
            v = hi - rng.randint(0, 3)
        out.append(v)
    return out


def _sample_column(schema, rules, table: str, col: str, cm, n: int, rng, literal_pool: dict) -> list:
    """Sample n values for a non-FK column, then apply the specification's targets."""
    r = rules.get((table, col)) or {}
    key = (table, col)
    pool = list(literal_pool.get(key, []))
    pool += [str(x) for x in r.get('literals', [])]
    ov = schema.original_values.get(key, [])
    p = 0.0 if cm.checked else 0.2
    sampler = _init_sampler(cm, pool, ov, p, rng, 1 if cm.pk_pos else 0)
    values = [sampler.sample() for _ in range(n)]

    enum = r.get('enum')
    if enum:
        if r.get('group_sizes'):
            values = _apply_enum_groups(values, enum, r['group_sizes'], rng)
        else:
            values = [rng.choice(enum) for _ in range(n)]
        if r.get('dup_share'):
            values = _apply_duplicates(values, r['dup_share'], rng)
    elif r.get('dup_share'):
        values = _apply_duplicates(values, r['dup_share'], rng)

    if r.get('boundary'):
        values = _apply_boundary(values, r['boundary'], rng)
    if r.get('max_tie'):
        values = _apply_max_tie(values, rng)

    rng_spec = r.get('range')
    if rng_spec:
        values = _apply_positive(values, rng_spec[0], rng_spec[1], rng)
    elif r.get('positive'):
        values = _apply_positive(values, 1, None, rng)

    share = _null_share_for(schema, rules, table, col, cm, rng)
    values = _plant_nulls(values, share, rng)
    return values


def _fill_foreign_keys(instance: dict, schema, rules, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) or are NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pv = _fk_parent_pool(instance, schema, table, cm.name)
        r = rules.get(key) or {}
        share = _null_share_for(schema, rules, table, cm.name, cm, rng)
        vals = []
        for _ in range(n):
            if pv and rng.random() >= share:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if pv and share > 0 and all(v is None for v in vals):
            vals[rng.randrange(n)] = rng.choice(pv)
        if pv and share <= 0 and any(v is None for v in vals):
            vals = [rng.choice(pv) if v is None else v for v in vals]
        out[cm.name] = vals
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    spec = spec or {}
    rules = column_rules(spec)
    if size is None:
        size = table_sizes(spec, schema, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                continue
            cols[cm.name] = _sample_column(schema, rules, t, cm.name, cm, n, rng, literal_pool)
        pk = _fill_primary_keys(schema, t, n, rng)
        cols.update(pk)
        cols.update(_fill_foreign_keys(inst, schema, rules, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
