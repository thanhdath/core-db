"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
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
    """Specification table sizes (spec.TABLE_SIZES), with a small per-instance jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 10
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, base + jitter)
    return sizes


def _parent_pool(schema, instance, table, col):
    """Parent key pool = compact rows + generated rows (in memory)."""
    vals = [r.get(col) for r in schema.original_rows.get(table, []) if r.get(col) is not None]
    vals += [v for v in instance.get(table, {}).get(col, []) if v is not None]
    return vals


def _apply_null_rule(schema, table, cols, n, rng):
    """NULL rule: at least one NULL per nullable column; share follows compact share."""
    for cm in schema.tables[table].columns:
        key = '%s.%s' % (table, cm.name)
        if key not in spec.NULL_TARGETS or cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        share = schema.null_share.get((table, cm.name), 0.0)
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k) if k < n else list(range(n))
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _apply_formulas(schema, table, cols, n):
    """Semantic formulas by construction: clamp non-negative, FTE_AY <= TotalEnrollment_AY."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key in spec.FORMULAS and cm.name in cols:
            for i in range(n):
                v = cols[cm.name][i]
                if v is not None and isinstance(v, (int, float)) and v < 0:
                    cols[cm.name][i] = abs(v)
    if table == 'enrollments' and 'FTE_AY' in cols and 'TotalEnrollment_AY' in cols:
        for i in range(n):
            f, t = cols['FTE_AY'][i], cols['TotalEnrollment_AY'][i]
            if f is not None and t is not None and f > t:
                cols['FTE_AY'][i] = t
    return cols


def _plant_ties(schema, table, cols, n, rng):
    """Tie at rank 1 for ORDER DESC columns (spec: ties_for_order_limit)."""
    if table == 'degrees' and 'Degrees' in cols and n >= 2:
        v = rng.randint(500, 900)
        cols['Degrees'][0] = v
        cols['Degrees'][1] = v
    if table == 'csu_fees' and 'CampusFee' in cols and n >= 2:
        v = rng.randint(1700, 2100)
        cols['CampusFee'][0] = v
        cols['CampusFee'][1] = v
    return cols


def _plant_duplicates(schema, table, cols, n, rng):
    """Duplicate share 20-50 % on DISTINCT columns (spec: duplicates_for_distinct)."""
    if table == 'Campuses' and 'Campus' in cols and n >= 3:
        share = rng.uniform(*spec.DUP_SHARE)
        k = max(1, int(round(share * n)))
        for i in range(1, min(k, n)):
            cols['Campus'][i] = cols['Campus'][0]
    if table == 'csu_fees' and 'Campus' in cols and n >= 3:
        share = rng.uniform(*spec.DUP_SHARE)
        k = max(1, int(round(share * n)))
        for i in range(1, min(k, n)):
            cols['Campus'][i] = cols['Campus'][0]
    return cols


def _plant_group_sizes(schema, table, cols, n, rng):
    """Group sizes 1, 2 and >= 3 for GROUP BY columns (spec: group_sizes)."""
    if table == 'Campuses' and 'Campus' in cols and n >= 6:
        plan = spec.GROUP_SIZE_PLAN
        pos = 0
        for g in plan:
            if pos >= n:
                break
            base = cols['Campus'][pos]
            for j in range(1, g):
                if pos + j < n:
                    cols['Campus'][pos + j] = base
            pos += g
    if table == 'degrees' and 'Year' in cols and n >= 6:
        plan = spec.GROUP_SIZE_PLAN
        pos = 0
        for g in plan:
            if pos >= n:
                break
            base = cols['Year'][pos]
            for j in range(1, g):
                if pos + j < n:
                    cols['Year'][pos + j] = base
            pos += g
    return cols


def _plant_boundaries(schema, table, cols, n, rng, samplers):
    """Plant boundary values from the spec pools (comparison_boundary)."""
    for cm in schema.tables[table].columns:
        key = '%s.%s' % (table, cm.name)
        if cm.name not in cols:
            continue
        s = samplers.get((table, cm.name))
        if s is None or not s.boundary:
            continue
        if key in spec.YEAR_BOUNDARY or key in spec.NUM_BOUNDARY or key in (
                'Campuses.Campus', 'Campuses.Location', 'Campuses.County'):
            k = min(n, max(1, n // 4))
            for i in range(k):
                cols[cm.name][i] = s.sample_boundary()
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
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
        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = _parent_pool(schema, inst, pt, pc)
            cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        cols = _plant_boundaries(schema, t, cols, n, rng, samplers)
        cols = _plant_ties(schema, t, cols, n, rng)
        cols = _plant_duplicates(schema, t, cols, n, rng)
        cols = _plant_group_sizes(schema, t, cols, n, rng)
        cols = _apply_formulas(schema, t, cols, n)
        cols = _apply_null_rule(schema, t, cols, n, rng)
        cols = _dedup_against_compact(schema, t, cols, n)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
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


def _dedup_against_compact(schema, table, cols, n):
    """Drop generated rows whose PK tuple already exists in the compact table."""
    tm = schema.tables[table]
    if not tm.primary_key or not cols:
        return cols
    existing = set()
    for r in schema.original_rows.get(table, []):
        existing.add(tuple(r.get(c) for c in tm.primary_key))
    keep = []
    for i in range(n):
        k = tuple(cols[c][i] for c in tm.primary_key if c in cols)
        if k not in existing:
            keep.append(i)
    return _filter(cols, keep)
