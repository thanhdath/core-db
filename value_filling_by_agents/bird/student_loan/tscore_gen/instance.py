"""Random instance construction (fuzz/fuzz.py:83-196) with specification-driven samplers."""
from .spec import (AGG_TIES, DUP_SHARES, NULL_SHARES, TABLE_SIZES, apply_column_rules,
                   enforce_duplicate_share, make_spec_sampler, plant_aggregate_tie)
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
    """FK child columns draw from the parent's FINAL (post-dedup) values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
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
    """Use the exact specification table sizes (spec: table_sizes_per_instance)."""
    return {t: TABLE_SIZES.get(t, 20) for t in schema.tables}


def _observed_null_share(schema, table: str, col: str):
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return None
    return sum(1 for v in vals if v is None) / len(vals)


def _ensure_null(values: list, rng) -> list:
    """Guarantee at least one NULL row for a nullable column (program-interface NULL rule)."""
    if not values:
        return values
    if any(v is None for v in values):
        return values
    out = list(values)
    out[rng.randrange(len(out))] = None
    return out


def _apply_null_share(values: list, share: float, rng) -> list:
    """Set a fraction of positions to NULL (keeping at least one NULL)."""
    if not values:
        return values
    out = list(values)
    n = len(out)
    n_null = max(1, int(n * share))
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs[:n_null]:
        out[i] = None
    return out


def _null_share_for(schema, table: str, col: str, rng) -> float:
    """NULL share for a nullable FK column, derived from the compact database."""
    lo, hi = NULL_SHARES.get((table, col), (0.0, 0.0))
    if hi <= 0:
        return 0.0
    obs = _observed_null_share(schema, table, col)
    if obs is not None:
        return min(hi, max(lo, obs))
    return rng.uniform(lo, hi)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) using spec-aware samplers."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = make_spec_sampler(
                    t, cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key),
                    observed_null_share=_observed_null_share(schema, t, cm.name))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = apply_column_rules(t, cm.name, cols[cm.name], rng)
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk_cols)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in fk_cols and key in NULL_SHARES:
                share = _null_share_for(schema, t, cm.name, rng)
                cols[cm.name] = _apply_null_share(cols[cm.name], share, rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in fk_cols and key in DUP_SHARES:
                lo, hi = DUP_SHARES[key]
                share = rng.uniform(lo, hi)
                cols[cm.name] = enforce_duplicate_share(cols[cm.name], share, rng)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                cols[cm.name] = _ensure_null(cols[cm.name], rng)
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
