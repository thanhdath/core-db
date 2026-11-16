"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven samplers."""
import re

from .values import _init_sampler


ENUMS = {
    ('person', 'gender'): ['M', 'F'],
    ('games', 'season'): ['Summer', 'Winter'],
    ('medal', 'medal_name'): ['Gold', 'Silver', 'Bronze', 'NA'],
}
ENUM_VARIANTS = {
    ('person', 'gender'): ['M', 'm', 'F', 'f'],
    ('games', 'season'): ['Summer', 'summer', 'Winter', 'winter'],
    ('medal', 'medal_name'): ['Gold', 'gold', 'Bronze', 'bronze', 'Silver', 'silver', 'NA', 'na'],
}
RANGES = {
    ('person', 'height'): (120, 230, True),
    ('person', 'weight'): (30, 200, True),
    ('games', 'games_year'): (1896, 2024, False),
    ('games_competitor', 'age'): (10, 80, False),
}
BOUNDARIES = {
    ('games', 'games_year'): [1987, 1988, 1989, 1991, 1992, 1993],
    ('games_competitor', 'age'): [27, 28, 29, 34, 35, 36],
    ('person', 'height'): [169, 170, 171, 174, 175, 176],
}
FK_BOUNDARIES = {
    ('games_competitor', 'games_id'): [12, 13, 14],
    ('games_city', 'games_id'): [2, 3, 4],
    ('competitor_event', 'medal_id'): [0, 1, 2, 3, 4, 5],
}
TEXT_LITERALS = {
    ('games', 'games_name'): ['2016 Summer', '2016 summer', '2012 Summer', '2012 summer',
                              '2014 Winter', '2014 winter', '1988 Winter', '1988 winter'],
    ('person', 'full_name'): ['Lee Chong Wei', 'lee chong wei', 'John Aalberg', 'john aalberg',
                              'Peter Kohnke', 'peter kohnke'],
    ('noc_region', 'region_name'): ['Tonga', 'tonga', 'Finland', 'finland', 'Philippines', 'philippines'],
    ('event', 'event_name'): ["Cross Country Skiing Men's 10/15 kilometres Pursuit",
                              "Shooting Women's Trap", "Basketball Men's Basketball"],
}
LIKE_LITERALS = {
    ('event', 'event_name'): ["Cross Country Skiing Men's 10/15 kilometres Pursuit",
                              "Shooting Women's Trap", "Basketball Men's Basketball"],
    ('games', 'games_name'): ['1988 Winter', '2012 Summer', 'Summer'],
}
DUP_TARGETS = {
    ('games_competitor', 'person_id'), ('person', 'id'), ('games', 'id'), ('event', 'event_name'),
    ('games', 'games_name'), ('games_city', 'games_id'), ('games_competitor', 'games_id'),
    ('city', 'city_name'), ('games', 'games_year'), ('noc_region', 'region_name'),
}
GROUP_TARGETS = {('person', 'id'), ('games', 'id'), ('games', 'games_name'), ('city', 'city_name')}
TIE_TARGETS = {('games', 'id'), ('games', 'games_name'), ('games', 'games_year'), ('city', 'city_name'),
               ('event', 'id'), ('sport', 'sport_name')}


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


def _like_variants(lit: str) -> list:
    """L, apostrophe removed, last char changed, trailing 'x', lowercase(L)."""
    out = [lit]
    if "'" in lit:
        out.append(lit.replace("'", ''))
    if lit:
        out.append(lit[:-1] + ('z' if lit[-1] != 'z' else 'y'))
    out.append(lit + 'x')
    out.append(lit.lower())
    return out


def _spec_values(table: str, col: str, rng) -> list:
    """All specification-mandated values for a column (enums, boundaries, literals, LIKE variants)."""
    key = (table, col)
    vals = []
    if key in ENUM_VARIANTS:
        vals += ENUM_VARIANTS[key]
    if key in BOUNDARIES:
        vals += BOUNDARIES[key]
    if key in TEXT_LITERALS:
        vals += TEXT_LITERALS[key]
    if key in LIKE_LITERALS:
        for lit in LIKE_LITERALS[key]:
            vals += _like_variants(lit)
    return vals


def _is_text_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'blob')) or t == ''


def _is_int_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'int' in t or 'year' in t


def _coerce(cm, v):
    """Coerce a specification value to the column's declared type."""
    if v is None:
        return None
    if _is_int_column(cm):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    if _is_text_column(cm):
        return str(v)
    return v


def _in_range(table: str, col: str, v) -> bool:
    """True if v satisfies the semantic range rule for (table, col) (non-NULL operands only)."""
    key = (table, col)
    if key not in RANGES or v is None:
        return True
    lo, hi, sentinel = RANGES[key]
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return True
    if sentinel and iv == 0:
        return True
    return lo <= iv <= hi


def _in_enum(table: str, col: str, v) -> bool:
    key = (table, col)
    if key not in ENUMS or v is None:
        return True
    return str(v) in ENUMS[key]


def _rule_ok(table: str, col: str, v) -> bool:
    """SQL three-valued logic: a rule holds when its expression is not FALSE (NULL passes)."""
    return _in_range(table, col, v) and _in_enum(table, col, v)


def _plant_spec_values(table: str, col: str, values: list, rng) -> list:
    """Overwrite positions with specification-mandated values (boundaries, literals, enums)."""
    spec = _spec_values(table, col, rng)
    if not spec or not values:
        return values
    n = len(values)
    positions = list(range(n))
    rng.shuffle(positions)
    for idx, sv in enumerate(spec):
        values[positions[idx % n]] = sv
    return values


def _plant_fk_boundaries(table: str, col: str, values: list, parent_pool: list, rng) -> list:
    """Plant FK boundary values only when they exist in the surviving parent PK pool."""
    key = (table, col)
    if key not in FK_BOUNDARIES or not values or not parent_pool:
        return values
    pool = set(parent_pool)
    valid = [v for v in FK_BOUNDARIES[key] if v in pool]
    if not valid:
        return values
    n = len(values)
    positions = list(range(n))
    rng.shuffle(positions)
    for idx, sv in enumerate(valid):
        values[positions[idx % n]] = sv
    return values


def _plant_nulls(table: str, col: str, values: list, rng, share: float) -> list:
    """Plant NULLs in a nullable column with the given share (at least one NULL row)."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    for pos in rng.sample(range(n), k):
        values[pos] = None
    return values


def _plant_duplicates(table: str, col: str, values: list, rng, share: float) -> list:
    """Make 20-50% of rows share values on a DISTINCT-targeted column."""
    n = len(values)
    if n < 2:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n - 1)
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    for pos in rng.sample(range(n), k):
        values[pos] = rng.choice(pool)
    return values


def _plant_group_sizes(table: str, col: str, values: list, rng) -> list:
    """Ensure groups of size 1, 2 and >= 3 on the grouping column."""
    n = len(values)
    if n < 6:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    a, b, c = rng.choice(pool), rng.choice(pool), rng.choice(pool)
    values[0] = a
    values[1] = b
    values[2] = b
    values[3] = c
    values[4] = c
    values[5] = c
    return values


def _plant_ties(table: str, col: str, values: list, rng) -> list:
    """Ensure at least two rows tie at rank 1 for the ORDER BY aggregate (duplicate a value)."""
    n = len(values)
    if n < 2:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    v = rng.choice(pool)
    values[0] = v
    values[1] = v
    return values


def _apply_spec(table: str, col: str, values: list, rng, nullable: bool, is_pk: bool) -> list:
    """Apply all specification patterns for one column, in a fixed order."""
    key = (table, col)
    if not is_pk:
        values = _plant_spec_values(table, col, values, rng)
    if key in DUP_TARGETS:
        values = _plant_duplicates(table, col, values, rng, rng.uniform(0.2, 0.5))
    if key in GROUP_TARGETS:
        values = _plant_group_sizes(table, col, values, rng)
    if key in TIE_TARGETS:
        values = _plant_ties(table, col, values, rng)
    if nullable:
        values = _plant_nulls(table, col, values, rng, rng.uniform(0.05, 0.3))
    return values


def _pk_start(schema, table: str) -> int:
    """First fresh integer PK value above the compact maximum (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    pk = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _assign_primary_keys(schema, table: str, n: int, rng) -> list:
    """Sequential fresh integer PKs starting above the compact maximum."""
    start = _pk_start(schema, table)
    return list(range(start, start + n))


def _parent_pool(inst: dict, schema, pt: str, pc: str) -> list:
    """Surviving parent PK values (compact + generated) for FK drawing."""
    vals = list(inst.get(pt, {}).get(pc) or [])
    vals += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    return [v for v in vals if v is not None]


def _fill_fk_column(inst: dict, schema, table: str, col: str, n: int, rng, nullable: bool) -> list:
    """Draw FK values from the surviving parent pool; NULL share for nullable FKs."""
    pt, pc = schema.fks[(table, col)]
    pool = _parent_pool(inst, schema, pt, pc)
    if not pool:
        return [None] * n
    vals = [rng.choice(pool) for _ in range(n)]
    if nullable:
        vals = _plant_nulls(table, col, vals, rng, rng.uniform(0.05, 0.3))
    return vals


def _repair_value(table: str, col: str, v, rng):
    """Replace a rule-violating value with a valid one (by construction, no SQL)."""
    key = (table, col)
    if key in ENUMS:
        return rng.choice(ENUMS[key])
    if key in RANGES:
        lo, hi, sentinel = RANGES[key]
        return rng.randint(lo, hi)
    return v


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification-driven samplers."""
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
        if tm.primary_key and len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            cols[tm.primary_key[0]] = _assign_primary_keys(schema, t, n, rng)
        inst[t] = cols
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                nullable = not cm.notnull
                cols[cm.name] = _fill_fk_column(inst, schema, t, cm.name, n, rng, nullable)
        for cm in tm.columns:
            if cm.name in cols:
                is_pk = cm.name in tm.primary_key
                nullable = (not cm.notnull) and (not is_pk)
                cols[cm.name] = _apply_spec(t, cm.name, cols[cm.name], rng, nullable, is_pk)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks and cm.name in cols:
                pt, pc = schema.fks[(t, cm.name)]
                pool = _parent_pool(inst, schema, pt, pc)
                cols[cm.name] = _plant_fk_boundaries(t, cm.name, cols[cm.name], pool, rng)
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            fixed = []
            for v in cols[cm.name]:
                if v is not None and not _rule_ok(t, cm.name, v):
                    v = _repair_value(t, cm.name, v, rng)
                fixed.append(v)
            cols[cm.name] = fixed
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks or cm.name not in cols:
                continue
            pt, pc = schema.fks[(t, cm.name)]
            pool = _parent_pool(inst, schema, pt, pc)
            pool_set = set(pool)
            nullable = not cm.notnull
            new_vals = []
            for v in cols[cm.name]:
                if v is None:
                    new_vals.append(None)
                elif v in pool_set:
                    new_vals.append(v)
                elif pool:
                    new_vals.append(rng.choice(pool))
                else:
                    new_vals.append(None if nullable else v)
            cols[cm.name] = new_vals
    return {t: inst[t] for t in schema.tables}
