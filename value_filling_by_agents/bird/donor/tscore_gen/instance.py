"""Random instance construction (fuzz/fuzz.py:83-196) plus the specification's by-construction rules."""
import datetime as dt
import re

from .values import _init_sampler

_HEX = '0123456789abcdef'

_TABLE_SIZES = {'projects': 200, 'essays': 200, 'donations': 400, 'resources': 400}

_NULL_SHARE = {
    ('projects', 'schoolid'): 0.10,
    ('projects', 'poverty_level'): 0.10,
    ('projects', 'school_year_round'): 0.10,
    ('projects', 'teacher_acctid'): 0.10,
    ('projects', 'school_metro'): 0.122,
    ('projects', 'secondary_focus_subject'): 0.313,
    ('projects', 'secondary_focus_area'): 0.313,
    ('projects', 'fulfillment_labor_materials'): 0.053,
    ('projects', 'school_ncesid'): 0.003,
    ('donations', 'donation_total'): 0.10,
    ('donations', 'donation_message'): 0.259,
    ('donations', 'donor_city'): 0.481,
    ('donations', 'donor_state'): 0.194,
    ('donations', 'donor_zip'): 0.55,
    ('resources', 'vendorid'): 0.03,
    ('resources', 'vendor_name'): 0.03,
    ('resources', 'item_name'): 0.004,
    ('resources', 'item_number'): 0.004,
    ('resources', 'item_unit_price'): 0.004,
    ('resources', 'item_quantity'): 0.002,
    ('essays', 'need_statement'): 0.002,
}

_ENUMS = {
    ('projects', 'school_charter'): ['t', 'f'],
    ('projects', 'school_magnet'): ['t', 'f'],
    ('projects', 'school_year_round'): ['t', 'f'],
    ('projects', 'school_nlns'): ['t', 'f'],
    ('projects', 'school_kipp'): ['t', 'f'],
    ('projects', 'school_charter_ready_promise'): ['t', 'f'],
    ('projects', 'teacher_teach_for_america'): ['t', 'f'],
    ('projects', 'teacher_ny_teaching_fellow'): ['t', 'f'],
    ('projects', 'eligible_double_your_impact_match'): ['t', 'f'],
    ('projects', 'eligible_almost_home_match'): ['t', 'f'],
    ('projects', 'school_metro'): ['urban', 'rural', 'suburban'],
    ('projects', 'poverty_level'): ['highest poverty', 'high poverty', 'moderate poverty', 'low poverty'],
    ('projects', 'grade_level'): ['Grades PreK-2', 'Grades 3-5', 'Grades 6-8', 'Grades 9-12'],
    ('projects', 'resource_type'): ['Books', 'Technology', 'Other', 'Supplies', 'Visitors', 'Trips'],
    ('projects', 'teacher_prefix'): ['Mrs.', 'Mr.', 'Ms.', 'Dr.', 'Mr. & Mrs.', ''],
    ('donations', 'is_teacher_acct'): ['t', 'f'],
    ('donations', 'donation_included_optional_support'): ['t', 'f'],
    ('donations', 'payment_included_acct_credit'): ['t', 'f'],
    ('donations', 'payment_included_campaign_gift_card'): ['t', 'f'],
    ('donations', 'payment_included_web_purchased_gift_card'): ['t', 'f'],
    ('donations', 'payment_was_promo_matched'): ['t', 'f'],
    ('donations', 'via_giving_page'): ['t', 'f'],
    ('donations', 'for_honoree'): ['t', 'f'],
    ('donations', 'dollar_amount'): ['under_10', '10_to_100', '100_and_up'],
    ('donations', 'payment_method'): ['no_cash_received', 'creditcard', 'paypal', 'amazon', 'promo_code_match',
                                      'check', 'double_your_impact_match', 'almost_home_match'],
    ('resources', 'project_resource_type'): ['Books', 'Technology', 'Other', 'Supplies', 'Visitors', 'Trips'],
}

_NEAR_VARIANTS = {
    ('essays', 'title'): ['Too Close for Comfort', 'Future Einsteins Of America', 'Virtual Aquarium Needs Help!',
                          'Creating Memories and Inspiring Dreams', 'Reading About Other Cultures'],
    ('projects', 'school_city'): ['Brooklyn', 'Los Angeles', 'Abington'],
    ('projects', 'teacher_prefix'): ['Dr.'],
    ('resources', 'vendor_name'): ['Amazon'],
}

_LIKE_TARGETS = {
    ('essays', 'title'): ['Creating Memories and Inspiring Dreams'],
    ('projects', 'teacher_prefix'): ['Dr.'],
}

_BOUNDARY = {
    ('projects', 'school_city'): ['Los Angeles', 'los angeles', 'LOS ANGELES'],
}

_HEX32 = {('projects', 'projectid'), ('donations', 'donationid'), ('resources', 'resourceid'),
          ('essays', 'projectid')}

_PK = {('projects', 'projectid'), ('donations', 'donationid'), ('resources', 'resourceid')}

_NONNEG = {('projects', 'total_price_excluding_optional_support'),
           ('projects', 'total_price_including_optional_support'),
           ('projects', 'fulfillment_labor_materials'),
           ('donations', 'donation_to_project'), ('donations', 'donation_optional_support'),
           ('donations', 'donation_total'), ('resources', 'item_unit_price')}

_POSITIVE = {('projects', 'students_reached'), ('resources', 'item_quantity')}

_ZIP = {('projects', 'school_zip')}

_LAT = {('projects', 'school_latitude')}
_LON = {('projects', 'school_longitude')}

_DUP_SHARE = {('projects', 'school_latitude'), ('projects', 'school_longitude'), ('projects', 'date_posted'),
              ('projects', 'grade_level'), ('projects', 'teacher_prefix'), ('resources', 'item_quantity'),
              ('donations', 'donation_message')}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _hex32(rng) -> str:
    return ''.join(rng.choice(_HEX) for _ in range(32))


def _one_char_sub(v: str, rng) -> str:
    """One-char-substituted variant of v (keeps length)."""
    if not v:
        return 'x'
    i = rng.randrange(len(v))
    c = v[i]
    repl = 'x' if c != 'x' else 'y'
    return v[:i] + repl + v[i + 1:]


def _near_variants(lit: str, rng) -> list:
    """L, L||'x', lower(L), one-char-substituted variant (near_variant rule)."""
    return [lit, lit + 'x', lit.lower(), _one_char_sub(lit, rng)]


def _boundary_variants(lit: str, rng) -> list:
    """L, one step below, one step above (boundary rule); strings step by case/char."""
    return [lit, lit.lower(), lit.upper()]


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs at the given share (at least one) into a list of non-NULL values."""
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


def _dedup_pk(values: list, rng) -> list:
    """Replace duplicate PK values with fresh hex32 strings (keeps first occurrence)."""
    seen, out = set(), []
    for v in values:
        if v is None or v in seen:
            v = _hex32(rng)
            while v in seen:
                v = _hex32(rng)
        seen.add(v)
        out.append(v)
    return out


def _apply_dup_share(values: list, rng) -> list:
    """Make 20-50% of rows share a value with another row (duplicates_for_distinct)."""
    n = len(values)
    if n < 2:
        return values
    share = rng.uniform(0.2, 0.5)
    k = max(1, int(round(n * share)))
    out = list(values)
    for i in rng.sample(range(n), k):
        j = rng.randrange(n)
        if j != i:
            out[i] = out[j]
    return out


def _clamp_nonneg(values: list) -> list:
    return [None if v is None else (abs(v) if isinstance(v, (int, float)) else v) for v in values]


def _clamp_positive(values: list) -> list:
    out = []
    for v in values:
        if v is None:
            out.append(None)
        elif isinstance(v, (int, float)):
            out.append(max(1, int(round(abs(v)))))
        else:
            out.append(v)
    return out


def _clamp_zip(values: list) -> list:
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            try:
                z = int(v)
            except (TypeError, ValueError):
                z = 10000
            out.append(min(99999, max(10000, abs(z))))
    return out


def _clamp_coord(values: list, lo: float, hi: float) -> list:
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = 0.0
            out.append(min(hi, max(lo, f)))
    return out


def _round2(values: list) -> list:
    return [None if v is None else round(float(v), 2) for v in values]


def _inject_variants(key: tuple, vals: list, rng) -> list:
    """Inject near-variant and boundary literals into a sampled column (works for any column)."""
    n = len(vals)
    if n == 0:
        return vals
    if key in _NEAR_VARIANTS:
        for lit in _NEAR_VARIANTS[key]:
            for v in _near_variants(lit, rng):
                vals[rng.randrange(n)] = v
    if key in _LIKE_TARGETS:
        for lit in _LIKE_TARGETS[key]:
            vals[rng.randrange(n)] = lit + '%'
    if key in _BOUNDARY:
        for lit in _BOUNDARY[key]:
            for v in _boundary_variants(lit, rng):
                vals[rng.randrange(n)] = v
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        if not cm.notnull and n > 0:
            k_null = max(1, int(round(n * 0.05)))
            idx = rng.sample(range(n), min(n, k_null))
            for i in idx:
                vals[i] = None
        out[cm.name] = vals
    return out


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


def _spec_size(table: str, rng) -> int:
    """Per-instance table size: the specification's table_sizes_per_instance, varied a little."""
    base = _TABLE_SIZES.get(table)
    if base is None:
        return 0
    lo = max(0, base - 30)
    hi = base + 30
    return rng.randint(lo, hi)


def _build_column_values(schema, table: str, n: int, samplers: dict, rng) -> dict:
    """Sample independent columns for the new rows of one table."""
    tm = schema.tables[table]
    cols = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks:
            continue
        if key in _HEX32:
            cols[cm.name] = [_hex32(rng) for _ in range(n)]
        elif key in _ENUMS:
            pool = _ENUMS[key]
            vals = [rng.choice(pool) for _ in range(n)]
            vals = _inject_variants(key, vals, rng)
            if key in _DUP_SHARE:
                vals = _apply_dup_share(vals, rng)
            cols[cm.name] = vals
        elif key in _ZIP:
            cols[cm.name] = _clamp_zip([rng.randint(10000, 99999) for _ in range(n)])
        elif key in _LAT:
            cols[cm.name] = _clamp_coord([rng.uniform(-90, 90) for _ in range(n)], -90, 90)
        elif key in _LON:
            cols[cm.name] = _clamp_coord([rng.uniform(-180, 180) for _ in range(n)], -180, 180)
        elif key in _NONNEG:
            cols[cm.name] = _round2(_clamp_nonneg([rng.uniform(0, 3000) for _ in range(n)]))
        elif key in _POSITIVE:
            cols[cm.name] = _clamp_positive([rng.randint(1, 500) for _ in range(n)])
        else:
            s = samplers.get(key)
            vals = [s.sample() for _ in range(n)] if s is not None else [None] * n
            vals = _inject_variants(key, vals, rng)
            if key in _DUP_SHARE:
                vals = _apply_dup_share(vals, rng)
            cols[cm.name] = vals
    return cols


def _apply_nulls(table: str, cols: dict, rng) -> dict:
    """Plant NULLs per the NULL rule (share from statistics, at least one NULL row)."""
    for cm_name in list(cols.keys()):
        key = (table, cm_name)
        share = _NULL_SHARE.get(key)
        if share is None:
            continue
        cols[cm_name] = _plant_nulls(cols[cm_name], share, rng)
    return cols


def _derive_projects(cols: dict, rng) -> dict:
    """Derived project columns: total_price_including >= excluding; fulfillment >= 0."""
    n = len(cols.get('projectid', []))
    excl = cols.get('total_price_excluding_optional_support')
    incl = cols.get('total_price_including_optional_support')
    if excl is not None and incl is not None:
        for i in range(n):
            e = excl[i]
            if e is None:
                continue
            opt = round(e * rng.uniform(0.15, 0.20), 2)
            incl[i] = round(e + opt, 2)
    return cols


def _derive_donations(cols: dict, rng) -> dict:
    """donation_total = donation_to_project + optional (if included) else = donation_to_project."""
    n = len(cols.get('donationid', []))
    to_proj = cols.get('donation_to_project')
    opt = cols.get('donation_optional_support')
    total = cols.get('donation_total')
    included = cols.get('donation_included_optional_support')
    if to_proj is None or opt is None or total is None:
        return cols
    for i in range(n):
        tp = to_proj[i]
        op = opt[i]
        if tp is None:
            continue
        if op is None:
            op = 0.0
            opt[i] = op
        inc = included[i] if included is not None else 't'
        if inc == 'f':
            total[i] = round(tp, 2)
        else:
            total[i] = round(tp + op, 2)
    return cols


def _derive_essays(cols: dict, projects_cols: dict, rng) -> dict:
    """essays.teacher_acctid copied from the matching project (dependency)."""
    n = len(cols.get('projectid', []))
    pids = projects_cols.get('projectid', [])
    tids = projects_cols.get('teacher_acctid', [])
    pid_to_tid = {p: t for p, t in zip(pids, tids)}
    out = []
    for i in range(n):
        pid = cols['projectid'][i]
        out.append(pid_to_tid.get(pid) if pid is not None else None)
    cols['teacher_acctid'] = out
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification's by-construction rules."""
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
        size = {t: _spec_size(t, rng) for t in schema.tables}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = _build_column_values(schema, t, n, samplers, rng)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        if t == 'projects':
            cols = _derive_projects(cols, rng)
        elif t == 'donations':
            cols = _derive_donations(cols, rng)
        elif t == 'essays':
            cols = _derive_essays(cols, inst.get('projects', {}), rng)
        cols = _apply_nulls(t, cols, rng)
        for cm in tm.columns:
            if (t, cm.name) in _PK:
                cols[cm.name] = _dedup_pk(cols[cm.name], rng)
        cols = sample_fresh_primary_keys(tm, cols)
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
