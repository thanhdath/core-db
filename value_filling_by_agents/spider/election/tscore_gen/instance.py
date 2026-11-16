"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from .values import _init_sampler, _num

SPEC_SIZES = {'county': 5, 'party': 7, 'election': 8}
NULL_TARGETS = {('election', 'Delegate'), ('election', 'District'), ('election', 'Party')}
BOUNDARIES = {
    ('election', 'District'): [0, 1, 2, 3, 4, 99999, 100000, 100001],
    ('county', 'Population'): [93059, 93060, 93061, 99999, 100000, 100001],
}
FORMULA_BOUNDS = {
    ('party', 'Year'): (1990, 2010),
    ('election', 'First_Elected'): (1990, 2010),
}
DUP_COLUMNS = {('election', 'Delegate'), ('county', 'County_name'), ('party', 'Party'),
               ('election', 'Committee')}


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
    """Specification table sizes per instance (generated rows appended to the compact rows)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = int(SPEC_SIZES.get(t, 0))
    return sizes


def _parent_key_pool(schema, instance: dict, pt: str, pc: str) -> list:
    """Parent key pool = compact values + generated values (in memory), non-NULL, deduplicated."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    out, seen = [], set()
    for v in vals:
        if v is None:
            continue
        k = (type(v).__name__, v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _fresh_pk_values(schema, table: str, col: str, n: int, rng) -> list:
    """Sequential integers starting at 1, skipping ids already used by the compact rows."""
    used = set()
    for v in schema.original_values.get((table, col), []):
        if isinstance(v, (int, float)) and float(v).is_integer():
            used.add(int(v))
    out, cur = [], 1
    while len(out) < n:
        if cur not in used:
            out.append(cur)
        cur += 1
    return out


def _plant_nulls(values: list, n_null: int, rng) -> list:
    """Plant NULL rows at random positions; never replace a planted NULL."""
    vals = list(values)
    n = len(vals)
    if n_null <= 0 or n == 0:
        return vals
    n_null = min(n_null, n)
    pos = rng.sample(range(n), n_null)
    for i in pos:
        vals[i] = None
    return vals


def _dup_share(values: list, rng, lo: float = 0.2, hi: float = 0.5) -> list:
    """Force a 20-50% duplicate share by copying existing non-NULL values into other rows."""
    vals = list(values)
    n = len(vals)
    if n < 2:
        return vals
    nonnull = [i for i, v in enumerate(vals) if v is not None]
    if len(nonnull) < 2:
        return vals
    target = int(round(n * rng.uniform(lo, hi)))
    seen, dups = set(), 0
    for v in vals:
        if v is None:
            continue
        if v in seen:
            dups += 1
        else:
            seen.add(v)
    need = max(0, target - dups)
    if need == 0:
        return vals
    candidates = [i for i in nonnull if vals[i] not in seen or True]
    rng.shuffle(candidates)
    for i in candidates[:need]:
        src = rng.choice(nonnull)
        if src != i:
            vals[i] = vals[src]
    return vals


def _group_sizes(values: list, rng) -> list:
    """Ensure group sizes 1, 2 and >=3 exist on the column (by copying values)."""
    vals = list(values)
    n = len(vals)
    if n < 6:
        return vals
    nonnull = [i for i, v in enumerate(vals) if v is not None]
    if len(nonnull) < 6:
        return vals
    rng.shuffle(nonnull)
    srcs = nonnull[:3]
    v0 = vals[srcs[0]]
    for i in nonnull:
        if i != srcs[0] and vals[i] == v0:
            vals[i] = vals[srcs[1]]
    v1 = vals[srcs[1]]
    copies = [i for i in nonnull if i not in srcs and vals[i] == v1]
    if len(copies) > 1:
        for i in copies[1:]:
            vals[i] = vals[srcs[2]]
    elif not copies:
        for i in nonnull:
            if i not in srcs:
                vals[i] = v1
                break
    v2 = vals[srcs[2]]
    copies2 = [i for i in nonnull if i not in srcs and vals[i] == v2]
    need = max(0, 2 - len(copies2))
    if need:
        free = [i for i in nonnull if i not in srcs and vals[i] != v1]
        for i in free[:need]:
            vals[i] = v2
    return vals


def _apply_formula_bounds(table: str, col: str, values: list, rng) -> list:
    """Clamp numeric values into the formula bounds (Year/First_Elected BETWEEN 1990 AND 2010)."""
    b = FORMULA_BOUNDS.get((table, col))
    if not b:
        return values
    lo, hi = b
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        f = _num(v)
        if f is None:
            out.append(v)
            continue
        if f < lo or f > hi:
            f = rng.uniform(lo, hi)
        out.append(int(round(f)) if float(f).is_integer() else round(f, 4))
    return out


def _apply_positive(table: str, col: str, values: list, rng) -> list:
    """County_Id > 0, Population > 0, Party_ID > 0, Election_ID > 0."""
    if (table, col) not in {('county', 'County_Id'), ('county', 'Population'), ('party', 'Party_ID'),
                            ('election', 'Election_ID')}:
        return values
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        f = _num(v)
        if f is None:
            out.append(v)
            continue
        if f <= 0:
            f = rng.uniform(1, 100)
        out.append(int(round(f)) if float(f).is_integer() else round(f, 4))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
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
                    len(tm.primary_key), boundaries=BOUNDARIES.get((t, cm.name)))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pool = _parent_key_pool(schema, inst, pt, pc)
            if pool:
                cols[cm.name] = [rng.choice(pool) for _ in range(n)]
            else:
                cols[cm.name] = [None] * n
        for cm in tm.columns:
            if cm.pk_pos > 0 and (t, cm.name) not in schema.fks:
                cols[cm.name] = _fresh_pk_values(schema, t, cm.name, n, rng)
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            if (t, cm.name) in NULL_TARGETS:
                n_null = max(1, int(round(n * rng.uniform(0.05, 0.30))))
            else:
                n_null = 1 if n > 0 else 0
            cols[cm.name] = _plant_nulls(cols[cm.name], n_null, rng)
        for cm in tm.columns:
            if (t, cm.name) in DUP_COLUMNS:
                cols[cm.name] = _dup_share(cols[cm.name], rng)
        for cm in tm.columns:
            if (t, cm.name) in {('county', 'County_Id'), ('county', 'County_name'), ('party', 'Party'),
                                ('election', 'Party'), ('election', 'District')}:
                cols[cm.name] = _group_sizes(cols[cm.name], rng)
        for cm in tm.columns:
            cols[cm.name] = _apply_formula_bounds(t, cm.name, cols[cm.name], rng)
            cols[cm.name] = _apply_positive(t, cm.name, cols[cm.name], rng)
        inst[t] = cols
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
    return {t: inst[t] for t in schema.tables}
