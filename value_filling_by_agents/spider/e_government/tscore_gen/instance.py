"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the generation specification."""
import datetime as dt

from .values import (_init_sampler, BankSampler, DateSampler, EnumSampler, make_column_sampler)


SPEC_SIZES = {'Addresses': 15, 'Services': 15, 'Forms': 6, 'Individuals': 15, 'Organizations': 5,
              'Parties': 15, 'Organization_Contact_Individuals': 15, 'Party_Addresses': 15,
              'Party_Forms': 13, 'Party_Services': 15}

ENUMS = {
    ('Parties', 'payment_method_code'): ['Cheque', 'Credit Card', 'Cash', 'Direct Debit'],
    ('Party_Addresses', 'address_type_code'): ['Residence', 'Billing', 'Delivery'],
    ('Party_Forms', 'form_status_code'): ['Completed', 'Partially Completed', 'Not Started', 'Work In Progress'],
    ('Services', 'service_type_code'): ['Education', 'Welfare', 'Health'],
    ('Forms', 'form_type_code'): ['Basic', 'Complex'],
}

BANKS = {
    ('Addresses', 'line_1_number_building'): [
        '6862 Kaitlyn Knolls Suite 309', '6862 Kaitlyn Knolls', '6862 Kaitlyn Knollt',
        '6862 Kaitlyn Knolls x', '6862 kaitlyn knolls'],
    ('Addresses', 'state_province_county'): ['Colorado', 'Coloradp', 'Colorado x', 'colorado'],
    ('Addresses', 'country'): ['USA', 'usa'],
}

DISTINCT_COLUMNS = {('Addresses', 'town_city'),
                    ('Individuals', 'individual_first_name'),
                    ('Individuals', 'individual_middle_name'),
                    ('Individuals', 'individual_last_name')}

GROUP_SIZES = {('Organizations', 'organization_id'), ('Organizations', 'organization_name'),
               ('Parties', 'party_id'), ('Parties', 'party_email'),
               ('Forms', 'form_id'), ('Forms', 'form_name'),
               ('Party_Forms', 'form_id')}

DATE_ORDER = {
    ('Organization_Contact_Individuals', 'date_contact_to'): 'date_contact_from',
    ('Party_Addresses', 'date_address_to'): 'date_address_from',
    ('Party_Forms', 'date_fully_completed'): 'date_completion_started',
    ('Party_Services', 'booking_made_date'): 'service_datetime',
}

NULLABLE = {
    ('Organizations', 'organization_name'), ('Organization_Contact_Individuals', 'date_contact_to'),
    ('Party_Addresses', 'date_address_to'), ('Party_Forms', 'date_fully_completed'),
    ('Party_Services', 'booking_made_date'), ('Forms', 'service_id'),
    ('Organizations', 'date_formed'), ('Organizations', 'uk_vat_number'),
    ('Services', 'service_name'), ('Services', 'service_descriptio'),
    ('Forms', 'form_number'), ('Forms', 'form_name'), ('Forms', 'form_description'),
    ('Addresses', 'line_1_number_building'), ('Addresses', 'town_city'),
    ('Addresses', 'zip_postcode'), ('Addresses', 'state_province_county'),
    ('Addresses', 'country'), ('Individuals', 'individual_first_name'),
    ('Individuals', 'individual_middle_name'), ('Individuals', 'inidividual_phone'),
    ('Individuals', 'individual_email'), ('Individuals', 'individual_address'),
    ('Individuals', 'individual_last_name'), ('Parties', 'party_phone'), ('Parties', 'party_email'),
}

_FMT = '%Y-%m-%d %H:%M:%S'


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
    """FK child columns draw from the parent's in-memory values (compact+generated); empty -> NULL."""
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
    """Use the specification sizes with per-instance jitter (0-230 rows, level x4 up to 2500 in upstream)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = SPEC_SIZES.get(t, 12)
            if rng.random() < 0.3:
                base = 0
            else:
                base = max(1, int(base * rng.uniform(0.6, 1.4)))
            sizes[t] = min(230, base)
    return sizes


def _pk_floor(schema, table) -> int:
    """Smallest fresh integer PK above compact max (0 if not a single-col int pk)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 0
    return int(schema.max_pk.get(table, 0) or 0)


def _plant_nulls(cols: dict, col_meta_list, nullable_set, rng, chance=0.10) -> None:
    """The NULL rule: NULL as a value; each nullable column gets >=1 NULL and ~chance share."""
    for c in col_meta_list:
        if c.name not in nullable_set:
            continue
        vals = cols.get(c.name)
        if vals is None:
            continue
        n = len(vals)
        if n == 0:
            continue
        k = max(1, int(round(n * chance)))
        idx = rng.sample(range(n), min(k, n))
        for j in idx:
            if not c.notnull and c.pk_pos == 0:
                vals[j] = None


def _distinct_share(values: list, rng, lo=0.20, hi=0.50) -> list:
    """Force 20-50 % duplicates among the values (for DISTINCT-targeted columns)."""
    n = len(values)
    if n < 3:
        return values
    ndistinct_wanted = max(1, int(round(n * (1 - rng.uniform(lo, hi)))))
    if ndistinct_wanted >= n:
        return values
    base = [v for v in values[:ndistinct_wanted]]
    out = list(base) + [rng.choice(base) for _ in range(n - ndistinct_wanted)]
    rng.shuffle(out)
    return out


def _group_sizes(values: list, rng) -> list:
    """Approximate the GROUP(l) 1/2/>=3 target by planting a few repeated keys."""
    n = len(values)
    if n < 6:
        return values
    out = [values[0], values[1], values[1]]
    big = values[2]
    out += [big] * (n - 3)
    rng.shuffle(out)
    return out


def _date_after(from_val, rng, fmt=_FMT):
    """Return a date string >= from_val (non-NULL)."""
    if from_val is None:
        lo, hi = dt.datetime(2016, 1, 1), dt.datetime(2018, 3, 31)
        d = lo + dt.timedelta(seconds=rng.randint(0, int((hi - lo).total_seconds())))
        return d.strftime(fmt)
    try:
        base = dt.datetime.strptime(str(from_val)[:19], fmt)
    except (ValueError, TypeError):
        base = dt.datetime(2016, 1, 1)
    hi = dt.datetime(2018, 3, 31, 23, 59, 59)
    if base > hi:
        return base.strftime(fmt)
    d = base + dt.timedelta(seconds=rng.randint(0, max(0, int((hi - base).total_seconds()))))
    return d.strftime(fmt)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) honoring the generation specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            if key in ENUMS:
                samplers[key] = EnumSampler(ENUMS[key], rng)
            elif key in BANKS:
                samplers[key] = BankSampler(BANKS[key], rng)
            else:
                samplers[key] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
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
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            floor = _pk_floor(schema, t)
            if floor > 0:
                cols[pk] = [floor + i + 1 for i in range(n)]
        for key in list(cols.keys()):
            if (t, key) in DISTINCT_COLUMNS:
                cols[key] = _distinct_share(cols[key], rng)
            if (t, key) in GROUP_SIZES and n >= 6:
                cols[key] = _group_sizes(cols[key], rng)
        for (tt, cto), cfrom in DATE_ORDER.items():
            if tt != t or cfrom not in cols:
                continue
            cols[cto] = [_date_after(cols[cfrom][i], rng) for i in range(len(cols[cfrom]))]
        if t == 'Party_Services':
            if 'booking_id' in cols:
                cols['booking_id'] = [1 + i for i in range(n)]
            if 'service_id' in cols:
                cols['service_id'] = [max(1, int(v)) if isinstance(v, int) and v > 0 else 1
                                      for v in cols['service_id']]
        nullable_set = {c for (tt, c) in NULLABLE if tt == t}
        _plant_nulls(cols, tm.columns, nullable_set, rng, chance=0.10)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        existing = schema.existing_pks.get(t)
        if existing and tm.primary_key:
            keep = []
            for i in range(len(next(iter(cols.values()))) if cols else 0):
                k = tuple(cols[c][i] for c in tm.primary_key if c in cols)
                if len(k) == len(tm.primary_key) and k in existing:
                    continue
                keep.append(i)
            cols = _filter(cols, keep)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
