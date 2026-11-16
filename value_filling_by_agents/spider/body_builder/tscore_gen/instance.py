"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec construction."""
from . import spec
from .values import (_init_sampler, _null_mask, sample_lift, sample_people_birth_date,
                     sample_people_birth_place, sample_people_height, sample_people_name,
                     sample_people_weight, sample_total)


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
    """FK child columns draw from the parent's values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
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
    """Spec table sizes when known, else upstream rand_lin / level sizes (fuzz.py:83-110)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            if t in spec.TABLE_SIZES:
                sizes[t] = spec.TABLE_SIZES[t]
    if sizes:
        for lvl in schema.table_order:
            for t in lvl:
                sizes.setdefault(t, 0)
        return sizes
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


def _max_pk(schema, table: str) -> int:
    """Largest existing integer primary-key value in the compact table (0 if none)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 0
    pk = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _spec_columns(schema, table: str, n: int, rng, pool: dict) -> dict:
    """Spec-driven column values for the named tables (round 1)."""
    cols: dict = {}
    if table == 'people':
        cols['Name'] = sample_people_name(n, rng, pool.get((table, 'Name'), []))
        cols['Height'] = sample_people_height(n, rng, pool.get((table, 'Height'), []))
        cols['Weight'] = sample_people_weight(n, rng)
        cols['Birth_Date'] = sample_people_birth_date(n, rng)
        cols['Birth_Place'] = sample_people_birth_place(n, rng)
    elif table == 'body_builder':
        snatch = sample_lift(n, rng, pool.get((table, 'Snatch'), []))
        clean = sample_lift(n, rng, pool.get((table, 'Clean_Jerk'), []))
        cols['Snatch'] = snatch
        cols['Clean_Jerk'] = clean
        cols['Total'] = sample_total(n, rng, snatch, clean)
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with round-1 spec construction."""
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
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        spec_cols = _spec_columns(schema, t, n, rng, literal_pool)
        for c, vals in spec_cols.items():
            if c in cols:
                cols[c] = vals
        if tm.primary_key:
            pk = tm.primary_key[0]
            base = _max_pk(schema, t)
            cols[pk] = [base + 1 + i for i in range(n)]
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk_cols)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks and not cm.notnull and cm.pk_pos == 0:
                mask = _null_mask(n, rng)
                cols[cm.name] = [None if mask[i] else cols[cm.name][i] for i in range(n)]
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0 or (t, cm.name) in schema.fks:
                continue
            if cm.name in cols and any(v is not None for v in cols[cm.name]):
                mask = _null_mask(n, rng)
                cols[cm.name] = [None if mask[i] else cols[cm.name][i] for i in range(n)]
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
