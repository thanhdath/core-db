"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append rows to a compact database."""
import re

from .values import _init_sampler

SPEC_TABLE_SIZES = {'event': 5, 'journalist': 11, 'news_report': 12}

_ENUMS = {
    ('journalist', 'Nationality'): ['England', 'Wales', 'Northern Ireland'],
    ('news_report', 'Work_Type'): ['Screening', 'Music', 'Host'],
}
_ENUM_VARIANTS = {
    ('journalist', 'Nationality'): ['england', 'wales'],
}
_BOUNDARY = {
    ('journalist', 'Nationality'): ['England', 'england', 'Wales', 'wales'],
    ('journalist', 'Years_working'): [2, 3, 4, 9, 10, 11],
    ('event', 'Event_Attendance'): [0, 1, 2],
}
_INT_RANGES = {
    ('event', 'Event_Attendance'): (0, 10000),
    ('journalist', 'Years_working'): (0, 40),
}
_DUP_SHARE = {('journalist', 'Nationality'): 0.30, ('journalist', 'Name'): 0.30}
_GROUP_SHAPES = {
    ('journalist', 'Nationality'): [1, 1, 2, 3],
    ('journalist', 'Name'): [1, 1, 2, 3, 4],
    ('journalist', 'Age'): [1, 1, 2, 3, 4],
    ('journalist', 'Years_working'): [1, 1, 2, 3, 4],
    ('event', 'Venue'): [1, 1, 3],
}
_TIE_COLUMNS = {('journalist', 'Age'), ('journalist', 'Nationality'),
                ('journalist', 'Years_working'), ('event', 'Event_Attendance')}
_TEXT_NAME_COLS = {('journalist', 'Name')}
_NULL_EXEMPT = {
    ('journalist', 'Nationality'), ('journalist', 'Years_working'), ('journalist', 'Name'),
    ('journalist', 'Age'), ('event', 'Venue'), ('event', 'Event_Attendance'),
}


def _is_int(col):
    return any(k in (col.type_str or '').lower() for k in ('int', 'year'))


def _is_text(col):
    t = (col.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'varchar')) or t == ''


def _table_sizes(schema) -> dict:
    """Fixed spec sizes for the schema at hand (table_sizes_per_instance)."""
    sizes = {}
    for t, tm in schema.tables.items():
        n = SPEC_TABLE_SIZES.get(t, len(schema.original_values.get((t, tm.columns[0].name), [])) or 5)
        sizes[t] = int(n)
    return sizes


def table_sizes_from_spec(schema, rng) -> dict:
    """Expose table sizes (kept for API compatibility); sizes are deterministic per schema."""
    return _table_sizes(schema)


def _parent_keys(instance, schema, pt, pc):
    """Parent key values (compact or generated) for a foreign key."""
    vals = list(instance.get('_compact', {}).get(pt, {}).get(pc, []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _fresh_int_key(instance, schema, t, col, n, rng):
    """Strictly sequential integer PKs above the compact max (int_primary_key rule)."""
    used = set(instance.get('_compact', {}).get(t, {}).get(col, []))
    used |= {v for v in instance.get(t, {}).get(col, []) if v is not None}
    start = max([v for v in used if isinstance(v, int)], default=0) + 1
    out = []
    v = start
    for _ in range(n):
        while v in used:
            v += 1
        used.add(v)
        out.append(v)
        v += 1
    return out


def _enum_sequence(t, col, n, rng):
    """Enumeration with controlled group sizes and a ~30 % duplicate share."""
    vals = _ENUMS[(t, col)]
    variants = _ENUM_VARIANTS.get((t, col), [])
    shape = _GROUP_SHAPES.get((t, col), [1 for _ in vals])
    out = []
    for s in shape:
        out += [rng.choice(vals)] * s
    shaped_len = len(out)
    while len(out) < n:
        if rng.random() < _DUP_SHARE.get((t, col), 0.30) and out:
            out.append(rng.choice(out))
        else:
            out.append(rng.choice(vals))
    out = out[:n]
    if variants and n > shaped_len:
        i = rng.randrange(shaped_len, n)
        out[i] = rng.choice(variants)
        if n - shaped_len >= 2 and rng.random() < 0.5:
            j = rng.randrange(shaped_len, n)
            if j != i:
                out[j] = rng.choice(variants)
    return out


def _boundary_int_sequence(t, col, n, rng):
    """Integers in the semantic range plus boundary values; group sizes for GROUP BY."""
    lo, hi = _INT_RANGES.get((t, col), (0, 40))
    bounds = [b for b in _BOUNDARY.get((t, col), []) if isinstance(b, int) and lo <= b <= hi] or [lo, hi]
    out = []
    shape = _GROUP_SHAPES.get((t, col))
    if shape:
        for s in shape:
            v = rng.choice(bounds)
            out += [v] * s
    if (t, col) in _TIE_COLUMNS:
        tie = rng.choice(bounds)
        if len(out) >= 2:
            out[0] = out[1] = tie
        else:
            out += [tie, tie]
    while len(out) < n:
        if rng.random() < 0.5:
            out.append(rng.choice(bounds))
        else:
            out.append(rng.randint(lo, hi))
    return out[:n]


def _text_group_sequence(t, col, n, rng, sampler):
    """Names / venues: 1, 2 and >=3 sized groups; duplicate share; near-duplicates."""
    out = []
    shape = _GROUP_SHAPES.get((t, col))
    pool = []
    if shape:
        for s in shape:
            v = sampler.sample()
            pool.append(v)
            out += [v] * s
    while len(out) < n:
        if rng.random() < _DUP_SHARE.get((t, col), 0.25) and pool:
            out.append(rng.choice(pool))
        else:
            v = sampler.sample()
            pool.append(v)
            if (t, col) in _TEXT_NAME_COLS and rng.random() < 0.10 and len(v) > 2:
                v = v[0].lower() + v[1:]
            out.append(v)
    return out[:n]


def _sample_column(instance, schema, t, col, n, rng, pool):
    """Sample n values for one non-FK column following the specification."""
    key = (t, col.name)
    if key in _ENUMS:
        return _enum_sequence(t, col.name, n, rng)
    if _is_int(col) and (_INT_RANGES.get(key) or col.pk_pos > 0):
        if col.pk_pos > 0:
            return _fresh_int_key(instance, schema, t, col.name, n, rng)
        return _boundary_int_sequence(t, col.name, n, rng)
    if _is_int(col):
        return _boundary_int_sequence(t, col.name, n, rng)
    ov = list(schema.original_values.get(key, []))
    lit = list(pool.get(key, []))
    sampler = _init_sampler(col, lit, ov, 0.2, rng, len(schema.tables[t].primary_key))
    return _text_group_sequence(t, col.name, n, rng, sampler)


def _compact_null_share(schema, t, col) -> float:
    """Per-column NULL fraction of the compact database (0.0 when no compact rows)."""
    vals = schema.original_values.get((t, col), [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / float(len(vals))


def _protected_rows(t, col, n) -> set:
    """Row indices that carry a required group-size / tie structure and must stay non-NULL."""
    prot = set()
    shape = _GROUP_SHAPES.get((t, col))
    if shape:
        k = 0
        for s in shape:
            if k >= n:
                break
            prot.update(range(k, min(k + s, n)))
            k += s
    if (t, col) in _TIE_COLUMNS:
        prot.update({0, 1})
    return prot


def _plant_nulls(schema, t, cols, rng):
    """NULL rule: nullable columns get at least one NULL and the compact NULL share."""
    tm = schema.tables[t]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0 or (t, cm.name) in schema.fks:
            continue
        if (t, cm.name) in _NULL_EXEMPT:
            continue
        share = _compact_null_share(schema, t, cm.name)
        k = max(1, int(round(share * n)))
        if k >= n:
            k = n - 1 if n > 1 else 1
        prot = _protected_rows(t, cm.name, n)
        candidates = [i for i in range(n) if i not in prot]
        if not candidates:
            candidates = list(range(n))
        if k > len(candidates):
            k = len(candidates)
        idxs = rng.sample(candidates, k)
        for i in idxs:
            cols[cm.name][i] = None
    return cols


def _dedupe_pk(schema, t, cols):
    """Primary-key tuples are deduplicated (first occurrence kept; compact rows untouched)."""
    tm = schema.tables[t]
    pk = tm.primary_key
    if not pk or not cols:
        return cols, 0
    n = len(next(iter(cols.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(cols[c][i] for c in pk)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    dropped = n - len(keep)
    return {c: [v[i] for i in keep] for c, v in cols.items()}, dropped


def _dedupe_unique(schema, t, cols):
    """Single-column UNIQUE constraints deduplicated."""
    tm = schema.tables[t]
    dropped = 0
    for cm in tm.columns:
        if cm.unique and cm.name in cols:
            seen, keep = set(), []
            for i, v in enumerate(cols[cm.name]):
                if v is None or v not in seen:
                    seen.add(v)
                    keep.append(i)
            d = len(cols[cm.name]) - len(keep)
            if d:
                dropped += d
                cols = {c: [v[i] for i in keep] for c, v in cols.items()}
    return cols, dropped


def _fill_single_fk(instance, schema, t, cm, n, rng):
    """Foreign key: draw from parent keys; nullable FK gets ~10 % NULL; NOT NULL always parent."""
    pt, pc = schema.fks[(t, cm.name)]
    pv = _parent_keys(instance, schema, pt, pc)
    out = []
    for _ in range(n):
        if not pv:
            out.append(None)
        elif (not cm.notnull) and rng.random() < 0.10:
            out.append(None)
        else:
            out.append(rng.choice(pv))
    return out


def _apply_venue_sum_tie(instance, schema, t, cols, rng):
    """event.Venue tie_at_rank [2] on SUM(event_attendance)."""
    if t != 'event' or 'Venue' not in cols or 'Event_Attendance' not in cols:
        return cols
    venues = cols['Venue']
    att = cols['Event_Attendance']
    n = len(venues)
    if n < 2:
        return cols
    comp_v = schema.original_values.get((t, 'Venue'), [])
    comp_a = schema.original_values.get((t, 'Event_Attendance'), [])
    comp_sum = {}
    for v, a in zip(comp_v, comp_a):
        if v is None or a is None:
            continue
        comp_sum[v] = comp_sum.get(v, 0) + int(a)
    distinct = []
    for v in venues:
        if v is not None and v not in distinct:
            distinct.append(v)
    if len(distinct) < 2:
        return cols
    v1, v2 = distinct[0], distinct[1]
    idx1 = [i for i, v in enumerate(venues) if v == v1]
    idx2 = [i for i, v in enumerate(venues) if v == v2]
    if not idx1 or not idx2:
        return cols
    c1, c2 = comp_sum.get(v1, 0), comp_sum.get(v2, 0)
    base = max(1, rng.randint(1, 50))
    g1 = base * len(idx1)
    g2 = g1 + (c1 - c2)
    if g2 < len(idx2):
        g2 = len(idx2)
        g1 = g2 + (c2 - c1)
        if g1 < len(idx1):
            return cols
    per1 = max(1, g1 // len(idx1))
    per2 = max(1, g2 // len(idx2))
    for k, i in enumerate(idx1):
        att[i] = per1 + (k % 2)
    for k, i in enumerate(idx2):
        att[i] = per2 + (k % 2)
    s1 = sum(att[i] for i in idx1)
    s2 = sum(att[i] for i in idx2)
    diff = (c1 + s1) - (c2 + s2)
    if diff != 0:
        if diff > 0:
            j = idx2[-1]
            att[j] = max(0, att[j] + diff)
        else:
            j = idx1[-1]
            att[j] = max(0, att[j] - diff)
    if len(idx1) >= 2:
        top = max(att[i] for i in idx1)
        att[idx1[0]] = top
        att[idx1[1]] = top
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng):
    """Build one instance: generated rows per table (compact rows appended in writer)."""
    pool = literal_pool or {}
    sizes = size if isinstance(size, dict) else _table_sizes(schema)
    order = [t for lvl in schema.table_order for t in lvl]
    for t in schema.tables:
        if t not in order:
            order.append(t)
    inst = {'_compact': dict(schema.original_values)}
    stats = {'generated': {}, 'dropped': {}}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        if n <= 0:
            inst[t] = {c.name: [] for c in tm.columns}
            stats['generated'][t] = 0
            stats['dropped'][t] = 0
            continue
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            cols[cm.name] = _sample_column(inst, schema, t, cm, n, rng, pool)
        if t == 'event':
            cols = _apply_venue_sum_tie(inst, schema, t, cols, rng)
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            cols[cm.name] = _fill_single_fk(inst, schema, t, cm, n, rng)
        cols, d_pk = _dedupe_pk(schema, t, cols)
        cols, d_uq = _dedupe_unique(schema, t, cols)
        stats['dropped'][t] = d_pk + d_uq
        cols = _plant_nulls(schema, t, cols, rng)
        inst[t] = {c.name: cols.get(c.name, [None] * len(next(iter(cols.values())) if cols else []))
                   for c in tm.columns}
        stats['generated'][t] = len(next(iter(inst[t].values()))) if inst[t] else 0
    return {k: v for k, v in inst.items() if k != '_compact'}, stats
