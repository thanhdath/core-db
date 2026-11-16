"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec sizes with a small jitter; fallback to the upstream rand_lin / level sizes."""
    if schema.spec_sizes:
        sizes = {}
        for t in schema.tables:
            base = schema.spec_sizes.get(t)
            if base is None:
                base = 30 + int(rng.random() * 200)
            j = int(base * 0.10)
            sizes[t] = max(0, base + (rng.randint(-j, j) if j else 0))
        return sizes
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _plant_nulls(cols: dict, names: list, nullable: set, fk_cols: set, rng) -> None:
    """NULL rule: at least one NULL per nullable column, share ~2% (5% for FK)."""
    n = len(cols[names[0]]) if names else 0
    if n == 0:
        return
    for c in names:
        if c not in nullable:
            continue
        share = 0.05 if c in fk_cols else 0.02
        k = max(1, int(round(n * share)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[c][i] = None


def _plant_duplicates(cols: dict, names: list, dup_cols: set, rng) -> None:
    """20-50% duplicate share on DISTINCT-targeted columns: reuse values from a small pool."""
    n = len(cols[names[0]]) if names else 0
    if n < 4:
        return
    for c in names:
        if c not in dup_cols:
            continue
        share = rng.uniform(0.20, 0.50)
        k = int(n * share)
        if k < 2:
            continue
        pool = [v for v in cols[c] if v is not None]
        if not pool:
            continue
        small = rng.sample(pool, min(len(pool), max(2, len(pool) // 4)))
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[c][i] = rng.choice(small)


def _fresh_against_compact(schema, table: str, cols: dict, names: list) -> dict:
    """Drop generated rows whose PK / UNIQUE tuple already exists in the compact rows."""
    tm = schema.tables[table]
    n = len(cols[names[0]]) if names else 0
    if n == 0:
        return cols
    keys = []
    if tm.primary_key:
        keys.append(tuple(tm.primary_key))
    for t, tup in schema.unique_tuples:
        if t == table:
            keys.append(tuple(tup))
    for cm in tm.columns:
        if cm.unique:
            keys.append((cm.name,))
    if not keys:
        return cols
    seen = []
    for k in keys:
        if all(c in cols for c in k):
            seen.append((k, {tuple(schema.original_values.get((table, c), [])[i] for c in k)
                             for i in range(len(schema.original_values.get((table, k[0]), [])))}))
    keep = []
    for i in range(n):
        ok = True
        for k, orig in seen:
            tup = tuple(cols[c][i] for c in k)
            if tup in orig:
                ok = False
                break
        if ok:
            keep.append(i)
    return _filter(cols, keep)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                k = (t, cm.name)
                pool = list(literal_pool.get(k, [])) + list(schema.spec_pools.get(k, []))
                samplers[k] = _init_sampler(cm, pool, schema.original_values.get(k, []), p, rng,
                                            len(tm.primary_key),
                                            spec_range=schema.spec_ranges.get(k),
                                            spec_enum=schema.spec_enums.get(k))
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
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        names = [cm.name for cm in tm.columns]
        nullable = {cm.name for cm in tm.columns if not cm.notnull and cm.pk_pos == 0}
        fk_cols = {cm.name for cm in tm.columns if (t, cm.name) in schema.fks}
        dup_cols = {c for (tt, c) in schema.spec_dup if tt == t}
        _plant_duplicates(cols, names, dup_cols, rng)
        _plant_nulls(cols, names, nullable, fk_cols, rng)
        cols = _fresh_against_compact(schema, t, cols, names)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
