"""Random instance construction (fuzz/fuzz.py:83-196) + specification rules by construction."""
import math

from .values import _init_sampler


ENUMS = {
    ('CBSA', 'CBSA_type'): ['Micro', 'Metro'],
    ('zip_data', 'multi_county'): ['Yes', 'No'],
    ('zip_data', 'daylight_savings'): ['Yes', 'No'],
    ('zip_data', 'type'): ['Unique Post Office', 'Post Office', 'P.O. Box Only', 'Branch',
                           'Non Postal Community Name', 'Community Post Office', 'Branch-Unique',
                           'Non Postal Community Name-Unique'],
    ('zip_data', 'time_zone'): ['Eastern', 'Atlantic', 'Central', 'Mountain', 'Pacific',
                                'Hawaii-Aleutian Islands', 'American Samoa', 'Marshall Islands'],
    ('zip_data', 'region'): ['Northeast', 'South', 'Midwest', 'West'],
    ('zip_data', 'division'): ['Middle Atlantic', 'New England', 'South Atlantic', 'East South Central',
                               'East North Central', 'West North Central', 'Mountain', 'West South Central'],
    ('congress', 'party'): ['Republican', 'Democrat', 'Independent'],
    ('congress', 'House'): ['House of Repsentatives', 'Senate'],
}

BOUNDARY = {
    ('zip_data', 'zip_code'): [1115, 1116, 1117, 19018, 19019, 19020],
    ('alias', 'zip_code'): [1027, 1028, 1029, 19018, 19019, 19020],
    ('area_code', 'zip_code'): [1115, 1116, 1117],
    ('country', 'county'): ['CORYELL', 'coryell', 'GUAM', 'guam', 'SAINT CROIX', 'saint croix'],
    ('zip_data', 'city'): ['Aguada', 'aguada', 'Aguadilla', 'aguadilla', 'Hartford', 'hartford'],
    ('state', 'abbreviation'): ['NY', 'ny'],
    ('state', 'name'): ['Guam', 'guam', 'New York', 'new york', 'Alabama', 'alabama'],
    ('zip_data', 'type'): ['Post Office', 'post office', 'P.O. Box Only', 'p.o. box only'],
    ('avoid', 'bad_alias'): ['URB San Joaquin', 'urb san joaquin', 'Druid Hills', 'druid hills'],
    ('congress', 'first_name'): ['Smith', 'smith', 'Heck', 'heck'],
}

LIKE_VARIANTS = {
    ('CBSA', 'CBSA_name'): ['New York-Newark-Jersey City, NY-NJ-PA',
                            'New York-Newark-Jersey City, NY-NJ-PB',
                            'New York-Newark-Jersey City, NY-NJ-PAx',
                            'new york-newark-jersey city, ny-nj-pa'],
}

GROUP_SIZES = [1, 2, 3]

RANGES = {
    ('zip_data', 'population_2010'): (0, 10 ** 7),
    ('zip_data', 'population_2020'): (0, 10 ** 7),
    ('zip_data', 'persons_per_household'): (0.0, 10.0),
    ('zip_data', 'median_age'): (0.0, 120.0),
    ('zip_data', 'male_median_age'): (0.0, 120.0),
    ('zip_data', 'female_median_age'): (0.0, 120.0),
    ('zip_data', 'elevation'): (-100, 9000),
    ('zip_data', 'latitude'): (-90.0, 90.0),
    ('zip_data', 'longitude'): (-180.0, 180.0),
    ('zip_data', 'land_area'): (0.0, 10 ** 6),
    ('zip_data', 'water_area'): (0.0, 10 ** 6),
    ('zip_data', 'annual_payroll'): (0, 10 ** 9),
    ('zip_data', 'total_beneficiaries'): (0, 10 ** 6),
    ('congress', 'land_area'): (0.001, 10 ** 6),
    ('area_code', 'area_code'): (200, 999),
    ('CBSA', 'CBSA'): (1, 10 ** 6),
}

COUNT_COLS = {
    ('zip_data', 'households'), ('zip_data', 'avg_house_value'), ('zip_data', 'avg_income_per_household'),
    ('zip_data', 'white_population'), ('zip_data', 'black_population'), ('zip_data', 'hispanic_population'),
    ('zip_data', 'asian_population'), ('zip_data', 'american_indian_population'),
    ('zip_data', 'hawaiian_population'), ('zip_data', 'other_population'), ('zip_data', 'male_population'),
    ('zip_data', 'female_population'), ('zip_data', 'residential_mailboxes'), ('zip_data', 'business_mailboxes'),
    ('zip_data', 'total_delivery_receptacles'), ('zip_data', 'businesses'),
    ('zip_data', '1st_quarter_payroll'), ('zip_data', 'employees'),
    ('zip_data', 'single_family_delivery_units'), ('zip_data', 'multi_family_delivery_units'),
    ('zip_data', 'retired_workers'), ('zip_data', 'disabled_workers'), ('zip_data', 'parents_and_widowed'),
    ('zip_data', 'spouses'), ('zip_data', 'children'), ('zip_data', 'over_65'),
    ('zip_data', 'monthly_benefits_all'), ('zip_data', 'monthly_benefits_retired_workers'),
    ('zip_data', 'monthly_benefits_widowed'),
}

AMOUNT_COLS = {('zip_data', '1st_quarter_payroll'), ('zip_data', 'annual_payroll'),
               ('zip_data', 'monthly_benefits_all'), ('zip_data', 'monthly_benefits_retired_workers'),
               ('zip_data', 'monthly_benefits_widowed')}

FREE_TEXT = {('zip_data', 'city'), ('country', 'county'), ('alias', 'alias'), ('avoid', 'bad_alias'),
             ('CBSA', 'CBSA_name'), ('congress', 'first_name'), ('congress', 'last_name'),
             ('congress', 'CID'), ('state', 'name'), ('zip_data', 'organization')}

NULLABLE = {
    ('zip_data', 'organization'), ('zip_data', 'time_zone'), ('zip_data', 'latitude'),
    ('zip_data', 'longitude'), ('zip_data', 'elevation'), ('zip_data', 'state_fips'),
    ('zip_data', 'county_fips'), ('zip_data', 'region'), ('zip_data', 'division'),
    ('zip_data', 'population_2020'), ('zip_data', 'population_2010'), ('zip_data', 'households'),
    ('zip_data', 'avg_house_value'), ('zip_data', 'avg_income_per_household'),
    ('zip_data', 'persons_per_household'), ('zip_data', 'white_population'), ('zip_data', 'black_population'),
    ('zip_data', 'hispanic_population'), ('zip_data', 'asian_population'),
    ('zip_data', 'american_indian_population'), ('zip_data', 'hawaiian_population'),
    ('zip_data', 'other_population'), ('zip_data', 'male_population'), ('zip_data', 'female_population'),
    ('zip_data', 'median_age'), ('zip_data', 'male_median_age'), ('zip_data', 'female_median_age'),
    ('zip_data', 'residential_mailboxes'), ('zip_data', 'business_mailboxes'),
    ('zip_data', 'total_delivery_receptacles'), ('zip_data', 'businesses'),
    ('zip_data', '1st_quarter_payroll'), ('zip_data', 'annual_payroll'), ('zip_data', 'employees'),
    ('zip_data', 'water_area'), ('zip_data', 'land_area'), ('zip_data', 'single_family_delivery_units'),
    ('zip_data', 'multi_family_delivery_units'), ('zip_data', 'total_beneficiaries'),
    ('zip_data', 'retired_workers'), ('zip_data', 'disabled_workers'), ('zip_data', 'parents_and_widowed'),
    ('zip_data', 'spouses'), ('zip_data', 'children'), ('zip_data', 'over_65'),
    ('zip_data', 'monthly_benefits_all'), ('zip_data', 'monthly_benefits_retired_workers'),
    ('zip_data', 'monthly_benefits_widowed'), ('zip_data', 'CBSA'), ('congress', 'District'),
}

TABLE_SIZES = {'state': 62, 'CBSA': 200, 'congress': 200, 'zip_data': 400, 'alias': 400,
               'area_code': 400, 'avoid': 400, 'country': 400, 'zip_congress': 400}


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


def drop_unique_tuples(schema, table: str, columns: dict) -> dict:
    """Drop rows repeating any composite UNIQUE tuple (schema.unique_tuples)."""
    for t, cols in schema.unique_tuples:
        if t != table or not all(c in columns for c in cols):
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
    """Specification table_sizes_per_instance, with per-instance variation in [0.5x, 1.25x]."""
    sizes = {}
    for t in TABLE_SIZES:
        if t not in schema.tables:
            continue
        base = TABLE_SIZES[t]
        lo = int(math.ceil(0.5 * base))
        hi = int(math.floor(1.25 * base))
        sizes[t] = rng.randint(lo, max(lo, hi))
    return sizes


def _null_share(schema, key) -> float:
    """NULL share of a column in the compact database (at least one NULL row per nullable column)."""
    vals = schema.original_values.get(key, [])
    if not vals:
        return 0.02
    return max(1.0 / max(1, len(vals)), sum(1 for v in vals if v is None) / len(vals))


def _apply_nulls(values: list, key, schema, rng) -> list:
    """Plant NULLs in a nullable column following the compact share; never replace a planted NULL."""
    if key not in NULLABLE:
        return values
    share = _null_share(schema, key)
    n = len(values)
    k = max(1, int(round(share * n)))
    idx = rng.sample(range(n), min(k, n))
    for i in idx:
        values[i] = None
    return values


def _boundary_values(key, rng) -> list:
    """Boundary literals for a column: L, L-step, L+step (numeric) or case variants (text)."""
    out = []
    for lit in BOUNDARY.get(key, []):
        if isinstance(lit, (int, float)):
            out += [lit, lit - 1, lit + 1]
        else:
            out += [lit, lit.lower(), lit.upper()]
    return out


def _enum_values(key, rng) -> list:
    """Enumerated pool with 2% case/whitespace near-variants."""
    pool = list(ENUMS.get(key, []))
    if not pool:
        return []
    out = []
    for v in pool:
        out.append(v)
        if rng.random() < 0.02:
            out.append(v.lower() if rng.random() < 0.5 else v + ' ')
    return out


def _free_text_values(key, schema, rng, n) -> list:
    """Reuse city/county names from a small pool; ~30% repeated values."""
    ov = [v for v in schema.original_values.get(key, []) if v is not None]
    pool = ov[:max(1, min(len(ov), 20))] if ov else ['Alpha', 'Beta', 'Gamma']
    out = []
    for _ in range(n):
        if rng.random() < 0.3 and out:
            out.append(rng.choice(out))
        else:
            out.append(rng.choice(pool))
    return out


def _range_values(key, rng, n) -> list:
    """Positive real drawn from a log-normal-ish shape; round to 3 decimals for areas, 1 for ages."""
    lo, hi = RANGES[key]
    is_int = isinstance(lo, int) and isinstance(hi, int)
    out = []
    for _ in range(n):
        if is_int:
            v = int(lo + (hi - lo) * (rng.random() ** 2))
        else:
            v = lo + (hi - lo) * (rng.random() ** 2)
            v = round(v, 3) if 'area' in key[1] else round(v, 1)
        out.append(v)
    return out


def _count_values(key, rng, n) -> list:
    """Non-negative integer; skew small via geometric with mean 5; include 0 and boundary 1."""
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.1:
            v = 0
        elif u < 0.2:
            v = 1
        else:
            v = int(rng.expovariate(1.0 / 5.0))
        if key in AMOUNT_COLS:
            v = int(round(v / 1000.0)) * 1000
        out.append(v)
    return out


def _apply_semantic_rules(inst: dict, schema, rng) -> None:
    """Derived columns computed in Python from sampled values held in memory."""
    cg = inst.get('congress')
    if cg:
        n = len(cg.get('cognress_rep_id', []))
        if 'District' in cg:
            for i in range(n):
                d = cg['District'][i]
                if d is not None and not (1 <= d <= 53):
                    cg['District'][i] = rng.randint(1, 53)
        if 'land_area' in cg:
            for i in range(n):
                v = cg['land_area'][i]
                if v is not None and v <= 0:
                    cg['land_area'][i] = round(rng.uniform(0.001, 10 ** 6), 3)


def _apply_group_sizes(inst: dict, schema, rng) -> None:
    """Ensure groups of size 1, 2 and >=3 exist for aggregate-boundary columns."""
    for t, cols in [('CBSA', ['CBSA_name']), ('zip_data', ['city']), ('state', ['name'])]:
        if t not in inst:
            continue
        for c in cols:
            vals = inst[t].get(c)
            if not vals:
                continue
            if len(vals) >= 6:
                vals[1] = vals[0]
                vals[3] = vals[2]
                vals[4] = vals[2]
                vals[5] = vals[2]


def _apply_like_variants(inst: dict, rng) -> None:
    """Emit LIKE near-variants for CBSA.CBSA_name (literal + case/prefix/suffix variants)."""
    for (t, c), variants in LIKE_VARIANTS.items():
        vals = inst.get(t, {}).get(c)
        if not vals:
            continue
        for j, v in enumerate(variants):
            if j < len(vals):
                vals[j] = v


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification rules by construction."""
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
            if key in schema.fks:
                continue
            if key in ENUMS:
                pool = _enum_values(key, rng)
                cols[cm.name] = [rng.choice(pool) for _ in range(n)] if pool else [None] * n
            elif key in BOUNDARY:
                pool = _boundary_values(key, rng)
                cols[cm.name] = [rng.choice(pool) for _ in range(n)]
            elif key in FREE_TEXT:
                cols[cm.name] = _free_text_values(key, schema, rng, n)
            elif key in RANGES:
                cols[cm.name] = _range_values(key, rng, n)
            elif key in COUNT_COLS:
                cols[cm.name] = _count_values(key, rng, n)
            else:
                cols[cm.name] = [samplers[key].sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        cols = drop_unique_tuples(schema, t, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in inst:
        for c in list(inst[t].keys()):
            inst[t][c] = _apply_nulls(inst[t][c], (t, c), schema, rng)
    _apply_semantic_rules(inst, schema, rng)
    _apply_group_sizes(inst, schema, rng)
    _apply_like_variants(inst, rng)
    return {t: inst[t] for t in schema.tables}
