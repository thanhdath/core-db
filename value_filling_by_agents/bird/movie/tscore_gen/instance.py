"""Random instance construction (fuzz/fuzz.py:83-196) with specification-driven domains."""
import re

from .values import _init_sampler, MoneySampler, ShortTextSampler, LongTextSampler, NumberSampler

SPEC_SIZES = {'actor': 40, 'movie': 40, 'characters': 80}

_INT_RANGES = {
    ('actor', 'Height (Inches)'): (50, 90),
    ('movie', 'Budget'): (0, 500000000),
    ('movie', 'Gross'): (0, 500000000),
    ('movie', 'Runtime'): (1, 200),
    ('movie', 'Rating Count'): (0, 500000000),
    ('characters', 'creditOrder'): (0, 8),
}
_REAL_RANGES = {('movie', 'Rating'): (0.0, 10.0)}
_ENUMS = {
    ('actor', 'Gender'): ['Male', 'Female'],
    ('actor', 'Ethnicity'): ['White', 'African American', 'Lebanese', 'Armenian', 'Asian', 'Latino',
                             'Native American', 'Asian American'],
    ('movie', 'MPAA Rating'): ['G', 'PG', 'PG-13', 'R'],
    ('movie', 'Genre'): ['Romance', 'Comedy', 'Crime', 'War', 'Drama', 'Family', 'Action', 'Animation',
                         'Thriller', 'thriller', 'Horror', 'Sci-Fi', 'Fantasy', 'Mystery', 'Adventure',
                         'Western', 'Musical', 'Documentary'],
}
_MONEY = {('actor', 'NetWorth'), ('characters', 'pay')}
_LONG = {('actor', 'Biography'), ('movie', 'Summary')}
_SHORT = {('actor', 'Name'), ('actor', 'Birth City'), ('actor', 'Birth Country'), ('movie', 'Title'),
          ('characters', 'Character Name')}
_TIME = {('characters', 'screentime')}

_BOUNDARY = {
    ('actor', 'Name'): ['Morgan Freeman', 'morgan freeman'],
    ('actor', 'Gender'): ['Male', 'male'],
    ('movie', 'Title'): ['Mrs. Doubtfire', 'mrs. doubtfire', 'Batman', 'batman',
                         'American Hustle', 'american hustle'],
    ('movie', 'Genre'): ['Thriller', 'thriller'],
    ('characters', 'creditOrder'): [0, 1, 2],
}

_DUPLICATES = {('actor', 'Name'), ('actor', 'Biography'), ('movie', 'Title'), ('movie', 'Runtime')}

_TIES = {
    ('actor', 'NetWorth'): lambda v: float(str(v).replace('$', '').replace(',', '')),
    ('movie', 'Rating'): lambda v: float(v),
    ('characters', 'pay'): lambda v: float(str(v).replace('$', '').replace(',', '')),
    ('characters', 'screentime'): lambda v: int(str(v).replace(':', '')),
}

_NULL_SHARE = {
    ('actor', 'Name'): 0.04,
    ('actor', 'Date of Birth'): 0.15,
    ('actor', 'Birth City'): 0.15,
    ('actor', 'Birth Country'): 0.15,
    ('actor', 'Height (Inches)'): 0.24,
    ('actor', 'Biography'): 0.06,
    ('actor', 'Gender'): 0.57,
    ('actor', 'Ethnicity'): 0.79,
    ('actor', 'NetWorth'): 0.20,
    ('movie', 'Gross'): 0.01,
    ('movie', 'Rating'): 0.01,
    ('movie', 'Rating Count'): 0.01,
    ('characters', 'pay'): 0.95,
    ('characters', 'screentime'): 0.95,
}

_LITERALS = {
    ('actor', 'Ethnicity'): ['White', 'African American'],
    ('movie', 'Gross'): [136766062],
}


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


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples=()) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195) or UNIQUE tuple."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for t, cols in unique_tuples:
        if t != table_meta.name or not all(c in columns for c in cols):
            continue
        seen, keep = set(), []
        n = len(next(iter(columns.values())))
        for i in range(n):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with per-instance variation (0-230 rows, level x4 capped at 2500)."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = SPEC_SIZES.get(t, 40)
                sizes[t] = max(0, int(base * rng.uniform(0.5, 1.5)))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _pk_start(schema, table: str, col: str) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _plant_duplicates(values: list, rng, share=(0.2, 0.5)) -> list:
    """Make 20-50% of values repeat an earlier non-NULL value (duplicates_for_distinct)."""
    n = len(values)
    if n < 2:
        return values
    k = int(n * rng.uniform(*share))
    idx = list(range(1, n))
    rng.shuffle(idx)
    for i in idx[:k]:
        src = [j for j in range(i) if values[j] is not None]
        if src:
            values[i] = values[rng.choice(src)]
    return values


def _plant_ties(values: list, rng, key, n_ties=2) -> list:
    """Force at least n_ties non-NULL numeric rows to share the numeric-key top value."""
    idx = []
    for i, v in enumerate(values):
        if v is None:
            continue
        try:
            key(v)
        except (TypeError, ValueError):
            continue
        idx.append(i)
    if len(idx) < n_ties:
        return values
    top = max((values[i] for i in idx), key=key)
    rng.shuffle(idx)
    for i in idx[:n_ties]:
        values[i] = top
    return values


def _plant_boundary(values: list, rng, pair: list) -> list:
    """Overwrite the first k rows with the listed literals exactly (comparison_boundary)."""
    if not values:
        return values
    for j, lit in enumerate(pair):
        values[j % len(values)] = lit
    return values


def _plant_nulls(values: list, rng, share: float) -> list:
    """NULL is a value: at least one NULL and ~share of rows NULL, but never all-NULL."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n - 1)
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:k]:
        values[i] = None
    return values


def _plant_literals(values: list, rng, lits: list) -> list:
    """Ensure each listed literal appears in at least one non-NULL row (specification literals)."""
    if not values or not lits:
        return values
    for j, lit in enumerate(lits):
        values[j % len(values)] = lit
    return values


def _make_sampler(schema, table, cm, literal_pool, p, rng, n_pk):
    key = (table, cm.name)
    ov = schema.original_values.get(key, [])
    pool = literal_pool.get(key, [])
    if key in _ENUMS:
        return ShortTextSampler(_ENUMS[key], 0.0, float('inf'), rng, pool_size=len(_ENUMS[key]))
    if key in _MONEY:
        top = None
        if key == ('actor', 'NetWorth'):
            top = '${:,.2f}'.format(rng.randint(400000000, 500000000))
        return MoneySampler(pool + [str(v) for v in ov if v is not None], p, float('inf'), rng, top=top,
                            lo=1000000, hi=600000000)
    if key in _LONG:
        return LongTextSampler(pool, p, float('inf'), rng)
    if key in _SHORT:
        return ShortTextSampler(pool + [str(v) for v in ov if v is not None], p, float('inf'), rng)
    if key in _TIME:
        from .values import TimeSampler
        return TimeSampler(pool + [str(v) for v in ov if v is not None], p, float('inf'), rng)
    if key in _INT_RANGES:
        lo, hi = _INT_RANGES[key]
        return NumberSampler(pool + [v for v in ov if isinstance(v, (int, float))], p, float('inf'), rng,
                             is_int=True, lo=lo, hi=hi)
    if key in _REAL_RANGES:
        lo, hi = _REAL_RANGES[key]
        return NumberSampler(pool + [v for v in ov if isinstance(v, (int, float))], p, float('inf'), rng,
                             is_int=False, precision=1, lo=lo, hi=hi)
    return _init_sampler(cm, pool, ov, p, rng, n_pk)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) appended to the compact rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                start = _pk_start(schema, t, cm.name)
                cols[cm.name] = list(range(start, start + n))
                continue
            s = _make_sampler(schema, t, cm, literal_pool, p, rng, len(tm.primary_key))
            vals = [s.sample() for _ in range(n)]
            key = (t, cm.name)
            if key in _NULL_SHARE:
                vals = _plant_nulls(vals, rng, _NULL_SHARE[key])
            if key in _DUPLICATES:
                vals = _plant_duplicates(vals, rng)
            if key in _TIES:
                vals = _plant_ties(vals, rng, _TIES[key])
            if key in _LITERALS:
                vals = _plant_literals(vals, rng, _LITERALS[key])
            if key in _BOUNDARY:
                vals = _plant_boundary(vals, rng, _BOUNDARY[key])
            cols[cm.name] = vals
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            if (t, cm.name) not in schema.fks:
                continue
            if cm.name not in cols:
                continue
            cols[cm.name] = _plant_nulls(cols[cm.name], rng, 0.08)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols, schema.unique_tuples)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
