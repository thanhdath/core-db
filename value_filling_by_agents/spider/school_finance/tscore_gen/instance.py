"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec-driven samplers."""
from . import spec
from .values import EnumSampler, TextPercentSampler, NumberSampler, StringSampler


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


def choose_table_sizes(schema, rng) -> dict:
    """Round-1: fixed per-instance sizes from the specification (table_sizes_per_instance)."""
    return {t: int(spec.TABLE_SIZES.get(t, 0)) for t in schema.tables}


def _enum_sampler(values, rng):
    return EnumSampler(values, rng)


def _int_sampler(domain, boundary, rng, p=0.2):
    return NumberSampler([], p, float('inf'), rng, is_int=True, domain=domain, boundary=boundary)


def _real_sampler(domain, boundary, rng, p=0.2, precision=2):
    return NumberSampler([], p, float('inf'), rng, is_int=False, precision=precision,
                         domain=domain, boundary=boundary)


def _plant_group_sizes(values: list, targets: list, rng) -> list:
    """Reorder/duplicate values so that group sizes hit 1, 2 and >=3 (in order)."""
    if not values:
        return values
    out = []
    pool = list(values)
    rng.shuffle(pool)
    for t in targets:
        for _ in range(t):
            if pool:
                out.append(pool.pop())
            else:
                out.append(rng.choice(values))
    while pool:
        out.append(pool.pop())
    return out


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs on a nullable column: share of rows, at least one."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _compact_null_share(schema, table: str, column: str) -> float:
    """Per-column NULL share from the compact database (fallback spec.NULL_SHARE)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return spec.NULL_SHARE
    n_null = sum(1 for v in vals if v is None)
    share = n_null / float(len(vals))
    return share if share > 0 else spec.NULL_SHARE


def _compact_max_int(schema, table: str, column: str) -> int:
    """Max integer value of a compact column (0 if none)."""
    best = 0
    for v in schema.original_values.get((table, column), []):
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv > best:
            best = iv
    return best


def _build_school(schema, literal_pool, n, rng) -> dict:
    cols = {}
    base = _compact_max_int(schema, 'School', 'School_id')
    cols['School_id'] = [str(base + i + 1) for i in range(n)]
    names = [rng.choice(spec.SCHOOL_NAME_POOL) for _ in range(n)]
    names = _plant_group_sizes(names, spec.GROUP_SIZE_TARGETS, rng)
    cols['School_name'] = names
    cols['Location'] = [rng.choice(spec.LOCATION_POOL) for _ in range(n)]
    mascots = [rng.choice(spec.MASCOT_POOL) for _ in range(n)]
    mascots = _plant_group_sizes(mascots, spec.GROUP_SIZE_TARGETS, rng)
    cols['Mascot'] = _plant_nulls(mascots, _compact_null_share(schema, 'School', 'Mascot'), rng)
    enr = _int_sampler(spec.ENROLLMENT_RANGE, [], rng)
    cols['Enrollment'] = [enr.sample() for _ in range(n)]
    cls = _enum_sampler(spec.IHSAA_CLASS, rng)
    fcls = _enum_sampler(spec.IHSAA_FOOTBALL_CLASS, rng)
    cols['IHSAA_Class'] = [cls.sample() for _ in range(n)]
    cols['IHSAA_Football_Class'] = [fcls.sample() for _ in range(n)]
    cols['County'] = [rng.choice(spec.COUNTY_POOL) for _ in range(n)]
    for c in ('School_name', 'Location', 'Enrollment', 'IHSAA_Class', 'IHSAA_Football_Class', 'County'):
        cols[c] = _plant_nulls(cols[c], _compact_null_share(schema, 'School', c), rng)
    return cols


def _build_budget(schema, literal_pool, n, rng, school_ids: list) -> dict:
    cols = {}
    if school_ids:
        fk = [rng.choice(school_ids) for _ in range(n)]
        if n >= 1:
            fk[0] = school_ids[spec.UNMATCHED_BUDGET_SCHOOL_INDEX % len(school_ids)]
        cols['School_id'] = fk
    else:
        cols['School_id'] = [None] * n
    yr = _int_sampler(spec.YEAR_RANGE, spec.YEAR_BOUNDARY, rng)
    cols['Year'] = [yr.sample() for _ in range(n)]
    bud = _int_sampler(spec.BUDGETED_RANGE, spec.BUDGETED_BOUNDARY, rng)
    cols['Budgeted'] = [bud.sample() for _ in range(n)]
    inv = _int_sampler(spec.INVESTED_RANGE, spec.INVESTED_BOUNDARY, rng)
    cols['Invested'] = [inv.sample() for _ in range(n)]
    pb = _real_sampler(spec.PERCENT_BUDGETED_RANGE, [], rng, precision=1)
    pi = _real_sampler(spec.PERCENT_INVESTED_RANGE, [], rng, precision=1)
    cols['total_budget_percent_budgeted'] = [pb.sample() for _ in range(n)]
    cols['total_budget_percent_invested'] = [pi.sample() for _ in range(n)]
    tp = TextPercentSampler(rng)
    cols['Budget_invested_percent'] = [tp.sample() for _ in range(n)]
    for c in ('Budgeted', 'total_budget_percent_budgeted', 'Invested',
              'total_budget_percent_invested', 'Budget_invested_percent'):
        cols[c] = _plant_nulls(cols[c], _compact_null_share(schema, 'budget', c), rng)
    return cols


def _build_endowment(schema, literal_pool, n, rng, school_ids: list) -> dict:
    cols = {}
    base = _compact_max_int(schema, 'endowment', 'endowment_id')
    cols['endowment_id'] = list(range(base + 1, base + 1 + n))
    if school_ids:
        fk = [rng.choice(school_ids) for _ in range(n)]
        fk = _plant_group_sizes(fk, spec.GROUP_SIZE_TARGETS, rng)
        if n >= 1:
            fk[0] = school_ids[spec.MATCHED_ENDOWMENT_SCHOOL_INDEX % len(school_ids)]
        if n >= 2:
            fk[-1] = None
        cols['School_id'] = fk
    else:
        cols['School_id'] = [None] * n
    names = [rng.choice(spec.DONATOR_POOL) for _ in range(n)]
    names = _plant_group_sizes(names, spec.GROUP_SIZE_TARGETS, rng)
    cols['donator_name'] = _plant_nulls(names, _compact_null_share(schema, 'endowment', 'donator_name'), rng)
    amt = _real_sampler(spec.AMOUNT_RANGE, spec.AMOUNT_BOUNDARY, rng, precision=2)
    vals = [amt.sample() for _ in range(n)]
    if n >= 2:
        i = rng.randrange(n)
        j = rng.randrange(n)
        if i != j:
            vals[j] = vals[i]
    cols['amount'] = _plant_nulls(vals, _compact_null_share(schema, 'endowment', 'amount'), rng)
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with round-1 spec-driven samplers."""
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    n_school = int(size.get('School', 0))
    school_cols = _build_school(schema, literal_pool, n_school, rng)
    school_cols = sample_fresh_primary_keys(schema.tables['School'], school_cols)
    inst['School'] = school_cols
    school_ids = [v for v in school_cols.get('School_id', []) if v is not None]
    n_budget = int(size.get('budget', 0))
    budget_cols = _build_budget(schema, literal_pool, n_budget, rng, school_ids)
    budget_cols = sample_fresh_primary_keys(schema.tables['budget'], budget_cols)
    inst['budget'] = budget_cols
    n_end = int(size.get('endowment', 0))
    end_cols = _build_endowment(schema, literal_pool, n_end, rng, school_ids)
    end_cols = sample_fresh_primary_keys(schema.tables['endowment'], end_cols)
    inst['endowment'] = end_cols
    return {t: inst[t] for t in schema.tables}
