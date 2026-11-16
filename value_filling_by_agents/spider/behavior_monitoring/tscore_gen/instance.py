"""Random instance construction (fuzz/fuzz.py:83-196) plus the specification's by-construction rules."""
import datetime as dt

from .values import _init_sampler

TABLE_SIZES = {
    'Ref_Address_Types': 2, 'Ref_Detention_Type': 3, 'Ref_Incident_Type': 3,
    'Addresses': 20, 'Students': 15, 'Teachers': 15, 'Assessment_Notes': 15,
    'Behavior_Incident': 15, 'Detention': 15, 'Student_Addresses': 20, 'Students_in_Detention': 15,
}

ENUM_POOLS = {
    ('Ref_Address_Types', 'address_type_code'): ['BILL', 'HOME'],
    ('Ref_Detention_Type', 'detention_type_code'): ['AFTER', 'BREAK ', 'LUNCH'],
    ('Ref_Incident_Type', 'incident_type_code'): ['DISTURB', 'NOISE', 'VIOLENCE'],
    ('Behavior_Incident', 'incident_type_code'): ['DISTURB', 'NOISE', 'VIOLENCE'],
    ('Detention', 'detention_type_code'): ['AFTER', 'BREAK ', 'LUNCH'],
    ('Teachers', 'gender'): ['0', '1'],
}

BOUNDARY_EXACT = {
    ('Addresses', 'zip_postcode'): ['917', '918', '919', '918', '919'],
    ('Students', 'last_name'): ['Fahey', 'fahey', 'Rohan', 'rohan'],
    ('Teachers', 'last_name'): ['Schultz', 'schultz', 'Medhurst', 'medhurst'],
    ('Behavior_Incident', 'incident_type_code'): ['NOISE', 'noise'],
    ('Ref_Incident_Type', 'incident_type_code'): ['NOISE', 'noise'],
    ('Addresses', 'state_province_county'): ['Wisconsin', 'wisconsin'],
}
LIKE_NEAR = {('Addresses', 'state_province_county'): ['Texas', 'texas', 'Texas ']}

DUP_SHARE_COLUMNS = {
    ('Addresses', 'city'), ('Addresses', 'line_1'), ('Teachers', 'first_name'),
    ('Teachers', 'email_address'), ('Assessment_Notes', 'date_of_notes'),
    ('Behavior_Incident', 'date_incident_start'), ('Behavior_Incident', 'date_incident_end'),
}

GROUP_SIZE_COLUMNS = {
    ('Behavior_Incident', 'student_id'), ('Student_Addresses', 'student_id'),
    ('Student_Addresses', 'address_id'), ('Assessment_Notes', 'student_id'),
    ('Assessment_Notes', 'teacher_id'), ('Detention', 'teacher_id'),
    ('Students', 'first_name'), ('Ref_Detention_Type', 'detention_type_description'),
}

NULL_TARGETS = {
    ('Assessment_Notes', 'student_id'): 0.0,
    ('Students', 'other_student_details'): 0.733,
    ('Behavior_Incident', 'recommendations'): 0.8,
    ('Teachers', 'other_details'): 0.933,
    ('Addresses', 'line_2'): 1.0, ('Addresses', 'line_3'): 1.0,
    ('Addresses', 'other_address_details'): 1.0,
    ('Assessment_Notes', 'text_of_notes'): 1.0, ('Assessment_Notes', 'other_details'): 1.0,
    ('Behavior_Incident', 'incident_summary'): 1.0, ('Behavior_Incident', 'other_details'): 1.0,
    ('Detention', 'detention_summary'): 1.0, ('Detention', 'other_details'): 1.0,
    ('Student_Addresses', 'date_address_to'): 0.0,
}

DATE_ORDER = [
    ('Behavior_Incident', 'date_incident_start', 'date_incident_end'),
    ('Detention', 'datetime_detention_start', 'datetime_detention_end'),
    ('Student_Addresses', 'date_address_from', 'date_address_to'),
    ('Students', 'date_first_rental', 'date_left_university'),
]

DATE_LO = dt.datetime(2017, 1, 1)
DATE_HI = dt.datetime(2018, 3, 31, 23, 59, 59)
DATE_FMT = '%Y-%m-%d %H:%M:%S'

UNMATCHED_PARENT = {
    ('Addresses', 'address_id'), ('Ref_Detention_Type', 'detention_type_code'),
    ('Ref_Incident_Type', 'incident_type_code'),
}

TIE_RANK1 = {('Ref_Incident_Type', 'incident_type_description')}

RENTAL_LO, RENTAL_HI = 500.0, 1500.0


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
    """Specification table sizes per instance (fixed), falling back to the fuzz size choice."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            if t in TABLE_SIZES:
                sizes[t] = TABLE_SIZES[t]
    if not sizes:
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


def _rand_dt(rng) -> dt.datetime:
    span = int((DATE_HI - DATE_LO).total_seconds())
    return DATE_LO + dt.timedelta(seconds=rng.randint(0, span))


def _fmt_dt(d) -> str:
    return d.strftime(DATE_FMT)


def _parse_dt(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, str):
        try:
            return dt.datetime.strptime(v, DATE_FMT)
        except ValueError:
            return None
    return None


def _is_datetime_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _is_numeric_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))


def _boundary_values(table: str, col: str) -> list:
    """Exact comparison-boundary target multiset for a column (per-column exception list)."""
    out = list(BOUNDARY_EXACT.get((table, col), []))
    out += list(LIKE_NEAR.get((table, col), []))
    pool = ENUM_POOLS.get((table, col))
    if pool is not None:
        out = [v for v in out if v in pool]
    return out


def _apply_duplicate_share(values: list, rng) -> list:
    """Force a 20-50% duplicate share on a DISTINCT column by copying existing non-NULL values."""
    n = len(values)
    if n < 2:
        return values
    share = rng.uniform(0.2, 0.5)
    k = max(1, int(round(n * share)))
    idx = [i for i in range(n) if values[i] is not None]
    if len(idx) < 2:
        return values
    rng.shuffle(idx)
    k = min(k, len(idx) - 1)
    for j in range(k):
        src = idx[j]
        dst = idx[k + j] if k + j < len(idx) else idx[j]
        if values[src] is not None:
            values[dst] = values[src]
    return values


def _apply_group_sizes(values: list, rng) -> list:
    """Force groups of size 1, 2 and >= 3 by copying existing non-NULL values."""
    n = len(values)
    if n < 6:
        return values
    idx = [i for i in range(n) if values[i] is not None]
    if len(idx) < 6:
        return values
    rng.shuffle(idx)
    values[idx[2]] = values[idx[1]]
    values[idx[4]] = values[idx[3]]
    values[idx[5]] = values[idx[3]]
    return values


def _apply_tie_rank1(values: list, rng) -> list:
    """Force a tie at rank 1 (two equal non-NULL values)."""
    idx = [i for i in range(len(values)) if values[i] is not None]
    if len(idx) >= 2:
        values[idx[1]] = values[idx[0]]
    return values


def _apply_null_rule(table: str, col: str, values: list, rng, nullable: bool, compact_share: float) -> list:
    """NULL is a value to generate, for EVERY nullable column (interface rule 7)."""
    if not nullable:
        return values
    n = len(values)
    if n == 0:
        return values
    share = NULL_TARGETS.get((table, col), compact_share)
    k = int(round(n * share))
    if k == 0:
        k = 1
    if k > n:
        k = n
    idx = list(range(n))
    rng.shuffle(idx)
    for j in range(k):
        values[idx[j]] = None
    return values


def _apply_date_order(table: str, start_col: str, end_col: str, cols: dict, rng) -> None:
    """end >= start (or NULL) for every row; planted NULLs are never replaced."""
    if start_col not in cols or end_col not in cols:
        return
    starts, ends = cols[start_col], cols[end_col]
    end_has_dup = (table, end_col) in DUP_SHARE_COLUMNS
    for i in range(len(starts)):
        s = _parse_dt(starts[i])
        e = _parse_dt(ends[i])
        if s is None:
            continue
        if e is None:
            if ends[i] is not None:
                ends[i] = _fmt_dt(s + dt.timedelta(seconds=rng.randint(0, 86400 * 30)))
            continue
        if e < s:
            if end_has_dup and starts[i] is not None:
                starts[i] = _fmt_dt(e - dt.timedelta(seconds=rng.randint(0, 86400 * 30)))
            else:
                ends[i] = _fmt_dt(s + dt.timedelta(seconds=rng.randint(0, 86400 * 30)))


def _apply_rental_range(values: list, rng) -> list:
    """monthly_rental >= 0, uniform in [500, 1500] with 4 decimals."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = rng.uniform(RENTAL_LO, RENTAL_HI)
        if f < 0:
            f = rng.uniform(RENTAL_LO, RENTAL_HI)
        out.append(round(f, 4))
    return out


def _apply_enum(table: str, col: str, values: list, rng) -> list:
    """Pick from the enum pool; exact listed codes only (no case-variant near-duplicates)."""
    pool = ENUM_POOLS.get((table, col))
    if not pool:
        return values
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        out.append(rng.choice(pool))
    return out


def _apply_boundary(table: str, col: str, values: list, rng) -> list:
    """Restrict the column to the exact comparison-boundary target multiset (cycled over non-NULL rows)."""
    bv = _boundary_values(table, col)
    if not bv:
        return values
    n = len(values)
    if n == 0:
        return values
    idx = [i for i in range(n) if values[i] is not None]
    if not idx:
        return values
    for j, i in enumerate(idx):
        values[i] = bv[j % len(bv)]
    return values


def _apply_tie_rank1_col(table: str, col: str, values: list, rng) -> list:
    if (table, col) in TIE_RANK1:
        return _apply_tie_rank1(values, rng)
    return values


def _compact_pk_values(schema, table: str, col: str) -> list:
    """Existing compact values of a parent key column (for FK drawing and PK offset)."""
    return [v for v in schema.original_values.get((table, col), []) if v is not None]


def _next_pk_start(schema, table: str, col: str) -> int:
    """First generated PK: max(existing compact PK)+1 (or 1 if none)."""
    vals = _compact_pk_values(schema, table, col)
    ints = [int(v) for v in vals if isinstance(v, int) or (isinstance(v, str) and v.isdigit())]
    return (max(ints) + 1) if ints else 1


def _enum_pk_values(schema, table: str, col: str, n: int, rng) -> list:
    """VARCHAR PK codes drawn from the enum pool (cycling), fresh against the compact rows."""
    pool = ENUM_POOLS.get((table, col))
    existing = {str(v) for v in _compact_pk_values(schema, table, col)}
    if pool:
        fresh = [v for v in pool if v not in existing]
        if fresh:
            return [fresh[i % len(fresh)] for i in range(n)]
    out = []
    k = 1
    while len(out) < n:
        cand = 'GEN%03d' % k
        k += 1
        if cand not in existing:
            out.append(cand)
    return out


def _compact_null_share(schema, table: str, col: str) -> float:
    """NULL share of a column in the compact database (0.0 if no rows)."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification rules by construction."""
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

    final_keys: dict = {}
    inst: dict = {}

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}

        for pk_col in tm.primary_key:
            if pk_col not in cols:
                continue
            cm = next(c for c in tm.columns if c.name == pk_col)
            if _is_numeric_column(cm):
                start = _next_pk_start(schema, t, pk_col)
                cols[pk_col] = list(range(start, start + n))
            else:
                cols[pk_col] = _enum_pk_values(schema, t, pk_col, n, rng)

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = final_keys.get((pt, pc), [])
            if not parent_vals:
                parent_vals = _compact_pk_values(schema, pt, pc)
            if parent_vals:
                cols[cm.name] = [rng.choice(parent_vals) for _ in range(n)]
            else:
                cols[cm.name] = [None] * n

        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)

        for cm in tm.columns:
            if cm.name not in cols:
                continue
            key = (t, cm.name)
            nullable = (not cm.notnull) and cm.pk_pos == 0
            is_pk = cm.pk_pos > 0
            is_fk = key in schema.fks
            vals = cols[cm.name]
            vals = _apply_null_rule(t, cm.name, vals, rng, nullable,
                                    _compact_null_share(schema, t, cm.name))
            if key in ENUM_POOLS and not is_fk:
                vals = _apply_enum(t, cm.name, vals, rng)
            if (key in BOUNDARY_EXACT or key in LIKE_NEAR) and not is_fk:
                vals = _apply_boundary(t, cm.name, vals, rng)
            if key in DUP_SHARE_COLUMNS and not is_pk:
                vals = _apply_duplicate_share(vals, rng)
            if key in GROUP_SIZE_COLUMNS and not is_pk:
                vals = _apply_group_sizes(vals, rng)
            if not is_pk:
                vals = _apply_tie_rank1_col(t, cm.name, vals, rng)
            if t == 'Student_Addresses' and cm.name == 'monthly_rental':
                vals = _apply_rental_range(vals, rng)
            cols[cm.name] = vals

        for (dt_table, s_col, e_col) in DATE_ORDER:
            if dt_table == t:
                _apply_date_order(t, s_col, e_col, cols, rng)

        inst[t] = cols

        for pk_col in tm.primary_key:
            if pk_col in cols:
                compact = _compact_pk_values(schema, t, pk_col)
                gen = [v for v in cols[pk_col] if v is not None]
                final_keys[(t, pk_col)] = list(compact) + list(gen)

    for (pt, pc) in UNMATCHED_PARENT:
        if pt not in inst or pc not in inst[pt]:
            continue
        parent_vals = [v for v in inst[pt][pc] if v is not None]
        if len(parent_vals) < 2:
            continue
        reserved = parent_vals[-1]
        allowed = [v for v in parent_vals if v != reserved]
        if not allowed:
            continue
        for (ct, cc), (p_t, p_c) in schema.fks.items():
            if p_t == pt and p_c == pc and ct in inst and cc in inst[ct]:
                child_vals = inst[ct][cc]
                for i, v in enumerate(child_vals):
                    if v == reserved:
                        child_vals[i] = rng.choice(allowed)
                inst[ct][cc] = child_vals

    return {t: inst[t] for t in schema.tables}
