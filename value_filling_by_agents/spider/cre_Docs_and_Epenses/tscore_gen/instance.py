"""Random instance construction (fuzz/fuzz.py:83-196) plus specification-driven construction."""
import datetime as dt
from collections import Counter

from .values import _init_sampler

SPEC_TABLE_SIZES = {
    'Ref_Document_Types': 5,
    'Ref_Budget_Codes': 3,
    'Projects': 5,
    'Documents': 15,
    'Statements': 3,
    'Documents_with_Expenses': 10,
    'Accounts': 15,
}

SPEC_ENUMS = {
    ('Ref_Document_Types', 'Document_Type_Code'): ['BK', 'CV', 'FM', 'PP', 'PT'],
    ('Ref_Budget_Codes', 'Budget_Type_Code'): ['GV', 'ORG', 'SF'],
    ('Documents', 'Document_Type_Code'): ['BK', 'CV', 'FM', 'PP', 'PT'],
    ('Documents_with_Expenses', 'Budget_Type_Code'): ['GV', 'ORG', 'SF'],
}

SPEC_BUDGET_BOUNDARY = ['ORG', 'org', 'SF', 'sf']

SPEC_GROUP_SIZES = {
    ('Documents', 'Project_ID'): [1, 2, 3],
    ('Documents', 'Document_Type_Code'): [1, 2, 3],
    ('Documents_with_Expenses', 'Budget_Type_Code'): [1, 2, 3],
    ('Accounts', 'Statement_ID'): [1, 2, 3],
}

SPEC_AGG_BOUNDARY = {
    ('Documents', 'Project_ID'): [1, 2, 3],
}

SPEC_DUP_COLUMNS = {
    ('Accounts', 'Account_Details'),
    ('Projects', 'Project_Details'),
    ('Ref_Budget_Codes', 'Budget_Type_Description'),
    ('Ref_Document_Types', 'Document_Type_Description'),
    ('Ref_Document_Types', 'Document_Type_Name'),
    ('Statements', 'Statement_Details'),
    ('Documents', 'Document_Name'),
    ('Documents', 'Document_Date'),
    ('Documents', 'Document_Description'),
    ('Documents_with_Expenses', 'Budget_Type_Code'),
}

SPEC_NULL_COLUMNS = {
    ('Documents', 'Document_Date'),
    ('Documents', 'Document_Name'),
    ('Documents', 'Document_Description'),
    ('Documents', 'Other_Details'),
    ('Statements', 'Statement_Details'),
    ('Accounts', 'Account_Details'),
    ('Projects', 'Project_Details'),
    ('Documents_with_Expenses', 'Document_Details'),
}

SPEC_ALL_NULL_COLUMNS = {
    ('Documents', 'Document_Description'),
    ('Documents', 'Other_Details'),
}

SPEC_UNMATCHED_JOINS = {
    ('Documents', 'Document_ID'): [('Documents_with_Expenses', 'Document_ID'),
                                   ('Statements', 'Statement_ID'),
                                   ('Accounts', 'Statement_ID')],
    ('Documents_with_Expenses', 'Document_ID'): [('Documents', 'Document_ID')],
    ('Documents_with_Expenses', 'Budget_Type_Code'): [('Ref_Budget_Codes', 'Budget_Type_Code')],
    ('Accounts', 'Statement_ID'): [('Statements', 'Statement_ID'), ('Documents', 'Document_ID')],
    ('Statements', 'Statement_ID'): [('Accounts', 'Statement_ID'), ('Documents', 'Document_ID')],
    ('Documents', 'Project_ID'): [('Projects', 'Project_ID')],
    ('Documents', 'Document_Type_Code'): [('Ref_Document_Types', 'Document_Type_Code')],
    ('Ref_Budget_Codes', 'Budget_Type_Code'): [('Documents_with_Expenses', 'Budget_Type_Code')],
    ('Projects', 'Project_ID'): [('Documents', 'Project_ID')],
    ('Ref_Document_Types', 'Document_Type_Code'): [('Documents', 'Document_Type_Code')],
}

SPEC_TIES = {
    ('Documents_with_Expenses', 'Budget_Type_Code'): [1, 2, 3],
}

DATE_LO = dt.datetime(1970, 1, 1, 0, 0, 0)
DATE_HI = dt.datetime(2013, 12, 31, 23, 59, 59)
DATE_FMT = '%Y-%m-%d %H:%M:%S'

_DESC_PHRASES = ['Review on UK files', 'Chapter on private files', 'Book on USA files',
                 'Deontae files', 'Winona Book', 'Review on Canadian files']


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
    """Number of GENERATED rows per table = spec final size - compact size (min 0)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = SPEC_TABLE_SIZES.get(t)
            compact = schema.original_sizes.get(t, 0)
            if base is None:
                if rng.random() < 0.5:
                    min_c = 30 * rng.random()
                    sizes[t] = int(min_c + int(rng.random() * 200))
                else:
                    s = 1 + 30 * rng.random()
                    sizes[t] = int(min(s, 2500))
            else:
                sizes[t] = max(0, base - compact)
    return sizes


def _plant_enum_pool(schema, table: str, column: str, rng) -> list:
    """Return the enum pool for a column (exact case as listed; no query literals)."""
    return list(SPEC_ENUMS.get((table, column), []))


def _compose_group_values(pool: list, n: int, targets: list, rng) -> list:
    """Build n values from `pool` with group sizes from `targets` (1, 2, >=3)."""
    if not pool or n <= 0:
        return []
    values = []
    pi = 0
    ti = 0
    while len(values) < n:
        gs = targets[ti % len(targets)]
        v = pool[pi % len(pool)]
        values.extend([v] * gs)
        pi += 1
        ti += 1
    return values[:n]


def _plant_group_sizes(schema, table: str, column: str, n: int, rng, parent_pool: list = None) -> list:
    """Return a list of n values for a grouping column with planted group sizes 1, 2 and >= 3."""
    targets = SPEC_GROUP_SIZES.get((table, column))
    if not targets:
        return None
    if (table, column) in SPEC_ENUMS:
        pool = _plant_enum_pool(schema, table, column, rng)
    elif parent_pool:
        pool = list(parent_pool)
    else:
        pt, pc = schema.fks.get((table, column), (None, None))
        pool = list(schema.original_values.get((pt, pc), [])) if pt else []
        if not pool:
            pool = list(range(1, max(2, n) + 1))
    if not pool:
        return None
    return _compose_group_values(pool, n, targets, rng)


def _plant_agg_boundary(schema, table: str, column: str, n: int, rng, parent_pool: list = None) -> list:
    """Return a list of n values for a counted column with planted aggregate-boundary counts."""
    targets = SPEC_AGG_BOUNDARY.get((table, column))
    if not targets:
        return None
    if parent_pool:
        pool = list(parent_pool)
    else:
        pt, pc = schema.fks.get((table, column), (None, None))
        pool = list(schema.original_values.get((pt, pc), [])) if pt else []
        if not pool:
            pool = list(range(1, max(2, n) + 1))
    if not pool:
        return None
    return _compose_group_values(pool, n, [1, 2, 3], rng)


def _plant_duplicates(schema, table: str, column: str, n: int, rng, base_values: list) -> list:
    """Plant a 20-50 % duplicate share on a DISTINCT column, then adjust to be in range."""
    if (table, column) not in SPEC_DUP_COLUMNS or n < 2:
        return base_values
    out = list(base_values)
    non_null_idx = [i for i, v in enumerate(out) if v is not None]
    if len(non_null_idx) < 2:
        return out
    share = 0.2 + 0.3 * rng.random()
    n_dup = max(1, int(len(non_null_idx) * share))
    src = [out[rng.choice(non_null_idx)] for _ in range(n_dup)]
    positions = rng.sample(non_null_idx, min(n_dup, len(non_null_idx)))
    for pos, v in zip(positions, src):
        out[pos] = v
    for _ in range(20):
        nn = [v for v in out if v is not None]
        if len(nn) < 2:
            break
        distinct = len(set(nn))
        dup_share = 1.0 - distinct / len(nn)
        if 0.2 <= dup_share <= 0.5:
            break
        if dup_share < 0.2:
            counts = Counter(nn)
            uniq_pos = [i for i in non_null_idx if counts[out[i]] == 1]
            if not uniq_pos:
                break
            pos = rng.choice(uniq_pos)
            out[pos] = rng.choice(nn)
        else:
            counts = Counter(nn)
            dup_pos = [i for i in non_null_idx if counts[out[i]] > 1]
            if not dup_pos:
                break
            pos = rng.choice(dup_pos)
            out[pos] = _fresh_text(out[pos], rng)
    return out


def _fresh_text(v, rng) -> str:
    """A short descriptive phrase variant (prefix/suffix/dropped-character)."""
    s = str(v) if v is not None else 'item'
    u = rng.random()
    if u < 0.25:
        return s + ' ' + rng.choice(['copy', 'draft', 'v2', 'note'])
    if u < 0.5:
        return rng.choice(['New', 'Old', 'Draft']) + ' ' + s
    if u < 0.75 and len(s) > 1:
        return s[:-1]
    if len(s) > 1:
        return s[1:]
    return s + 'x'


def _plant_ties(schema, table: str, column: str, n: int, rng, values: list) -> list:
    """Plant at least two rows sharing each listed rank value (ties_for_order_limit)."""
    ranks = SPEC_TIES.get((table, column))
    if not ranks or n < 2:
        return values
    out = list(values)
    pool = [v for v in out if v is not None]
    if not pool:
        return out
    for _r in ranks:
        v = rng.choice(pool)
        p1 = rng.randrange(n)
        p2 = rng.randrange(n)
        if p2 == p1:
            p2 = (p1 + 1) % n
        out[p1] = v
        out[p2] = v
    return out


def _plant_nulls(schema, table: str, column: str, n: int, rng, values: list) -> list:
    """Plant at least one NULL row per nullable column (NULL rule)."""
    if (table, column) not in SPEC_NULL_COLUMNS or n < 1:
        return values
    out = list(values)
    if (table, column) in SPEC_ALL_NULL_COLUMNS:
        for i in range(n):
            out[i] = None
        if n > 1:
            pos = rng.randrange(n)
            out[pos] = rng.choice(_DESC_PHRASES)
        return out
    pos = rng.randrange(n)
    out[pos] = None
    ov = schema.original_values.get((table, column), [])
    if ov:
        null_share = sum(1 for v in ov if v is None) / len(ov)
        n_null = min(int(n * null_share), n - 1)
        for _ in range(max(0, n_null - 1)):
            p = rng.randrange(n)
            out[p] = None
    return out


def _plant_date_range(schema, table: str, column: str, n: int, rng, values: list) -> list:
    """Ensure Document_Date values are in the 1970-2013 range and parse under %Y-%m-%d %H:%M:%S."""
    if (table, column) != ('Documents', 'Document_Date'):
        return values
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        try:
            if isinstance(v, str):
                d = dt.datetime.strptime(v, DATE_FMT)
            elif isinstance(v, dt.datetime):
                d = v
            else:
                d = DATE_LO + dt.timedelta(seconds=rng.randint(0, int((DATE_HI - DATE_LO).total_seconds())))
        except (ValueError, TypeError):
            d = DATE_LO + dt.timedelta(seconds=rng.randint(0, int((DATE_HI - DATE_LO).total_seconds())))
        if d < DATE_LO:
            d = DATE_LO
        if d > DATE_HI:
            d = DATE_HI
        out.append(d.strftime(DATE_FMT))
    return out


def _plant_numeric_amount(schema, table: str, column: str, n: int, rng, values: list) -> list:
    """Constrain Accounts.Account_Details to numeric strings with 2-3 fractional digits, >= 0."""
    if (table, column) != ('Accounts', 'Account_Details'):
        return values
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        int_part = rng.randint(0, 20000)
        frac_digits = rng.choice([2, 3])
        frac = rng.randint(0, 10 ** frac_digits - 1)
        out.append('%d.%0*d' % (int_part, frac_digits, frac))
    return out


def _verify_duplicate_share(schema, table: str, column: str, values: list) -> bool:
    if (table, column) not in SPEC_DUP_COLUMNS:
        return True
    non_null = [v for v in values if v is not None]
    if len(non_null) < 2:
        return True
    distinct = len(set(non_null))
    dup_share = 1.0 - distinct / len(non_null)
    return 0.2 <= dup_share <= 0.5


def _verify_group_sizes(schema, table: str, column: str, values: list) -> bool:
    if (table, column) not in SPEC_GROUP_SIZES:
        return True
    counts = Counter(v for v in values if v is not None)
    sizes = set(counts.values())
    return 1 in sizes and 2 in sizes and any(s >= 3 for s in sizes)


def _verify_agg_boundary(schema, table: str, column: str, values: list) -> bool:
    if (table, column) not in SPEC_AGG_BOUNDARY:
        return True
    counts = Counter(v for v in values if v is not None)
    sizes = list(counts.values())
    return any(s > 2 for s in sizes) and any(s >= 2 for s in sizes)


def _verify_nulls(schema, table: str, column: str, values: list) -> bool:
    if (table, column) not in SPEC_NULL_COLUMNS:
        return True
    has_null = any(v is None for v in values)
    has_non_null = any(v is not None for v in values)
    if (table, column) in SPEC_ALL_NULL_COLUMNS:
        if len(values) > 1:
            return has_null and has_non_null
        return has_null
    return has_null and has_non_null


def _verify_date_format(schema, table: str, column: str, values: list) -> bool:
    if (table, column) != ('Documents', 'Document_Date'):
        return True
    for v in values:
        if v is None:
            continue
        try:
            d = dt.datetime.strptime(v, DATE_FMT)
        except (ValueError, TypeError):
            return False
        if d < DATE_LO or d > DATE_HI:
            return False
    return True


def _verify_ties(schema, table: str, column: str, values: list) -> bool:
    if (table, column) not in SPEC_TIES:
        return True
    counts = Counter(v for v in values if v is not None)
    return any(c >= 2 for c in counts.values())


def _verify_fk_membership(schema, inst: dict) -> list:
    """Return a list of unmet FK-membership descriptions (empty when all FKs are valid)."""
    unmet = []
    for (ct, cc), (pt, pc) in schema.fks.items():
        child_vals = inst.get(ct, {}).get(cc, [])
        parent_vals = set(v for v in inst.get(pt, {}).get(pc, []) if v is not None)
        bad = [v for v in child_vals if v is not None and v not in parent_vals]
        if bad:
            unmet.append('FK %s.%s -> %s.%s: %d bad values' % (ct, cc, pt, pc, len(bad)))
    return unmet


def build_random_instance(schema, literal_pool: dict, size, rng):
    """Build one random instance (fuzz.py:111-196) with specification-driven construction."""
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

    for t in order:
        tm = schema.tables[t]
        n = len(inst[t].get(tm.columns[0].name, [])) if tm.columns else 0
        if n == 0:
            continue
        for cm in tm.columns:
            col = cm.name
            key = (t, col)
            is_pk = cm.pk_pos > 0
            if key in SPEC_GROUP_SIZES and not is_pk:
                parent_pool = None
                pt, pc = schema.fks.get(key, (None, None))
                if pt is not None:
                    parent_pool = inst.get(pt, {}).get(pc)
                gs = _plant_group_sizes(schema, t, col, n, rng, parent_pool)
                if gs is not None:
                    inst[t][col] = gs
            if key in SPEC_AGG_BOUNDARY and not is_pk:
                parent_pool = None
                pt, pc = schema.fks.get(key, (None, None))
                if pt is not None:
                    parent_pool = inst.get(pt, {}).get(pc)
                ab = _plant_agg_boundary(schema, t, col, n, rng, parent_pool)
                if ab is not None:
                    inst[t][col] = ab
            if key in SPEC_ENUMS and key not in SPEC_GROUP_SIZES:
                pool = _plant_enum_pool(schema, t, col, rng)
                inst[t][col] = [rng.choice(pool) for _ in range(n)]
            if key in SPEC_TIES:
                inst[t][col] = _plant_ties(schema, t, col, n, rng, inst[t][col])
            if key in SPEC_DUP_COLUMNS:
                inst[t][col] = _plant_duplicates(schema, t, col, n, rng, inst[t][col])
            if key in SPEC_NULL_COLUMNS:
                inst[t][col] = _plant_nulls(schema, t, col, n, rng, inst[t][col])
            if key == ('Documents', 'Document_Date'):
                inst[t][col] = _plant_date_range(schema, t, col, n, rng, inst[t][col])
            if key == ('Accounts', 'Account_Details'):
                inst[t][col] = _plant_numeric_amount(schema, t, col, n, rng, inst[t][col])

    for t in order:
        tm = schema.tables[t]
        inst[t] = sample_fresh_primary_keys(tm, inst[t])
        inst[t] = drop_unique_duplicates(tm, inst[t])

    unmet = []
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            vals = inst[t].get(cm.name, [])
            if key in SPEC_DUP_COLUMNS and not _verify_duplicate_share(schema, t, cm.name, vals):
                unmet.append('dup_share %s.%s' % (t, cm.name))
            if key in SPEC_GROUP_SIZES and not _verify_group_sizes(schema, t, cm.name, vals):
                unmet.append('group_sizes %s.%s' % (t, cm.name))
            if key in SPEC_AGG_BOUNDARY and not _verify_agg_boundary(schema, t, cm.name, vals):
                unmet.append('agg_boundary %s.%s' % (t, cm.name))
            if key in SPEC_NULL_COLUMNS and not _verify_nulls(schema, t, cm.name, vals):
                unmet.append('null_rule %s.%s' % (t, cm.name))
            if key == ('Documents', 'Document_Date') and not _verify_date_format(schema, t, cm.name, vals):
                unmet.append('date_format %s.%s' % (t, cm.name))
            if key in SPEC_TIES and not _verify_ties(schema, t, cm.name, vals):
                unmet.append('ties %s.%s' % (t, cm.name))
    unmet.extend(_verify_fk_membership(schema, inst))

    return {t: inst[t] for t in schema.tables}, unmet
