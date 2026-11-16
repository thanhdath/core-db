"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, apply_null_rule

DOMAINS = {
    ('artist', 'Artist_ID'): (1, 10 ** 6),
    ('artist', 'Year_Join'): (1900, 2025),
    ('artist', 'Age'): (18, 100),
    ('exhibition', 'Exhibition_ID'): (1, 10 ** 6),
    ('exhibition', 'Year'): (2000, 2025),
    ('exhibition', 'Ticket_Price'): (0.0, 100.0),
    ('exhibition_record', 'Attendance'): (0, 10 ** 6),
}

BOUNDARIES = {
    ('artist', 'Year_Join'): [1989, 1990, 1991],
    ('exhibition', 'Year'): [2003, 2004, 2005],
    ('exhibition', 'Ticket_Price'): [9.99, 10.0, 10.01],
    ('exhibition_record', 'Attendance'): [9, 10, 11, 99, 100, 101, 199, 200, 201],
}

TABLE_SIZES = {'artist': 7, 'exhibition': 6, 'exhibition_record': 13}

NULL_FLOOR = 0.15

DATE_POOL = ['December 2', 'December 5', 'December 7', 'December 9', 'December 12',
             'December 13', 'December 16', 'February 19', 'February 22', 'March 1',
             'March 8', 'April 4', 'April 15', 'May 6', 'May 20', 'June 9',
             'July 4', 'August 11', 'September 23', 'October 5', 'November 30']
_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']
_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> tuple:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns, 0
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key if c in columns)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep), n - len(keep)


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples: list) -> dict:
    """Drop rows repeating any UNIQUE tuple (single or composite)."""
    if not columns:
        return columns
    n = len(next(iter(columns.values())))
    keep = list(range(n))
    for t, cols in unique_tuples:
        if t != table_meta.name:
            continue
        if not all(c in columns for c in cols):
            continue
        seen = set()
        nk = []
        for i in keep:
            k = tuple(columns[c][i] for c in cols)
            if k in seen:
                continue
            seen.add(k)
            nk.append(i)
        keep = nk
    return _filter(columns, keep)


def _compact_rows(schema, table: str) -> dict:
    """Compact rows of a table as {col: [values]} (read-only, already in schema)."""
    tm = schema.tables[table]
    return {c.name: list(schema.original_values.get((table, c.name), [])) for c in tm.columns}


def _null_share(schema, table: str, col: str) -> float:
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return NULL_FLOOR
    n_null = sum(1 for v in vals if v is None)
    share = n_null / len(vals)
    return max(share, NULL_FLOOR)


def _next_pk_start(schema, table: str, col: str) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, (int, float))]
    return int(max(vals)) + 1 if vals else 1


def choose_table_sizes(schema, rng) -> dict:
    """Per-instance table sizes: specification sizes, with small random variation."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t)
        if base is None:
            base = 5
        sizes[t] = max(1, base + rng.randint(-2, 2))
    return sizes


def _is_numeric_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'real', 'float', 'double', 'decimal', 'numeric', 'number'))


def _is_text_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'varchar'))


def _inject_boundaries(vals: list, boundaries: list, rng, is_int: bool, lo, hi) -> list:
    """Guarantee every boundary literal (plus one step each side, where reachable) appears at least once."""
    if not boundaries or not vals:
        return list(vals)
    planted = []
    step = 1 if is_int else 0.01
    for b in boundaries:
        cand = [b]
        lo_b = b - step
        hi_b = b + step
        if lo is None or lo_b >= lo:
            cand.append(lo_b)
        if hi is None or hi_b <= hi:
            cand.append(hi_b)
        for c in cand:
            v = int(round(c)) if is_int else round(float(c), 2)
            if lo is not None and v < lo:
                continue
            if hi is not None and v > hi:
                continue
            planted.append(v)
    if not planted:
        return list(vals)
    out = list(vals)
    n = len(out)
    positions = rng.sample(range(n), min(len(planted), n)) if n >= len(planted) else \
        [i % n for i in range(len(planted))]
    rng.shuffle(positions)
    for v, pos in zip(planted, positions):
        out[pos] = v
    return out


def _fresh_dates(n: int, rng, fresh_share: float = 0.3) -> list:
    """Expanding fresh date generator: yields N distinct 'Month D' strings."""
    n_fresh = max(1, int(round(fresh_share * n)))
    n_pool = n - n_fresh
    pool = list(DATE_POOL)
    rng.shuffle(pool)
    out = [pool[i % len(pool)] for i in range(n_pool)]
    used = set(out) | set(DATE_POOL)
    minted = []
    guard = 0
    while len(minted) < n_fresh and guard < 10000:
        guard += 1
        m = rng.randrange(12)
        d = rng.randint(1, _MONTH_DAYS[m])
        s = '%s %d' % (_MONTHS[m], d)
        if s in used:
            continue
        used.add(s)
        minted.append(s)
    while len(minted) < n_fresh:
        minted.append('%s %d' % (_MONTHS[rng.randrange(12)], rng.randint(1, 28)))
    out.extend(minted)
    rng.shuffle(out)
    return out


def _distinct_dates_for_group(k: int, rng, used: set) -> list:
    """Return k distinct 'Month D' strings not in `used`; adds them to `used`."""
    out = []
    guard = 0
    while len(out) < k and guard < 100000:
        guard += 1
        m = rng.randrange(12)
        d = rng.randint(1, _MONTH_DAYS[m])
        s = '%s %d' % (_MONTHS[m], d)
        if s in used:
            continue
        used.add(s)
        out.append(s)
    while len(out) < k:
        s = '%s %d' % (_MONTHS[rng.randrange(12)], rng.randint(1, 28))
        if s not in used:
            used.add(s)
            out.append(s)
    return out


def _build_table(schema, table: str, n: int, rng, literal_pool: dict, parent_rows: dict,
                 reserved_parent_keys: dict) -> dict:
    """Build n generated rows for one table by construction."""
    tm = schema.tables[table]
    cols: dict = {}

    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks:
            continue
        domain = DOMAINS.get(key)
        boundaries = [] if cm.pk_pos > 0 else BOUNDARIES.get(key, [])
        if _is_text_col(cm) and cm.name.lower() == 'date':
            cols[cm.name] = _fresh_dates(n, rng)
            continue
        sampler = _init_sampler(cm, literal_pool.get(key, []),
                                schema.original_values.get(key, []), 0.2, rng,
                                len(tm.primary_key), domain=domain, boundaries=boundaries)
        vals = [sampler.sample() for _ in range(n)]
        if cm.pk_pos > 0 and _is_numeric_col(cm):
            start = _next_pk_start(schema, table, cm.name)
            vals = [start + i for i in range(n)]
        if boundaries:
            lo, hi = domain if domain else (None, None)
            vals = _inject_boundaries(vals, boundaries, rng, _is_numeric_col(cm), lo, hi)
        cols[cm.name] = vals

    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(parent_rows.get(pt, {}).get(pc) or [])
        reserved = reserved_parent_keys.get((pt, pc))
        if reserved is not None:
            pv = [v for v in pv if v != reserved]
        if not pv:
            cols[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        nullable = (not cm.notnull) and cm.pk_pos == 0
        if nullable:
            idx = rng.sample(range(n), min(n, 2)) if n >= 2 else [0]
            if n >= 2:
                vals[idx[0]] = None
                vals[idx[1]] = rng.choice(pv)
            else:
                vals[0] = None
        cols[cm.name] = vals

    for cm in tm.columns:
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if cm.name not in cols:
            continue
        key = (table, cm.name)
        if key in schema.fks:
            continue
        share = _null_share(schema, table, cm.name)
        cols[cm.name] = apply_null_rule(cols[cm.name], True, share, rng)

    return cols


def _reserve_unreferenced_parents(schema, order, generated_sizes, rng) -> dict:
    """Pick one parent key per FK relationship that no compact or generated child row will use."""
    reserved: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        key = (pt, pc)
        if key in reserved:
            continue
        pm = schema.tables[pt]
        pcol = next((c for c in pm.columns if c.name == pc), None)
        if pcol is None:
            continue
        pvals = list(schema.original_values.get((pt, pc), []))
        pvals = [v for v in pvals if v is not None]
        n_gen = int(generated_sizes.get(pt, 0))
        if pcol.pk_pos > 0 and _is_numeric_col(pcol):
            start = _next_pk_start(schema, pt, pc)
            pvals += [start + i for i in range(n_gen)]
        compact_child = set(v for v in schema.original_values.get((ct, cc), []) if v is not None)
        candidates = [v for v in pvals if v not in compact_child]
        if not candidates:
            candidates = pvals
        if candidates:
            reserved[key] = rng.choice(candidates)
    return reserved


def _apply_attendance_avg_target(schema, inst: dict, rng) -> None:
    """Per-group AVG(Attendance) straddles 200 over the FULL merged instance."""
    if 'exhibition_record' not in inst:
        return
    cols = inst['exhibition_record']
    if 'Attendance' not in cols or 'Exhibition_ID' not in cols:
        return
    att = cols['Attendance']
    ex = cols['Exhibition_ID']
    n = len(att)
    if n == 0:
        return

    compact_att = schema.original_values.get(('exhibition_record', 'Attendance'), [])
    compact_ex = schema.original_values.get(('exhibition_record', 'Exhibition_ID'), [])
    compact_groups: dict = {}
    for g, a in zip(compact_ex, compact_att):
        if g is None or a is None:
            continue
        compact_groups.setdefault(g, []).append(a)

    groups: dict = {}
    for i in range(n):
        g = ex[i]
        if g is None:
            continue
        groups.setdefault(g, []).append(i)
    if not groups:
        return

    clean = [g for g in groups if g not in compact_groups]
    gids = sorted(clean) if clean else sorted(groups)
    if not gids:
        return

    mode = rng.randrange(2)
    low_g = gids[rng.randrange(len(gids))]
    high_g = gids[rng.randrange(len(gids))]
    if len(gids) >= 2 and low_g == high_g:
        high_g = gids[(gids.index(low_g) + 1) % len(gids)]
    exact_g = gids[rng.randrange(len(gids))] if mode == 1 else None

    def _set_group_avg(g, target):
        idxs = groups[g]
        k = len(idxs)
        if k == 0:
            return
        compact_vals = compact_groups.get(g, [])
        c_sum = sum(compact_vals)
        c_n = len(compact_vals)
        total_n = k + c_n
        need = target * total_n - c_sum
        base = need // k
        rem = need - base * k
        vals = [base] * k
        for j in range(rem):
            vals[j] += 1
        if k >= 2:
            d = rng.randint(1, 50)
            if vals[0] + d >= 0 and vals[1] - d >= 0:
                vals[0] += d
                vals[1] -= d
        for j, i in enumerate(idxs):
            v = vals[j]
            if v < 0:
                v = 0
            att[i] = v

    _set_group_avg(low_g, 199)
    _set_group_avg(high_g, 201)
    if exact_g is not None:
        _set_group_avg(exact_g, 200)


def _verify_attendance_avg(schema, inst: dict) -> dict:
    """Verify per-group AVG(Attendance) straddles 200 on the merged data."""
    compact_att = schema.original_values.get(('exhibition_record', 'Attendance'), [])
    compact_ex = schema.original_values.get(('exhibition_record', 'Exhibition_ID'), [])
    merged: dict = {}
    for g, a in zip(compact_ex, compact_att):
        if g is None or a is None:
            continue
        merged.setdefault(g, []).append(a)
    cols = inst.get('exhibition_record', {})
    att = cols.get('Attendance', [])
    ex = cols.get('Exhibition_ID', [])
    for g, a in zip(ex, att):
        if g is None or a is None:
            continue
        merged.setdefault(g, []).append(a)
    avgs = {g: sum(v) / len(v) for g, v in merged.items() if v}
    return {
        'low': any(a < 200 for a in avgs.values()),
        'high': any(a > 200 for a in avgs.values()),
        'exact': any(abs(a - 200) < 1e-9 for a in avgs.values()),
        'avgs': avgs,
    }


def _verify_parent_without_children(schema, inst: dict) -> dict:
    """Verify at least one parent row has no child rows for each FK relationship."""
    out = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        parent_vals = set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        pcols = inst.get(pt, {})
        if pc in pcols:
            parent_vals |= set(v for v in pcols[pc] if v is not None)
        child_vals = set(v for v in schema.original_values.get((ct, cc), []) if v is not None)
        ccols = inst.get(ct, {})
        if cc in ccols:
            child_vals |= set(v for v in ccols[cc] if v is not None)
        out[(ct, cc)] = bool(parent_vals - child_vals)
    return out


def _fix_composite_pk_dates(schema, inst: dict, rng) -> None:
    """Make (Exhibition_ID, Date) unique by construction."""
    if 'exhibition_record' not in inst:
        return
    cols = inst['exhibition_record']
    if 'Exhibition_ID' not in cols or 'Date' not in cols:
        return
    ex = cols['Exhibition_ID']
    dates = cols['Date']
    n = len(ex)
    if n == 0:
        return

    compact_ex = schema.original_values.get(('exhibition_record', 'Exhibition_ID'), [])
    compact_date = schema.original_values.get(('exhibition_record', 'Date'), [])
    used_tuples = set()
    for g, d in zip(compact_ex, compact_date):
        if g is not None and d is not None:
            used_tuples.add((g, d))

    group_used: dict = {}
    for g, d in used_tuples:
        group_used.setdefault(g, set()).add(d)

    for i in range(n):
        g = ex[i]
        d = dates[i]
        if g is None:
            if (g, d) in used_tuples:
                new_d = _distinct_dates_for_group(1, rng, set(x[1] for x in used_tuples if x[0] is None))[0]
                dates[i] = new_d
                used_tuples.add((g, new_d))
            else:
                used_tuples.add((g, d))
            continue
        gused = group_used.setdefault(g, set())
        if d in gused:
            new_d = _distinct_dates_for_group(1, rng, gused)[0]
            dates[i] = new_d
            gused.add(new_d)
            used_tuples.add((g, new_d))
        else:
            gused.add(d)
            used_tuples.add((g, d))


def build_random_instance(schema, literal_pool: dict, size, rng):
    """Build one random instance (fuzz.py:111-196) as generated rows to append."""
    if size is None:
        size = choose_table_sizes(schema, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    parent_rows: dict = {}
    for t in schema.tables:
        parent_rows[t] = _compact_rows(schema, t)
    reserved = _reserve_unreferenced_parents(schema, order, size, rng)
    inst: dict = {}
    for t in order:
        n = int(size.get(t, 0))
        if n <= 0:
            inst[t] = {c.name: [] for c in schema.tables[t].columns}
            continue
        cols = _build_table(schema, t, n, rng, literal_pool, parent_rows, reserved)
        inst[t] = cols
        for cname, vals in cols.items():
            parent_rows[t].setdefault(cname, []).extend(vals)

    _fix_composite_pk_dates(schema, inst, rng)

    _apply_attendance_avg_target(schema, inst, rng)

    for t, tm in schema.tables.items():
        cols = inst.get(t, {})
        if not cols:
            continue
        cols, n_dropped = sample_fresh_primary_keys(tm, cols)
        if t == 'exhibition_record':
            assert n_dropped == 0, 'composite PK dedup dropped %d rows' % n_dropped
        cols = drop_unique_duplicates(tm, cols, schema.unique_tuples)
        inst[t] = cols

    if 'exhibition_record' in inst:
        cols = inst['exhibition_record']
        if 'Exhibition_ID' in cols and 'Date' in cols:
            tuples = list(zip(cols['Exhibition_ID'], cols['Date']))
            assert len(tuples) == len(set(tuples)), \
                'composite PK (Exhibition_ID, Date) not unique: %d rows, %d distinct' % (
                    len(tuples), len(set(tuples)))

    avg_check = _verify_attendance_avg(schema, inst)
    parent_check = _verify_parent_without_children(schema, inst)

    out = {t: inst.get(t, {c.name: [] for c in schema.tables[t].columns}) for t in schema.tables}
    info = {'reserved_parents': reserved, 'avg_check': avg_check, 'parent_check': parent_check}
    return out, info
