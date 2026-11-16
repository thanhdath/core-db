"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import column_plan, null_share, table_size
from .values import _init_sampler


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


def _parent_pool(instance: dict, schema, table: str, column: str) -> list:
    """Compact + generated values of a parent column (kept in memory for lookups)."""
    vals = list(schema.original_values.get((table, column), []) or [])
    vals += list(instance.get(table, {}).get(column, []) or [])
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        share = null_share(spec, table, cm.name, 0.0, n) if not cm.notnull else 0.0
        col = []
        for _ in range(n):
            if share and rng.random() < share:
                col.append(None)
            elif pv:
                col.append(rng.choice(pv))
            else:
                col.append(None)
        out[cm.name] = col
    return out


def _group_size_plan(n: int, rng) -> list:
    """Group-size hint: sizes 1, 2 and >=3 all present, summing exactly to n (when n >= 6)."""
    if n <= 0:
        return []
    if n < 6:
        return [1] * n
    sizes = [1, 2, 3]
    while sum(sizes) < n:
        sizes.append(rng.choice([1, 1, 2, 3, 3, 4]))
    excess = sum(sizes) - n
    while excess > 0:
        for j in range(len(sizes) - 1, -1, -1):
            floor = 3 if j == 2 else 1
            if sizes[j] - 1 >= floor:
                sizes[j] -= 1
                excess -= 1
                break
        else:
            break
    return sizes


def _assign_group_keys(n: int, rng, plan: dict) -> list:
    """Assign group keys so that group sizes 1, 2 and >=3 occur (when the hint is set)."""
    if not plan.get('group_sizes') or n < 6:
        return [rng.randint(1, max(1, n // 2)) for _ in range(n)]
    sizes = _group_size_plan(n, rng)
    keys, k = [], 1
    for s in sizes:
        keys.extend([k] * s)
        k += 1
    rng.shuffle(keys)
    return keys


def _fresh_pk_start(schema, table: str, column: str) -> int:
    vals = [v for v in (schema.original_values.get((table, column), []) or []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _pk_values(schema, table: str, column: str, n: int, rng) -> list:
    """Sequential integers starting after the compact maximum; unique; never NULL."""
    start = _fresh_pk_start(schema, table, column)
    return list(range(start, start + n))


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs in a nullable column: at least one NULL row, share following the compact share."""
    if not values or share <= 0:
        return values
    existing = sum(1 for v in values if v is None)
    target = max(1, int(round(len(values) * share)))
    k = max(0, target - existing)
    k = min(k, len(values))
    if k <= 0:
        return values
    idx = rng.sample(range(len(values)), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _compact_max(schema, table: str, column: str):
    vals = [v for v in (schema.original_values.get((table, column), []) or [])
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return max(vals) if vals else None


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance of appended rows (fuzz.py:111-196 + specification)."""
    spec = spec or {'columns': {}, 'sizes': {}, 'null_targets': set()}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    plans = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                plan = column_plan(spec, t, cm.name, cm.type_str)
                plans[(t, cm.name)] = plan
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), plan=plan,
                                                       compact_max=_compact_max(schema, t, cm.name))
    if size is None:
        size = {t: table_size(spec, t, rng) for t in order}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        for cm in tm.columns:
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                cols[cm.name] = _pk_values(schema, t, cm.name, n, rng)
        for cm in tm.columns:
            plan = plans.get((t, cm.name), {})
            if plan.get('group_sizes') and cm.pk_pos == 0 and (t, cm.name) not in schema.fks:
                keys = _assign_group_keys(n, rng, plan)
                base = cols.get(cm.name) or [None] * n
                if len(base) < n:
                    base = list(base) + [None] * (n - len(base))
                first = {}
                for i, k in enumerate(keys):
                    if k not in first:
                        first[k] = base[i]
                cols[cm.name] = [first[k] for k in keys]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            share = null_share(spec, t, cm.name, 0.0, n)
            if share > 0 and cm.name in cols:
                cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
