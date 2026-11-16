"""Random instance construction (fuzz/fuzz.py:83-196, patch 64: spec-driven)."""
from .spec import SPEC, TABLE_SIZES, build_column
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (in the instance or in the compact table)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
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


def _compact_primary_keys(schema, table: str) -> set:
    """Compact table's primary-key tuples (as tuples)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    if not cols:
        return set()
    n = len(cols[0])
    return {tuple(c[i] for c in cols) for i in range(n)}


def _compact_foreign_keys(schema, table: str, col: str) -> list:
    """Compact parent values for a child FK column."""
    return schema.original_values.get((table, col), [])


def _next_primary_values(schema, table: str, n: int) -> list:
    """Fresh integer PK values starting after the compact max."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return []
    pk = tm.primary_key[0]
    vals = schema.original_values.get((table, pk), [])
    ints = [v for v in vals if isinstance(v, int)]
    start = (max(ints) + 1) if ints else 1
    return list(range(start, start + n))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from parent values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += _compact_foreign_keys(schema, pt, pc)
        if pv:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
        else:
            out[cm.name] = [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Per-instance table sizes: the specification's sizes, with a small jitter."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 8)
        jitter = rng.choice([-1, 0, 0, 1])
        sizes[t] = max(1, base + jitter)
    return sizes


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (compact rows kept as-is; generated rows appended)."""
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
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                spec = SPEC.get(t, {}).get(cm.name)
                if spec is not None:
                    cols[cm.name] = build_column(rng, spec, n, spec.get('null_share', 0.0))
                else:
                    cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        taken = _compact_primary_keys(schema, t)
        if len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            fresh = _next_primary_values(schema, t, n)
            if fresh:
                cols[tm.primary_key[0]] = fresh
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
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
