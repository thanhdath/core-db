"""Random instance construction (fuzz/fuzz.py:83-196) plus the specification's by-construction rules."""
import datetime as dt

from .values import _init_sampler


NUM_BOUNDARIES = {
    ('PlayerInfo', 'weight'): [189, 190, 191],
    ('PlayerInfo', 'birthyear'): [1979, 1980, 1981, 1982, 1983],
    ('PlayerInfo', 'height'): [199, 200, 201],
    ('height_info', 'height_in_cm'): [-1, 0, 1, 199, 200, 201],
    ('weight_info', 'weight_in_kg'): [81, 82, 83, 89, 90, 91],
}

STR_BOUNDARIES = {
    ('PlayerInfo', 'PlayerName'): ['Ian Schultz', 'ian schultz', 'Yevgeni Muratov', 'yevgeni muratov',
                                   'Pavel Brendl', 'pavel brendl'],
    ('PlayerInfo', 'nation'): ['Russia', 'russia', 'Sweden', 'sweden'],
    ('SeasonStatus', 'SEASON'): ['2004-2005', '2004-2006', '2003', '2004', '2005', '2006'],
    ('SeasonStatus', 'GAMETYPE'): ['Regular Season', 'regular season', 'Playoffs', 'playoffs'],
    ('PlayerInfo', 'birthdate'): ['1979-12-31', '1980-01-01', '1980-12-31', '1981-01-01'],
}

ENUMS = {
    ('PlayerInfo', 'shoots'): ['L', 'R', '-'],
    ('PlayerInfo', 'GP_greater_than_0'): ['yes', 'no'],
    ('SeasonStatus', 'GAMETYPE'): ['Regular Season', 'Playoffs'],
}

INT_RANGES = {
    ('height_info', 'height_in_cm'): (150, 220),
    ('weight_info', 'weight_in_kg'): (60, 120),
    ('weight_info', 'weight_in_lbs'): (130, 270),
    ('PlayerInfo', 'birthyear'): (1960, 2005),
    ('PlayerInfo', 'birthmonth'): (1, 12),
    ('PlayerInfo', 'birthday'): (1, 31),
    ('PlayerInfo', 'draftround'): (1, 9),
    ('PlayerInfo', 'overall'): (1, 300),
    ('PlayerInfo', 'CSS_rank'): (1, 300),
    ('PlayerInfo', 'sum_7yr_GP'): (0, 500),
    ('PlayerInfo', 'sum_7yr_TOI'): (0, 5000),
    ('SeasonStatus', 'GP'): (0, 82),
    ('SeasonStatus', 'G'): (0, 60),
    ('SeasonStatus', 'A'): (0, 80),
    ('SeasonStatus', 'PIM'): (0, 200),
    ('SeasonStatus', 'PLUSMINUS'): (-50, 50),
}

NULL_TARGETS = {
    ('SeasonStatus', 'G'): 0.15,
    ('SeasonStatus', 'A'): 0.15,
    ('PlayerInfo', 'weight'): 0.10,
    ('SeasonStatus', 'ELITEID'): 0.10,
}

TIE_MAX = {
    ('SeasonStatus', 'P'), ('SeasonStatus', 'PIM'), ('PlayerInfo', 'ELITEID'),
    ('PlayerInfo', 'PlayerName'), ('PlayerInfo', 'sum_7yr_GP'), ('PlayerInfo', 'sum_7yr_TOI'),
}

DUP_COLUMNS = {('PlayerInfo', 'PlayerName'), ('SeasonStatus', 'TEAM')}

DERIVED = {('PlayerInfo', 'birthdate'), ('SeasonStatus', 'P')}

DEFAULT_NULL_SHARE = 0.10


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
    """Uniform rand_lin sizes w.p."""
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


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _spec_int(key, rng, base_sampler):
    """Integer value honouring the column's range and boundary literals."""
    lo, hi = INT_RANGES.get(key, (None, None))
    bounds = NUM_BOUNDARIES.get(key, [])
    r = rng.random()
    if bounds and r < 0.35:
        v = rng.choice(bounds)
    elif lo is not None and r < 0.75:
        v = rng.randint(lo, hi)
    else:
        v = base_sampler.sample()
        try:
            v = int(round(float(v)))
        except (TypeError, ValueError):
            v = rng.randint(lo, hi) if lo is not None else 0
    if lo is not None:
        v = _clamp(v, lo, hi)
    return v


def _spec_str(key, rng, base_sampler):
    """String value honouring the column's boundary literals / near-variants."""
    bounds = STR_BOUNDARIES.get(key, [])
    if bounds and rng.random() < 0.4:
        return rng.choice(bounds)
    return base_sampler.sample()


def _spec_enum(key, rng):
    return rng.choice(ENUMS[key])


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs in a nullable column: at least one, share following the compact DB."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n - 1) if n > 1 else 1
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def _plant_ties(values: list, rng) -> list:
    """Ensure at least two rows share the maximum value (ORDER/LIMIT tie)."""
    if len(values) < 2:
        return values
    non_null = [v for v in values if v is not None]
    if not non_null:
        return values
    mx = max(non_null)
    holders = [i for i, v in enumerate(values) if v == mx]
    if len(holders) >= 2:
        return values
    cand = [i for i, v in enumerate(values) if v is not None and v != mx]
    if cand:
        values[rng.choice(cand)] = mx
    return values


def _plant_duplicates(values: list, rng) -> list:
    """Ensure 20-50% of values are duplicates of other rows (DISTINCT columns)."""
    n = len(values)
    if n < 4:
        return values
    target = max(1, int(round(rng.uniform(0.2, 0.5) * n)))
    idx = rng.sample(range(n), min(target, n - 1))
    for i in idx:
        j = rng.randrange(n)
        if j != i:
            values[i] = values[j]
    return values


def _derive_birthdate(row: dict):
    """birthdate = printf('%04d-%02d-%02d', birthyear, birthmonth, birthday)."""
    y, m, d = row.get('birthyear'), row.get('birthmonth'), row.get('birthday')
    if y is None or m is None or d is None:
        return None
    try:
        return dt.date(int(y), int(m), int(d)).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def _derive_p(row: dict):
    """P = G + A (only when both operands are non-NULL)."""
    g, a = row.get('G'), row.get('A')
    if g is None or a is None:
        return None
    return int(g) + int(a)


def _parent_key_pool(inst: dict, pt: str, pc: str) -> list:
    """Distinct non-NULL values of the parent's FINAL (post-dedup) key column."""
    vals = inst.get(pt, {}).get(pc) or []
    seen, out = set(), []
    for v in vals:
        if v is None:
            continue
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _remap_fk(values: list, pool: list, rng) -> list:
    """Map every non-NULL FK value into the parent's final key pool (or NULL if the pool is empty)."""
    if not pool:
        return [None] * len(values)
    pset = set(pool)
    return [v if (v is None or v in pset) else rng.choice(pool) for v in values]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied by construction."""
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
            key = (t, cm.name)
            if key in samplers:
                s = samplers[key]
                if key in ENUMS:
                    vals = [_spec_enum(key, rng) for _ in range(n)]
                elif key in INT_RANGES or key in NUM_BOUNDARIES:
                    vals = [_spec_int(key, rng, s) for _ in range(n)]
                elif key in STR_BOUNDARIES:
                    vals = [_spec_str(key, rng, s) for _ in range(n)]
                else:
                    vals = [s.sample() for _ in range(n)]
                cols[cm.name] = vals
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                pt, pc = schema.fks[key]
                pool = _parent_key_pool(inst, pt, pc)
                cols[cm.name] = [rng.choice(pool) for _ in range(n)] if pool else [None] * n
        inst[t] = cols
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        if t == 'PlayerInfo' and 'birthdate' in cols:
            cols['birthdate'] = [_derive_birthdate({c: cols[c][i] for c in cols}) for i in range(n)]
        if t == 'SeasonStatus' and 'P' in cols:
            cols['P'] = [_derive_p({c: cols[c][i] for c in cols}) for i in range(n)]
        for cm in tm.columns:
            key = (t, cm.name)
            if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
                continue
            share = NULL_TARGETS.get(key, DEFAULT_NULL_SHARE)
            cols[cm.name] = _plant_nulls(list(cols[cm.name]), share, rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in TIE_MAX and cm.name in cols:
                cols[cm.name] = _plant_ties(list(cols[cm.name]), rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in DUP_COLUMNS and cm.name in cols and cm.pk_pos == 0:
                cols[cm.name] = _plant_duplicates(list(cols[cm.name]), rng)
        inst[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        if not cols:
            continue
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks or cm.name not in cols:
                continue
            pt, pc = schema.fks[key]
            pool = _parent_key_pool(inst, pt, pc)
            cols[cm.name] = _remap_fk(list(cols[cm.name]), pool, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
