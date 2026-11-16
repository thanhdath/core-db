"""Random instance construction (fuzz/fuzz.py:83-196) + patch 64 spec construction."""
import random

from .spec import (
    SIZES, ENUM_POOLS, BOUNDARY_VALUES, LIKE_VARIANTS, NULL_RATES, DUP_TARGETS, GROUP_TARGETS,
    UNMATCHED, COPY_DEPENDENCIES, pool_for, null_rate, is_nullable, is_copied, _cast, _perturb,
    _pick, _datetime_in_range, derive_invoice_total, derive_invoice_billing,
    derive_invoice_line_unit_price, derive_employee_hire_date, derive_employee_reports_to,
    derive_customer_email, derive_customer_support_rep, derive_track_name,
    derive_track_milliseconds, derive_track_bytes, derive_invoice_line_quantity,
    derive_invoice_line_unit_price_nonneg, derive_invoice_total_nonneg, derive_artist_name,
    derive_genre_name, derive_mediatype_name, derive_playlist_name, derive_album_title,
)


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


def _retained_keys(inst: dict, table: str, col: str) -> list:
    """FINAL retained parent key list (after PK dedup) for a parent column."""
    return [v for v in inst.get(table, {}).get(col, []) if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's FINAL retained key list with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _retained_keys(instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
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


def _spec_sizes(schema, rng) -> dict:
    """Per-instance sizes from spec: spec table sizes, with small variation."""
    out = {}
    for t in schema.tables:
        base = SIZES.get(t, 30)
        jitter = int(base * rng.uniform(-0.2, 0.2))
        out[t] = max(1, base + jitter)
    return out


def _build_pool(schema, table, table_meta, literal_pool, rng):
    """Build a per-column pool of values (observed + pool literals + boundary)."""
    pools = {}
    for cm in table_meta.columns:
        key = (table, cm.name)
        if key in schema.fks:
            continue
        vals = []
        observed = schema.original_values.get(key, [])
        vals.extend([str(v) for v in observed if v is not None])
        vals.extend(pool_for(table, cm.name))
        vals.extend(literal_pool.get(key, []))
        for (t, c), v in literal_pool.items():
            if c == cm.name and t != table:
                vals.extend(v)
        seen = set()
        uniq = []
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        pools[cm.name] = uniq
    return pools


def _sample_column(table, cm, table_meta, pools, rng, used, n, schema, literal_pool):
    """Sample n values for one column."""
    key = (table, cm.name)
    if key in schema.fks:
        return None
    pool = pools.get(cm.name, [])
    if not pool:
        pool = [str(v) for v in schema.original_values.get(key, []) if v is not None]
    if cm.pk_pos > 0:
        if len(table_meta.primary_key) == 1:
            start = max(used) + 1 if used else 1
            return [start + i for i in range(n)]
        return [rng.randint(1, 100000) for _ in range(n)]
    if cm.unique:
        return [rng.choice(pool) if pool else _perturb('', rng, cm.type_str) for _ in range(n)]
    out = []
    for _ in range(n):
        if pool and rng.random() < 0.7:
            v = _pick(pool, rng, cm.type_str)
        else:
            v = _pick(pool, rng, cm.type_str) if pool else _perturb('', rng, cm.type_str)
        if rng.random() < 0.1:
            v = _perturb(v, rng, cm.type_str)
        out.append(v)
    return out


def _reserve_unmatched(inst, schema, rng):
    """Deterministically reserve parent rows with no child (unmatched_join_rows targets)."""
    for (pt, pc), ct in UNMATCHED.items():
        if pt not in inst or ct not in inst:
            continue
        pvals = _retained_keys(inst, pt, pc)
        if not pvals:
            continue
        child_col = None
        for (c_t, c_c), (p_t, p_c) in schema.fks.items():
            if c_t == ct and p_t == pt and p_c == pc:
                child_col = c_c
                break
        if child_col is None or child_col not in inst[ct]:
            continue
        cvals = inst[ct][child_col]
        referenced = {v for v in cvals if v is not None}
        unused = [v for v in pvals if v not in referenced]
        if unused:
            continue
        victim_parent = pvals[0]
        idxs = [i for i, v in enumerate(cvals) if v == victim_parent]
        if not idxs:
            continue
        i = idxs[0]
        others = [v for v in pvals if v != victim_parent]
        if others:
            cvals[i] = rng.choice(others)
        else:
            pass


def _enforce_group_sizes(inst, schema, rng):
    """Deterministically produce groups of size 1, 2 and >=3 for GROUP_TARGETS columns."""
    for (ct, cc), (pt, pc) in GROUP_TARGETS.items():
        if ct not in inst or pt not in inst:
            continue
        if cc not in inst[ct]:
            continue
        pvals = _retained_keys(inst, pt, pc)
        if len(pvals) < 3:
            continue
        cvals = inst[ct][cc]
        n = len(cvals)
        if n < 6:
            continue
        keys = list(pvals)
        rng.shuffle(keys)
        k1, k2, k3 = keys[0], keys[1], keys[2]
        assign = [k1] + [k2, k2] + [k3, k3, k3]
        rest = [rng.choice(keys) for _ in range(n - len(assign))]
        new = assign + rest
        rng.shuffle(new)
        inst[ct][cc] = new


def _enforce_duplicates(inst, schema, rng):
    """Ensure 20-50% duplicate share on DUP_TARGETS columns (duplicates_for_distinct)."""
    for (t, c), share in DUP_TARGETS.items():
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        n = len(vals)
        if n < 4:
            continue
        from collections import Counter
        cnt = Counter(v for v in vals if v is not None)
        dup_rows = sum(k for v, k in cnt.items() if k > 1)
        target = int(round(n * share))
        if dup_rows >= target:
            continue
        nonnull = [v for v in vals if v is not None]
        if not nonnull:
            continue
        need = target - dup_rows
        idxs = [i for i, v in enumerate(vals) if v is not None]
        rng.shuffle(idxs)
        for i in idxs[:need]:
            vals[i] = rng.choice(nonnull)


def _revalidate_fks(inst, schema, rng):
    """Final safety net: every non-NULL FK value must exist in the retained parent key set."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        pvals = _retained_keys(inst, pt, pc)
        pset = set(pvals)
        cvals = inst[ct][cc]
        for i, v in enumerate(cvals):
            if v is None:
                continue
            if v in pset:
                continue
            cvals[i] = rng.choice(pvals) if pvals else None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + spec construction."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = size if size is not None else _spec_sizes(schema, rng)
    pools = {}
    for t in order:
        pools[t] = _build_pool(schema, t, schema.tables[t], literal_pool, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        cols = {}
        used = set()
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            vals = _sample_column(t, cm, tm, pools[t], rng, used, n, schema, literal_pool)
            if vals is None:
                continue
            cols[cm.name] = vals
            if cm.pk_pos > 0:
                used.update(vals)
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk_cols)
        cols = sample_fresh_primary_keys(tm, cols)
        inst[t] = cols
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = _retained_keys(inst, t, pc)
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
    _reserve_unmatched(inst, schema, rng)
    _enforce_group_sizes(inst, schema, rng)
    _enforce_duplicates(inst, schema, rng)
    _apply_spec_rules(inst, schema, rng)
    _revalidate_fks(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}


def _plant_nulls(inst, schema, rng):
    """Plant NULLs LAST for every nullable column: compact share, at least one, never overwrite."""
    for t, cols in inst.items():
        tm = schema.tables[t]
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            key = (t, cm.name)
            if key not in cols:
                continue
            if is_copied(t, cm.name):
                continue
            n = len(cols[cm.name])
            if n == 0:
                continue
            rate = null_rate(t, cm.name)
            n_null = max(1, int(round(n * rate)))
            n_null = min(n_null, n)
            idxs = rng.sample(range(n), n_null)
            for i in idxs:
                cols[cm.name][i] = None


def _apply_spec_rules(inst, schema, rng):
    """Apply spec-derived rules in construction (derived first, NULLs last)."""
    if 'Invoice' in inst and 'Customer' in inst:
        cust = inst['Customer']
        cust_id_to_idx = {c: i for i, c in enumerate(cust.get('CustomerId', []))}
        inv = inst['Invoice']
        inv_cids = inv.get('CustomerId', [])
        billing = derive_invoice_billing(cust, cust_id_to_idx, inv_cids)
        for col, vals in billing.items():
            if col in inv:
                inv[col] = vals
    if 'InvoiceLine' in inst and 'Track' in inst:
        tr = inst['Track']
        tr_id_to_idx = {t: i for i, t in enumerate(tr.get('TrackId', []))}
        il = inst['InvoiceLine']
        line_tids = il.get('TrackId', [])
        if 'UnitPrice' in il:
            il['UnitPrice'] = derive_invoice_line_unit_price(tr, tr_id_to_idx, line_tids)
    if 'Employee' in inst:
        emp = inst['Employee']
        ids = [e for e in emp.get('EmployeeId', []) if e is not None]
        n_emp = len(emp.get('EmployeeId', []))
        for i in range(n_emp):
            if 'HireDate' in emp and 'BirthDate' in emp:
                emp['HireDate'][i] = derive_employee_hire_date(emp['BirthDate'][i], rng)
            if 'ReportsTo' in emp:
                emp['ReportsTo'][i] = derive_employee_reports_to(emp['EmployeeId'][i], rng, ids)
    if 'Customer' in inst:
        cust = inst['Customer']
        n_c = len(cust.get('CustomerId', []))
        for i in range(n_c):
            if 'Email' in cust:
                cust['Email'][i] = derive_customer_email(cust['Email'][i], rng)
    if 'Track' in inst:
        tr = inst['Track']
        n_t = len(tr.get('TrackId', []))
        for i in range(n_t):
            if 'Name' in tr:
                tr['Name'][i] = derive_track_name(tr['Name'][i], rng)
            if 'Milliseconds' in tr:
                tr['Milliseconds'][i] = derive_track_milliseconds(tr['Milliseconds'][i], rng)
            if 'Bytes' in tr:
                tr['Bytes'][i] = derive_track_bytes(tr['Bytes'][i], rng)
    if 'InvoiceLine' in inst:
        il = inst['InvoiceLine']
        n_il = len(il.get('InvoiceLineId', []))
        for i in range(n_il):
            if 'Quantity' in il:
                il['Quantity'][i] = derive_invoice_line_quantity(il['Quantity'][i], rng)
            if 'UnitPrice' in il:
                il['UnitPrice'][i] = derive_invoice_line_unit_price_nonneg(il['UnitPrice'][i], rng)
    for t, col in [('Artist', 'Name'), ('Genre', 'Name'), ('MediaType', 'Name'), ('Playlist', 'Name')]:
        if t in inst and col in inst[t]:
            for i in range(len(inst[t][col])):
                inst[t][col][i] = derive_artist_name(inst[t][col][i], rng)
    if 'Album' in inst and 'Title' in inst['Album']:
        for i in range(len(inst['Album']['Title'])):
            inst['Album']['Title'][i] = derive_album_title(inst['Album']['Title'][i], rng)

    _plant_nulls(inst, schema, rng)

    if 'Invoice' in inst and 'InvoiceLine' in inst:
        il = inst['InvoiceLine']
        inv = inst['Invoice']
        if 'Total' in inv:
            totals = derive_invoice_total(il, inv.get('InvoiceId', []))
            inv['Total'] = [derive_invoice_total_nonneg(t, rng) for t in totals]
