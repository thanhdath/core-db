"""Random instance construction (fuzz/fuzz.py:83-196) with the generation specification applied by construction."""
import re

from .values import _init_sampler, make_column_sampler

SPEC_SIZES = {'actor': 40, 'director': 30, 'producer': 25, 'writer': 25, 'company': 20, 'genre': 12,
              'keyword': 20, 'movie': 60, 'tv_series': 20, 'copyright': 80, 'cast': 120,
              'classification': 80, 'directed_by': 80, 'made_by': 80, 'tags': 80, 'written_by': 80}

BOUNDARY = {
    ('movie', 'title'): ['Saving Private Ryan', 'saving private ryan', 'Rush Hour 3', 'rush hour 3',
                         'Jim Jarmusch', 'jim jarmusch'],
    ('movie', 'mid'): ['Steven Spielberg', 'steven spielberg', 'China', 'china'],
    ('actor', 'name'): ['Humphrey Bogart', 'humphrey bogart', 'Shahab Hosseini', 'shahab hosseini',
                        'Jennifer Aniston', 'jennifer aniston'],
    ('director', 'name'): ['Quentin Tarantino', 'quentin tarantino', 'Jim Jarmusch', 'jim jarmusch',
                           'Steven Spielberg', 'steven spielberg'],
    ('movie', 'release_year'): [2001, 2002, 2003, 2009, 2010, 2011],
    ('actor', 'birth_city'): ['New York City', 'new york city', 'Los Angeles', 'los angeles', ' ', ' x'],
    ('keyword', 'keyword'): ['Persians', 'persians', 'Iraq war', 'iraq war', '', 'x'],
    ('actor', 'nationality'): ['China', 'china', 'Iran', 'iran', 'New York City', 'new york city'],
    ('actor', 'birth_year'): [1979, 1980, 1981, 1999, 2000, 2001],
    ('actor', 'gender'): ['female', 'FEMALE', 'F', 'f'],
    ('director', 'nationality'): ['Iran', 'iran', 'China', 'china'],
}

LIKE_VARIANTS = {
    ('movie', 'title'): (['%Persians%', '% Iraq%'],
                         ['Persians', 'Persiant', 'Persians x', 'persians', ' Iraq', ' Irar', ' Iraq x', ' iraq']),
    ('movie', 'title_aka'): (['%Iraq-war%', '%Persians%', '%Persian%'],
                             ['Iraq-war', 'Iraq-was', 'Iraq-war x', 'iraq-war', 'Persians', 'Persiant',
                              'Persians x', 'persians']),
}

DUP_SHARE = {('movie', 'title'): 0.35, ('actor', 'name'): 0.35}

GENDER_ENUM = ('male', 'female', 'M', 'F', 'm', 'f')

TYPE_OVERRIDE = {('writer', 'name'): 'text', ('writer', 'nationality'): 'text'}

NULL_SHARE = 0.10


def _rule_gender(v):
    if v is None:
        return None
    s = str(v)
    if s in GENDER_ENUM:
        return s
    low = s.lower()
    if low.startswith('f'):
        return 'female'
    if low.startswith('m'):
        return 'male'
    return GENDER_ENUM[hash(s) % 2]


def _rule_year(v):
    if v is None:
        return None
    try:
        y = int(v)
    except (TypeError, ValueError):
        return 2000
    return min(2024, max(1900, y))


def _rule_positive(v):
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 1
    return n if n > 0 else 1


def _rule_nonneg(v):
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def _rule_country(v):
    if v is None:
        return None
    s = re.sub(r'[^A-Za-z]', '', str(v)).upper()
    if len(s) >= 2:
        return s[:2]
    return (s + 'XX')[:2]


RULES = {
    ('actor', 'birth_year'): _rule_year, ('director', 'birth_year'): _rule_year,
    ('producer', 'birth_year'): _rule_year, ('writer', 'birth_year'): _rule_year,
    ('movie', 'release_year'): _rule_year, ('tv_series', 'release_year'): _rule_year,
    ('actor', 'gender'): _rule_gender, ('director', 'gender'): _rule_gender,
    ('producer', 'gender'): _rule_gender, ('writer', 'gender'): _rule_gender,
    ('tv_series', 'num_of_seasons'): _rule_positive, ('tv_series', 'num_of_episodes'): _rule_positive,
    ('writer', 'num_of_episodes'): _rule_nonneg, ('cast', 'role'): _rule_nonneg,
    ('company', 'country_code'): _rule_country,
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


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs at ``share`` (at least one) into a list of sampled values, in place."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        vals = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        if not cm.notnull and cm.pk_pos == 0:
            vals = _plant_nulls(vals, NULL_SHARE, rng)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec_sizes=None) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    elif spec_sizes:
        for lvl in schema.table_order:
            for t in lvl:
                base = spec_sizes.get(t, 30)
                j = 0.8 + 0.4 * rng.random()
                sizes[t] = max(0, int(round(base * j)))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t


def _augment_pool(table: str, col: str, pool: list, type_str: str) -> list:
    """Add comparison_boundary and like_near_variant literals to a column's value pool."""
    out = list(pool)
    is_int = _is_int_type(type_str)
    for v in BOUNDARY.get((table, col), []):
        if is_int and not re.fullmatch(r'-?\d+', str(v)):
            continue
        out.append(v)
    lits, variants = LIKE_VARIANTS.get((table, col), ([], []))
    for lit in lits:
        out.append(lit.replace('%', ''))
    out.extend(variants)
    return out


def _apply_dup_cap(sampler, share: float, n: int) -> None:
    """Lower the fresh-value cap so roughly ``share`` of rows reuse an existing value."""
    if n <= 0:
        return
    target_fresh = max(1, int(round((1.0 - share) * n)))
    sampler.max_l0 = min(getattr(sampler, 'max_l0', float('inf')), target_fresh)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                pool = _augment_pool(t, cm.name, literal_pool.get((t, cm.name), []), cm.type_str)
                samplers[(t, cm.name)] = _init_sampler(cm, pool,
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, SPEC_SIZES)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        for cm in tm.columns:
            sh = DUP_SHARE.get((t, cm.name))
            if sh is not None and (t, cm.name) in samplers:
                _apply_dup_cap(samplers[(t, cm.name)], sh, n)
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            rule = RULES.get((t, cm.name))
            if rule is not None and cm.name in cols:
                cols[cm.name] = [rule(v) for v in cols[cm.name]]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if not cm.notnull and cm.pk_pos == 0 and cm.name in cols:
                cols[cm.name] = _plant_nulls(cols[cm.name], NULL_SHARE, rng)
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
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
