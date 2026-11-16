"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec overlay."""
from .spec import build_spec_instance, TABLE_SIZES, NULL_TARGETS
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
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
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
    """Spec sizes per instance (table_sizes_per_instance)."""
    return dict(TABLE_SIZES)


def _fresh_pk_start(schema, table: str) -> int:
    """First PK value above the compact rows (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 1
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, (int, float))]
    return int(max(vals)) + 1 if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance's generated rows (spec overlay + generic samplers)."""
    spec = build_spec_instance(schema, literal_pool, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        cols = spec.get(t, {})
        n = len(next(iter(cols.values()))) if cols else 0
        if tm.primary_key and n:
            start = _fresh_pk_start(schema, t)
            if len(tm.primary_key) == 1:
                cols[tm.primary_key[0]] = list(range(start, start + n))
        for cm in tm.columns:
            if cm.name in cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            s = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                              schema.original_values.get((t, cm.name), []), 0.2, rng,
                              len(tm.primary_key))
            cols[cm.name] = [s.sample() for _ in range(n)]
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for c, v in fk_cols.items():
            if c not in cols or all(x is None for x in cols.get(c, [])):
                cols[c] = v
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
