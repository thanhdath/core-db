"""Random instance construction (fuzz/fuzz.py:83-196) with the school/school_players specification."""
from collections import Counter

DENOMINATIONS = ['Catholic', 'Anglican', 'Uniting Church']
BOYS_OR_GIRLS = ['Boys', 'Boys only to Yr 9 Co-ed Year 10 to 12']
DAY_OR_BOARDING = ['Day', 'Day & Boarding']
LEAGUE = 'DSHA'
CLASSES = ['Flight A', 'Flight B', 'Fight A']
DIVISIONS = ['Division 1', 'Division 2', 'Division 3']
POSITIONS = ['Shortstop', 'Third baseman', 'First Baseman', 'Left-handed pitcher', 'Catcher',
             'First baseman', 'Right-handed pitcher', 'Second baseman']
FOUNDED_BOUNDARY = [1888, 1889, 1890, 1891, 1899, 1900, 1901, 1902]
ENROLLMENT_POOL = [1000.0, 1200.0, 1430.0, 1850.0, 2200.0, 2300.0]
AGE_POOL = [14, 15, 16, 17, 18]
YEAR_POOL = [1929, 1944]
SCHOOL_COLORS = ['Royal Blue and Gold', 'Red & Blue', 'Red, White & Blue', 'Black & Blue', 'Green and White']
NICKNAMES = ['Tigers', 'Auks', 'Buccaneers', 'Raiders', 'Seahawks', 'Silver Eagles']
DETAIL_COLORS = ['Blue and Yellow', 'Dark Green and White', 'Garnet and White', 'Maroon and White',
                 'Blue and Gold', 'Silver and Maroon']
LOCATIONS = ['Milsons Point', 'Hornsby', 'Bellevue Hill', 'Wahroonga', 'Summer Hill', 'Waverley']
SCHOOL_NAMES = ["St Aloysius' College", 'Barker College', 'Cranbrook School', 'Knox Grammar School',
                'Trinity Grammar School', 'Waverley College']
CLASS_A_POOL = ['Yantis', 'Happy', 'Skidmore-Tynan', 'Louise', 'Anton', 'Utopia', "Martin's Mill", 'Lindsay']
CLASS_AA_POOL = ['Blanco', 'Bishop', 'Lytle', 'Clarendon', 'Wheeler', 'Wallis Brazos', 'Henrietta', 'Canadian']
PLAYER_NAMES = ['Timothy Beckham', 'Pedro Álvarez', 'Eric Hosmer', 'Brian Matusz', 'Buster Posey',
                'Kyle Skipworth', 'Yonder Alonso', 'Gordon Beckham']
TEAMS = ['Tampa Bay Devil Rays', 'Pittsburgh Pirates', 'Kansas City Royals', 'Baltimore Orioles',
         'San Francisco Giants', 'Florida Marlins', 'Cincinnati Reds', 'Chicago White Sox']

SPEC_SIZES = {'school': 6, 'school_details': 6, 'school_performance': 22, 'player': 23}

NULL_SHARE = 0.08


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_nullable(cm) -> bool:
    return not cm.notnull and cm.pk_pos == 0


def _plant_nulls(values: list, nullable: bool, rng, share: float = NULL_SHARE,
                 protected: set = frozenset()) -> list:
    """NULL rule: at least one NULL row per nullable column, share following the compact share."""
    if not nullable or not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    k = min(k, n)
    candidates = [i for i in range(n) if i not in protected]
    if not candidates:
        candidates = list(range(n))
    k = min(k, len(candidates))
    idx = rng.sample(candidates, k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _dedupe_pk(tm, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not tm.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in tm.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def _dedupe_unique(tm, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in tm.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _group_sizes(values: list) -> dict:
    """Grouped counts of non-NULL values (NULL is its own group)."""
    return dict(Counter(values))


def choose_table_sizes(schema, rng) -> dict:
    """Spec sizes when the schema matches the school database, else the generic fuzz sizes."""
    names = {t.lower() for t in schema.tables}
    if {'school', 'school_details', 'school_performance', 'player'} <= names:
        return {t: SPEC_SIZES.get(t.lower(), 0) for t in schema.tables}
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


def _generic_samplers(schema, literal_pool, rng):
    from .values import _init_sampler
    p = 0.0 if rng.random() < 0.3 else 0.2
    samplers = {}
    for t in [t for lvl in schema.table_order for t in lvl]:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    return samplers


def _sample_school(schema, rng, n: int) -> dict:
    """school rows: 6 rows, School_ID 1..6."""
    tm = schema.tables['school']
    ids = list(range(1, n + 1))

    if n == 6:
        denom = ['Catholic', 'Catholic', 'Catholic', 'Anglican', 'Anglican', 'Uniting Church']
        denom_null_idx = 0
    else:
        denom = [DENOMINATIONS[i % len(DENOMINATIONS)] for i in range(n)]
        denom_null_idx = 0

    if n == 6:
        loc = [LOCATIONS[0], LOCATIONS[0], LOCATIONS[1], LOCATIONS[1], LOCATIONS[2], LOCATIONS[3]]
        loc_null_idx = 0
    else:
        loc = list(LOCATIONS[1:n + 1]) or list(LOCATIONS[:n])
        if n >= 3:
            loc[-1] = loc[0]
        loc_null_idx = 0

    enroll = list(ENROLLMENT_POOL[:n])
    if n >= 4:
        enroll[1] = enroll[0]
        enroll[n - 1] = enroll[n - 2]
    elif n >= 2:
        enroll[1] = enroll[0]

    if n == 6:
        founded = [1888, 1889, 1890, 1900, 1901, 1901]
    else:
        founded = list(FOUNDED_BOUNDARY[:n])
        if n >= 2:
            founded[-1] = founded[-2]
        if n > len(FOUNDED_BOUNDARY):
            founded += [1900 + (i % 20) for i in range(n - len(FOUNDED_BOUNDARY))]

    larger = max(BOYS_OR_GIRLS)
    smaller = min(BOYS_OR_GIRLS)
    boys = [larger, larger, larger, smaller, smaller, smaller][:n]
    if n < 6:
        boys = ([larger] * 2 + [smaller] * max(0, n - 2))[:n]

    day = [DAY_OR_BOARDING[i % len(DAY_OR_BOARDING)] for i in range(n)]
    year = [YEAR_POOL[i % len(YEAR_POOL)] for i in range(n)]
    colors = [SCHOOL_COLORS[i % len(SCHOOL_COLORS)] for i in range(n)]
    names = [SCHOOL_NAMES[i % len(SCHOOL_NAMES)] for i in range(n)]

    cols = {
        'School_ID': ids,
        'School': names,
        'Location': loc,
        'Enrollment': enroll,
        'Founded': founded,
        'Denomination': denom,
        'Boys_or_Girls': boys,
        'Day_or_Boarding': day,
        'Year_Entered_Competition': year,
        'School_Colors': colors,
    }

    for cm in tm.columns:
        if cm.name not in cols or not _is_nullable(cm):
            continue
        if cm.name == 'Denomination':
            c = list(cols[cm.name])
            if n > denom_null_idx:
                c[denom_null_idx] = None
            cols[cm.name] = c
        elif cm.name == 'Location':
            c = list(cols[cm.name])
            if n > loc_null_idx:
                c[loc_null_idx] = None
            cols[cm.name] = c
        else:
            cols[cm.name] = _plant_nulls(cols[cm.name], True, rng)
    return cols


def _sample_school_details(schema, rng, n: int, school_ids: list) -> dict:
    """school_details: 1:1 with school, Nickname 6 rows with 4 distinct before NULL; a duplicate index is protected
    from NULLing so duplicate_share stays in 20-50% after NULL planting."""
    tm = schema.tables['school_details']
    ids = list(school_ids[:n])
    if n == 6:
        nick = [NICKNAMES[0], NICKNAMES[0], NICKNAMES[0], NICKNAMES[1], NICKNAMES[2], NICKNAMES[3]]
        protect = {0}
    else:
        nick = [NICKNAMES[i % len(NICKNAMES)] for i in range(n)]
        if n >= 3:
            nick[-1] = nick[0]
        protect = {0}
    cols = {
        'School_ID': ids,
        'Nickname': nick,
        'Colors': [DETAIL_COLORS[i % len(DETAIL_COLORS)] for i in range(n)],
        'League': [LEAGUE] * n,
        'Class': [CLASSES[i % len(CLASSES)] for i in range(n)],
        'Division': [DIVISIONS[i % len(DIVISIONS)] for i in range(n)],
    }
    for cm in tm.columns:
        if cm.name in cols and _is_nullable(cm) and cm.name != 'School_ID':
            prot = protect if cm.name == 'Nickname' else frozenset()
            cols[cm.name] = _plant_nulls(cols[cm.name], True, rng, protected=prot)
    return cols


def _sample_school_performance(schema, rng, n: int, school_ids: list) -> dict:
    """school_performance: 1:N child of school, School_Year 'YYYY-YY' consecutive years."""
    tm = schema.tables['school_performance']
    fk_pool = school_ids[:-1] if len(school_ids) > 1 else school_ids
    ids, years, used = [], [], set()
    y = 1987
    while len(ids) < n and y <= 2025:
        for sid in fk_pool[:]:
            if len(ids) >= n:
                break
            yr = '%04d-%02d' % (y, (y + 1) % 100)
            if (sid, yr) not in used:
                used.add((sid, yr))
                ids.append(sid)
                years.append(yr)
        y += 1
    while len(ids) < n and fk_pool:
        sid = fk_pool[len(ids) % len(fk_pool)]
        y2 = 1987
        while (sid, '%04d-%02d' % (y2, (y2 + 1) % 100)) in used and y2 <= 2025:
            y2 += 1
        yr = '%04d-%02d' % (y2, (y2 + 1) % 100)
        used.add((sid, yr))
        ids.append(sid)
        years.append(yr)
    ids = ids[:n]
    years = years[:n]
    cols = {
        'School_Id': ids,
        'School_Year': years,
        'Class_A': [CLASS_A_POOL[i % len(CLASS_A_POOL)] for i in range(n)],
        'Class_AA': [CLASS_AA_POOL[i % len(CLASS_AA_POOL)] for i in range(n)],
    }
    for cm in tm.columns:
        if cm.name in cols and _is_nullable(cm) and cm.name != 'School_Id':
            cols[cm.name] = _plant_nulls(cols[cm.name], True, rng)
    return cols


def _sample_player(schema, rng, n: int, school_ids: list) -> dict:
    """player: 1:N child of school."""
    tm = schema.tables['player']
    ids = list(range(1, n + 1))
    fk_pool = school_ids[:-1] if len(school_ids) > 1 else school_ids
    fk = []
    if fk_pool:
        base = [1, 2, 4, 4] + [3] * max(0, len(fk_pool) - 4)
        for sid, sz in zip(fk_pool, base):
            fk.extend([sid] * sz)
        pad_targets = fk_pool[2:] if len(fk_pool) > 2 else fk_pool
        if pad_targets:
            k = 0
            while len(fk) < n:
                fk.append(pad_targets[k % len(pad_targets)])
                k += 1
        fk = fk[:n]
        ranges = {}
        for idx, v in enumerate(fk):
            ranges.setdefault(v, []).append(idx)
        gt3 = [sid for sid in fk_pool[2:] if len(ranges.get(sid, [])) >= 3]
        gt3 = sorted(gt3, key=lambda s: -len(ranges[s]))
        if len(gt3) >= 2:
            fk = list(fk)
            fk[ranges[gt3[0]][-1]] = None
            fk[ranges[gt3[1]][-1]] = max(school_ids) + 1
        elif len(gt3) == 1:
            fk = list(fk)
            idxs = ranges[gt3[0]]
            fk[idxs[-1]] = None
            fk[idxs[-2]] = max(school_ids) + 1
    else:
        fk = [None] * n

    ages = [AGE_POOL[i % len(AGE_POOL)] for i in range(n)]
    cols = {
        'Player_ID': ids,
        'Player': [PLAYER_NAMES[i % len(PLAYER_NAMES)] for i in range(n)],
        'Team': [TEAMS[i % len(TEAMS)] for i in range(n)],
        'Age': ages,
        'Position': [POSITIONS[i % len(POSITIONS)] for i in range(n)],
        'School_ID': fk,
    }
    for cm in tm.columns:
        if cm.name in cols and _is_nullable(cm) and cm.name != 'School_ID':
            cols[cm.name] = _plant_nulls(cols[cm.name], True, rng)
    return cols


def _fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _build_generic(schema, literal_pool, size, rng) -> dict:
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = _generic_samplers(schema, literal_pool, rng)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(_fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = _dedupe_pk(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = _dedupe_unique(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def _construction_report(inst: dict) -> dict:
    """Realized group sizes, tie ranks and boundary values per instance."""
    rep: dict = {}
    school = inst.get('school', {})
    player = inst.get('player', {})
    details = inst.get('school_details', {})
    if 'Denomination' in school:
        rep['school.Denomination.group_sizes'] = _group_sizes(school['Denomination'])
        vals = [v for v in school['Denomination'] if v is not None]
        rep['school.Denomination.dup_share'] = round((len(vals) - len(set(vals))) / max(1, len(vals)), 3)
    if 'Location' in school:
        rep['school.Location.group_sizes'] = _group_sizes(school['Location'])
        vals = [v for v in school['Location'] if v is not None]
        rep['school.Location.dup_share'] = round((len(vals) - len(set(vals))) / max(1, len(vals)), 3)
    if 'School_ID' in school:
        rep['school.School_ID.group_sizes'] = _group_sizes(school['School_ID'])
    if 'School_ID' in player:
        rep['player.School_ID.group_sizes'] = _group_sizes(player['School_ID'])
        kids = set(player['School_ID'])
        rep['school.School_ID.childless_parents'] = [sid for sid in school.get('School_ID', []) if sid not in kids]
    if 'Enrollment' in school:
        vals = [v for v in school['Enrollment'] if v is not None]
        rep['school.Enrollment.min_tie'] = vals.count(min(vals)) if vals else 0
        rep['school.Enrollment.max_tie'] = vals.count(max(vals)) if vals else 0
    if 'Founded' in school:
        vals = [v for v in school['Founded'] if v is not None]
        rep['school.Founded.values'] = sorted(vals)
        rep['school.Founded.max_tie'] = vals.count(max(vals)) if vals else 0
    if 'Boys_or_Girls' in school:
        vals = [v for v in school['Boys_or_Girls'] if v is not None]
        rep['school.Boys_or_Girls.max_tie'] = vals.count(max(vals)) if vals else 0
    if 'Nickname' in details:
        vals = [v for v in details['Nickname'] if v is not None]
        rep['school_details.Nickname.distinct'] = len(set(vals))
    return rep


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the generation specification."""
    names = {t.lower() for t in schema.tables}
    if not {'school', 'school_details', 'school_performance', 'player'} <= names:
        return _build_generic(schema, literal_pool, size, rng)

    sizes = choose_table_sizes(schema, rng)
    inst: dict = {}
    school = _sample_school(schema, rng, sizes['school'])
    inst['school'] = school
    school_ids = [v for v in school['School_ID'] if v is not None]
    inst['school_details'] = _sample_school_details(schema, rng, sizes['school_details'], school_ids)
    inst['school_performance'] = _sample_school_performance(schema, rng, sizes['school_performance'], school_ids)
    inst['player'] = _sample_player(schema, rng, sizes['player'], school_ids)

    for t in list(inst):
        tm = schema.tables[t]
        cols = _dedupe_pk(tm, {cm.name: inst[t][cm.name] for cm in tm.columns if cm.name in inst[t]})
        cols = _dedupe_unique(tm, cols)
        inst[t] = cols
    out = {t: inst[t] for t in schema.tables}
    out['__construction__'] = _construction_report(inst)
    return out
