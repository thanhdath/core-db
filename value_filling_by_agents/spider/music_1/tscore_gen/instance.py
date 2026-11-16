"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler, spec_sampler_for


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


def _parent_values(schema, instance, pt: str, pc: str) -> list:
    """Parent values = compact rows + generated rows (kept in memory)."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (spec.TABLE_SIZES), with small variation."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 6)
        sizes[t] = max(0, base + rng.randint(-1, 1))
    return sizes


def _apply_null_rule(table: str, columns: dict, schema, rng) -> dict:
    """For every nullable column, plant at least one NULL row (never replaced later)."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        key = '%s.%s' % (table, cm.name)
        if key not in spec.NULL_TARGETS:
            continue
        if cm.name not in columns:
            continue
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if any(v is None for v in columns[cm.name]):
            continue
        i = rng.randrange(n)
        columns[cm.name][i] = None
    return columns


def _apply_range_rules(table: str, columns: dict) -> dict:
    """Semantic range rules by construction (rating, resolution, f_id)."""
    if table == 'song':
        if 'rating' in columns:
            columns['rating'] = [None if v is None else min(max(int(v), spec.RATING_MIN), spec.RATING_MAX)
                                 for v in columns['rating']]
        if 'resolution' in columns:
            columns['resolution'] = [max(int(v), spec.RESOLUTION_MIN) for v in columns['resolution']]
    if table == 'files' and 'f_id' in columns:
        columns['f_id'] = [max(int(v), spec.F_ID_MIN) for v in columns['f_id']]
    return columns


def _fresh_pk_values(table: str, cm, n: int, schema, rng) -> list:
    """Fresh primary-key values that do not collide with compact rows."""
    existing = {v for v in schema.original_values.get((table, cm.name), []) if v is not None}
    out, seen = [], set(existing)
    if cm.type_str and any(k in cm.type_str.lower() for k in ('int', 'number', 'real', 'float')):
        start = (max([int(v) for v in existing if isinstance(v, (int, float))] or [0])) + 1
        for k in range(n):
            v = start + k
            while v in seen:
                v += 1
            seen.add(v)
            out.append(v)
    else:
        for k in range(n):
            v = '%s_%d' % (table, rng.randint(1, 10 ** 6))
            while v in seen:
                v = '%s_%d' % (table, rng.randint(1, 10 ** 6))
            seen.add(v)
            out.append(v)
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of *generated* rows (fuzz.py:111-196), spec-driven."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = spec_sampler_for(t, cm.name, schema, literal_pool.get((t, cm.name), []), rng)
            if s is None:
                s = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                  schema.original_values.get((t, cm.name), []), p, rng,
                                  len(tm.primary_key))
            samplers[(t, cm.name)] = s
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                cols[cm.name] = _fresh_pk_values(t, cm, n, schema, rng)
            else:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
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
        cols = _apply_range_rules(t, cols)
        cols = _apply_null_rule(t, cols, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
