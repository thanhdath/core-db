"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven samplers."""
import re

from .values import _init_sampler

GEN_SIZES = {'country': 6, 'team': 10, 'match_season': 16, 'player': 10}

ENUMS = {
    ('match_season', 'Position'): ['Defender', 'Midfielder', 'Forward'],
}

BOUNDARY = {
    ('match_season', 'College'): ['Duke', 'duke', 'UCLA', 'ucla', 'Maryland', 'maryland'],
    ('match_season', 'Position'): ['Defender', 'Midfielder', 'Forward'],
}

LIKE_VARIANTS = {
    ('country', 'Official_native_language'): ['English', 'english', 'ENGLISH', 'glish'],
}

NAME_POOLS = {
    ('country', 'Country_name'): ['Indonesia', 'Iran', 'Iraq', 'Ireland', 'Isle of Man', 'United States',
                                  'India', 'Italy', 'Iceland', 'Israel', 'Iowa', 'Indiana'],
    ('country', 'Capital'): ['Jakarta', 'Tehran', 'Baghdad', 'Dublin', 'Douglas', 'Washington',
                             'New Delhi', 'Rome', 'Reykjavik', 'Jerusalem', 'Des Moines', 'Indianapolis'],
    ('team', 'Name'): ['Columbus Crew', 'Miami Fusion', 'Los Angeles Galaxy', 'New York Red Bulls',
                       'Chicago Fire', 'Dallas Burn', 'Kansas City Wizards', 'San Jose Earthquakes',
                       'Tampa Bay Mutiny', 'New England Revolution', 'Colorado Rapids', 'DC United'],
    ('player', 'Player'): ['Cho Soong-Jae', 'Chung Hong', 'Im Kyu-tae', 'Jeong Suk-Young', 'Kim Hyun-Joon',
                           'Kim Young-Jun', 'Lim Yong-Kyu', 'Seol Jae-Min', 'Lee Hyung-Taik', 'Lee Duck-Hee',
                           'Park Sung-Hwan', 'Jun Woong-Sun'],
    ('match_season', 'Player'): ['Steve Ralston', 'Mike Duhaney', 'Ben Olsen', 'Jay Heaps', 'Carlos Bocanegra',
                                 'Rodrigo Faria', 'Kyle Martino', 'Damani Ralph',
                                 'Chris Armas', 'Eddie Pope'],
    ('match_season', 'Draft_Class'): ['1996 MLS College Draft', '1996 MLS Inaugural Player Draft', 'Project-40',
                                      '1999 MLS College Draft', '2000 MLS SuperDraft', '2001 MLS SuperDraft',
                                      '2002 MLS SuperDraft', '2003 MLS SuperDraft'],
    ('match_season', 'College'): ['Florida International', 'UNLV', 'Virginia', 'Duke', 'UCLA',
                                  'Concordia College', 'Connecticut', 'Furman', 'Maryland', 'duke', 'ucla',
                                  'maryland'],
}

SHORT_POOLS = {
    ('match_season', 'Draft_Class'): ['1996 MLS College Draft', '1996 MLS Inaugural Player Draft', 'Project-40',
                                      '1999 MLS College Draft', '2000 MLS SuperDraft', '2001 MLS SuperDraft',
                                      '2002 MLS SuperDraft', '2003 MLS SuperDraft'],
    ('match_season', 'College'): ['Florida International', 'UNLV', 'Virginia', 'Duke', 'UCLA',
                                  'Concordia College', 'Connecticut', 'Furman', 'Maryland'],
}

INT_RANGES = {
    ('match_season', 'Draft_Pick_Number'): (1, 100),
}
REAL_RANGES = {
    ('match_season', 'Season'): (1990.0, 2010.0),
}

DISTINCT_TARGETS = {
    ('country', 'Capital'), ('country', 'Official_native_language'),
    ('match_season', 'College'), ('match_season', 'Team'), ('match_season', 'Position'),
    ('player', 'Player'), ('player', 'Years_Played'), ('team', 'Name'),
}

ORDER_TARGETS = {('match_season', 'Position')}

GROUP_TARGETS = {('country', 'Country_name')}

NULL_TARGETS = {('match_season', 'Team'), ('match_season', 'Country'), ('player', 'Team'),
                ('country', 'Official_native_language')}

WL_COLUMNS = {('player', 'Total_WL'), ('player', 'Singles_WL'), ('player', 'Doubles_WL')}
YEARS_COLUMN = ('player', 'Years_Played')


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_int_type(t: str) -> bool:
    t = (t or '').lower()
    return 'int' in t


def _is_real_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number'))


def _is_text_type(t: str) -> bool:
    t = (t or '').lower()
    return t == '' or any(k in t for k in ('char', 'text', 'clob', 'blob'))


def _wl(rng) -> str:
    return '%d-%d' % (rng.randint(0, 9), rng.randint(0, 9))


def _years(rng) -> str:
    n = rng.randint(1, 10)
    y0 = rng.randint(1980, 2005)
    y1 = y0 + rng.randint(0, 5)
    return '%d (%d-%d)' % (n, y0, y1)


def _perturb_number(v, rng, is_int: bool):
    d = 1 if is_int else 0.1
    u = rng.random()
    if u < 0.2:
        v = v + d
    elif u < 0.4:
        v = v - d
    elif u < 0.5:
        v = v + 2 * d
    elif u < 0.6:
        v = v - 2 * d
    return int(round(v)) if is_int else round(v, 1)


def _perturb_string(v: str, rng) -> str:
    u = rng.random()
    if u < 0.2:
        return v + 'x'
    elif u < 0.4:
        return 'x' + v
    elif u < 0.6 and len(v) > 1:
        return v[:-1]
    elif u < 0.8 and len(v) > 1:
        return v[1:]
    return v


def _column_pool(schema, table: str, col: str, literal_pool: dict) -> list:
    """Ordered, de-duplicated candidate values for one column."""
    key = (table, col)
    out: list = []
    seen: set = set()

    def add(v):
        if v is None:
            return
        s = str(v)
        if s not in seen:
            seen.add(s)
            out.append(v)

    for v in schema.original_values.get(key, []):
        add(v)
    for v in literal_pool.get(key, []):
        add(v)
    for v in NAME_POOLS.get(key, []):
        add(v)
    for v in SHORT_POOLS.get(key, []):
        add(v)
    for v in ENUMS.get(key, []):
        add(v)
    for v in BOUNDARY.get(key, []):
        add(v)
    for v in LIKE_VARIANTS.get(key, []):
        add(v)
    return out


def _typed_pool(schema, table: str, col: str, cm, literal_pool: dict) -> list:
    """Coerce the candidate pool to the column's declared type."""
    raw = _column_pool(schema, table, col, literal_pool)
    out = []
    for v in raw:
        if _is_int_type(cm.type_str):
            try:
                out.append(int(float(v)))
            except (TypeError, ValueError):
                continue
        elif _is_real_type(cm.type_str):
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        else:
            out.append(str(v))
    return out


def _sample_column(schema, table: str, cm, n: int, rng, literal_pool: dict, sampler) -> list:
    """Draw n values for one non-FK, non-PK column, honouring the specification."""
    key = (table, cm.name)
    pool = _typed_pool(schema, table, cm.name, cm, literal_pool)
    vals: list = []

    if key in ENUMS:
        dom = ENUMS[key]
        for _ in range(n):
            vals.append(rng.choice(dom))
        return vals

    if key in WL_COLUMNS:
        for _ in range(n):
            if pool and rng.random() < 0.3:
                vals.append(rng.choice(pool))
            else:
                vals.append(_wl(rng))
        return vals

    if key == YEARS_COLUMN:
        for _ in range(n):
            if pool and rng.random() < 0.3:
                vals.append(rng.choice(pool))
            else:
                vals.append(_years(rng))
        return vals

    if _is_real_type(cm.type_str):
        lo, hi = REAL_RANGES.get(key, (1990.0, 2010.0))
        for _ in range(n):
            if pool and rng.random() < 0.3:
                v = float(rng.choice(pool))
                v = _perturb_number(v, rng, False)
            else:
                v = round(rng.uniform(lo, hi), 1)
            v = min(max(v, lo), hi)
            vals.append(v)
        return vals

    if _is_int_type(cm.type_str):
        lo, hi = INT_RANGES.get(key, (1, 100))
        for _ in range(n):
            if pool and rng.random() < 0.3:
                v = int(rng.choice(pool))
                v = _perturb_number(v, rng, True)
            else:
                v = rng.randint(lo, hi)
            v = min(max(v, lo), hi)
            vals.append(v)
        return vals

    if key in LIKE_VARIANTS:
        dom = LIKE_VARIANTS[key]
        for _ in range(n):
            vals.append(rng.choice(dom))
        return vals

    if key in BOUNDARY:
        dom = BOUNDARY[key]
        for _ in range(n):
            if rng.random() < 0.7:
                vals.append(rng.choice(dom))
            elif pool:
                vals.append(_perturb_string(str(rng.choice(pool)), rng))
            else:
                vals.append(rng.choice(dom))
        return vals

    if _is_text_type(cm.type_str):
        if pool:
            for _ in range(n):
                if rng.random() < 0.6:
                    vals.append(rng.choice(pool))
                else:
                    vals.append(_perturb_string(str(rng.choice(pool)), rng))
        else:
            for _ in range(n):
                vals.append(sampler.sample())
        return vals

    for _ in range(n):
        vals.append(sampler.sample())
    return vals


def _shape_duplicates(vals: list, rng, share: float = 0.3) -> list:
    """Force a 20-50% duplicate share by copying earlier values over later ones."""
    n = len(vals)
    if n < 2:
        return vals
    k = max(1, int(round(n * share)))
    idx = list(range(1, n))
    rng.shuffle(idx)
    for i in idx[:k]:
        vals[i] = vals[rng.randrange(0, i)]
    return vals


def _shape_ties(vals: list, rng) -> list:
    """Ensure at least two rows are tied at the first rank (smallest value)."""
    if len(vals) < 2:
        return vals
    try:
        first = min(vals)
    except TypeError:
        return vals
    others = [i for i, v in enumerate(vals) if v != first]
    if len(others) >= 1:
        vals[others[0]] = first
    return vals


def _shape_groups(vals: list, rng) -> list:
    """Ensure group sizes 1, 2 and >= 3 exist (needs >= 6 rows)."""
    n = len(vals)
    if n < 6:
        return vals
    try:
        base = min(vals)
    except TypeError:
        return vals
    vals[0] = base
    vals[1] = base
    vals[2] = base
    vals[3] = base
    vals[4] = base
    if vals[5] == base:
        try:
            vals[5] = base + 1 if isinstance(base, (int, float)) else str(base) + 'x'
        except Exception:
            pass
    return vals


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


def _parent_values(instance: dict, schema, table: str, col: str) -> list:
    """All non-NULL values of a parent column (compact rows + generated rows)."""
    vals = list(schema.original_values.get((table, col), []))
    vals += [v for v in instance.get(table, {}).get(col, []) if v is not None]
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        nullable = not cm.notnull and cm.pk_pos == 0
        if not pv:
            out[cm.name] = [None] * n
            continue
        if nullable:
            orig = schema.original_values.get(key, [])
            null_share = (sum(1 for v in orig if v is None) / len(orig)) if orig else 0.1
            null_share = max(null_share, 1.0 / max(n, 1))
            null_share = min(max(null_share, 0.05), 0.5)
            vals = []
            for _ in range(n):
                if rng.random() < null_share:
                    vals.append(None)
                else:
                    vals.append(rng.choice(pv))
            if None not in vals:
                vals[rng.randrange(n)] = None
            out[cm.name] = vals
        else:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table_sizes_per_instance, with per-instance variation (0-230 rows)."""
    sizes = {}
    for t in schema.tables:
        base = GEN_SIZES.get(t, 10)
        f = 0.5 + rng.random()
        sizes[t] = int(min(230, max(0, round(base * f))))
    return sizes


def _apply_null_rule(schema, table: str, cols: dict, rng) -> dict:
    """Every nullable non-FK column gets at least one NULL row; share follows the compact share."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        if (table, cm.name) in schema.fks:
            continue
        if cm.name not in cols:
            continue
        vals = cols[cm.name]
        n = len(vals)
        if n == 0:
            continue
        orig = schema.original_values.get((table, cm.name), [])
        share = (sum(1 for v in orig if v is None) / len(orig)) if orig else 0.1
        share = min(max(share, 0.05), 0.5)
        k = max(1, int(round(n * share)))
        idx = list(range(n))
        rng.shuffle(idx)
        for i in idx[:k]:
            vals[i] = None
        cols[cm.name] = vals
    return cols


def _apply_semantic_rules(schema, table: str, cols: dict, rng) -> dict:
    """Enforce semantic_rules_and_formulas on non-NULL operands (SQL three-valued logic)."""
    tm = schema.tables[table]
    names = {c.name for c in tm.columns}

    if 'Season' in names and 'Season' in cols:
        lo, hi = REAL_RANGES[('match_season', 'Season')]
        cols['Season'] = [v if v is None else min(max(float(v), lo), hi) for v in cols['Season']]

    if 'Position' in names and 'Position' in cols:
        dom = ENUMS[('match_season', 'Position')]
        cols['Position'] = [v if v is None or v in dom else rng.choice(dom) for v in cols['Position']]

    if 'Draft_Pick_Number' in names and 'Draft_Pick_Number' in cols:
        cols['Draft_Pick_Number'] = [v if v is None or v > 0 else abs(v) + 1 for v in cols['Draft_Pick_Number']]

    for wl in ('Total_WL', 'Singles_WL', 'Doubles_WL'):
        if wl in names and wl in cols:
            cols[wl] = [v if v is None or ('-' in str(v)) else _wl(rng) for v in cols[wl]]

    return cols


def _compact_pk_max(schema, table: str, pk_cols: list) -> int:
    """Largest compact integer PK value (0 if none)."""
    if len(pk_cols) != 1:
        return 0
    vals = [v for v in schema.original_values.get((table, pk_cols[0]), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _assign_primary_keys(schema, table: str, tm, n: int) -> dict:
    """Sequential integers starting after the compact max; never NULL; unique per table."""
    if not tm.primary_key or n <= 0:
        return {}
    if len(tm.primary_key) == 1:
        start = _compact_pk_max(schema, table, tm.primary_key) + 1
        return {tm.primary_key[0]: list(range(start, start + n))}
    out = {}
    for j, c in enumerate(tm.primary_key):
        start = _compact_pk_max(schema, table, [c]) + 1
        out[c] = list(range(start, start + n))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance: compact rows are kept, generated rows are appended (fuzz.py:111-196)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks and cm.pk_pos == 0:
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
            if (t, cm.name) in samplers:
                cols[cm.name] = _sample_column(schema, t, cm, n, rng, literal_pool, samplers[(t, cm.name)])
        cols.update(_assign_primary_keys(schema, t, tm, n))
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = _apply_semantic_rules(schema, t, cols, rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if cm.name not in cols or cm.pk_pos > 0:
                continue
            if key in DISTINCT_TARGETS:
                cols[cm.name] = _shape_duplicates(cols[cm.name], rng)
            if key in ORDER_TARGETS:
                cols[cm.name] = _shape_ties(cols[cm.name], rng)
            if key in GROUP_TARGETS:
                cols[cm.name] = _shape_groups(cols[cm.name], rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(schema, t, cols, rng)
        inst[t] = cols
    _enforce_fk_null_and_orphan_guarantees(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}


def _enforce_fk_null_and_orphan_guarantees(inst: dict, schema, rng) -> None:
    """Re-verify after dedup: each nullable FK keeps >=1 NULL child; each parent has an orphan row."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        if cm is None:
            continue
        vals = inst[ct][cc]
        if not vals:
            continue
        nullable = not cm.notnull and cm.pk_pos == 0
        if nullable and None not in vals:
            vals[rng.randrange(len(vals))] = None
        if pt in inst and pc in inst[pt]:
            parent_keys = [v for v in inst[pt][pc] if v is not None]
            referenced = {v for v in vals if v is not None}
            if parent_keys and all(k in referenced for k in parent_keys):
                idxs = [i for i, v in enumerate(vals) if v is not None]
                if idxs:
                    i = rng.choice(idxs)
                    vals[i] = None if nullable else rng.choice(parent_keys)
