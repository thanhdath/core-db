"""Specification-driven appended-row construction (round 1)."""
import re

from .values import _init_sampler, make_column_sampler

SPEC_SIZES = {
    'Customer_Master_Index': 9,
    'CMI_Cross_References': 21,
    'Council_Tax': 6,
    'Business_Rates': 3,
    'Benefits_Overpayments': 4,
    'Parking_Fines': 2,
    'Rent_Arrears': 4,
    'Electoral_Register': 6,
}

SOURCE_SYSTEM_ENUM = ['Rent', 'Parking', 'Benefits', 'Business', 'Electoral', 'Tax']

CMI_DETAILS_BOUNDARY = [
    'Schmidt , Kertzmann and Lubowitz',
    'Schmidt , Kert Lubowitz',
    'Schmidt , Kertzmann and Ltz',
    'Schmidt , Kertzmann and Lubowiz',
    'Schmidt , Kzmann and Lubowitz',
    'Sidt , Kertzmann and Lubowitz',
]
SOURCE_SYSTEM_BOUNDARY = ['Electoral', 'Tax', 'electoral', 'tax']

GROUP_SIZE_COLUMNS = [
    ('CMI_Cross_References', 'cmi_cross_ref_id'),
    ('CMI_Cross_References', 'source_system_code'),
    ('CMI_Cross_References', 'master_customer_id'),
    ('Council_Tax', 'cmi_cross_ref_id'),
    ('Business_Rates', 'cmi_cross_ref_id'),
]

AGGREGATE_COLUMNS = [
    ('CMI_Cross_References', 'cmi_cross_ref_id'),
    ('CMI_Cross_References', 'source_system_code'),
    ('Council_Tax', 'cmi_cross_ref_id'),
]

UNMATCHED_PARENT = ('CMI_Cross_References', 'cmi_cross_ref_id')
UNMATCHED_CHILD = ('Parking_Fines', 'cmi_cross_ref_id')

DUP_COLUMN = ('CMI_Cross_References', 'cmi_cross_ref_id')

POSITIVE_PK_TABLES = ['CMI_Cross_References', 'Council_Tax', 'Business_Rates', 'Electoral_Register']


def _is_int_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('int', 'number', 'numeric', 'decimal', 'real', 'float', 'double'))


def _is_text_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'varchar'))


def _perturb_number(v, rng):
    """numbers +-1 / +-2."""
    try:
        i = int(v)
    except (TypeError, ValueError):
        return v
    return i + rng.choice([-2, -1, 1, 2])


def _perturb_string(v: str, rng) -> str:
    """prefix / suffix / dropped-character variants and LIKE patterns without '%'."""
    if not isinstance(v, str):
        v = str(v)
    u = rng.random()
    if u < 0.2:
        return v + rng.choice(['x', 'z', '1', 'A'])
    if u < 0.4:
        return rng.choice(['x', 'z', '1', 'A']) + v
    if u < 0.6 and len(v) > 1:
        k = rng.randrange(len(v))
        return v[:k] + v[k + 1:]
    if u < 0.8:
        return v.replace('%', '')
    return v


def _fresh_values(column, pool_vals, observed, n, rng, cap):
    """Observed + pool literals + fresh perturbed values, capped on distinct fresh values."""
    base = []
    for v in observed:
        if v is not None:
            base.append(v)
    for v in pool_vals:
        if v is not None:
            base.append(v)
    out = []
    fresh_seen = set()
    for _ in range(n):
        u = rng.random()
        if base and u < 0.5:
            out.append(rng.choice(base))
            continue
        if base and u < 0.7:
            src = rng.choice(base)
            if _is_int_type(column.type_str):
                out.append(_perturb_number(src, rng))
            else:
                out.append(_perturb_string(src, rng))
            continue
        if len(fresh_seen) >= cap and fresh_seen:
            out.append(rng.choice(sorted(fresh_seen, key=str)))
            continue
        if _is_int_type(column.type_str):
            lo, hi = 1, 1000
            if column.pk_pos > 0:
                lo, hi = 1, 10 ** 6
            v = rng.randint(lo, hi)
        else:
            v = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ')
                        for _ in range(rng.randint(3, 12)))
        fresh_seen.add(v)
        out.append(v)
    return out


def _null_share(schema, table, col):
    """NULL share following the compact database's share for that column."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.1
    n_null = sum(1 for v in vals if v is None)
    return n_null / len(vals)


def _apply_nulls(values, share, rng, nullable):
    """Plant NULLs: at least one NULL row per nullable column, share from compact db."""
    if not nullable or not values:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _dedupe_pk(rows, pk_cols):
    """Drop rows whose PK tuple repeats (first occurrence kept)."""
    if not pk_cols:
        return rows
    seen, keep = set(), []
    for r in rows:
        k = tuple(r.get(c) for c in pk_cols)
        if any(v is None for v in k):
            keep.append(r)
            continue
        if k in seen:
            continue
        seen.add(k)
        keep.append(r)
    return keep


def _dedupe_unique(rows, unique_cols):
    """Drop rows repeating any single unique column value."""
    for c in unique_cols:
        seen, keep = set(), []
        for r in rows:
            v = r.get(c)
            if v is None:
                keep.append(r)
                continue
            if v in seen:
                continue
            seen.add(v)
            keep.append(r)
        rows = keep
    return rows


def _dedupe_unique_tuples(rows, unique_tuples):
    for cols in unique_tuples:
        seen, keep = set(), []
        for r in rows:
            k = tuple(r.get(c) for c in cols)
            if any(v is None for v in k):
                keep.append(r)
                continue
            if k in seen:
                continue
            seen.add(k)
            keep.append(r)
        rows = keep
    return rows


def _table_size(schema, table, rng):
    """Specification size jittered per instance (0-230 rows, or level x 4 up to 2,500)."""
    base = SPEC_SIZES.get(table)
    if base is None:
        base = schema.original_sizes.get(table, 0)
    if rng.random() < 0.5:
        n = max(0, int(base + rng.randint(-2, 2)))
        return min(n, 230)
    lvl = 1
    for level in schema.table_order:
        if table in level:
            break
        lvl += 1
    n = min(lvl * 4, 2500)
    return max(0, n)


def _group_size_plan(n, rng):
    """Group sizes 1, 2 and >= 3 covering n rows."""
    plan = []
    remaining = n
    for size in (1, 2, 3):
        if remaining >= size:
            plan.append(size)
            remaining -= size
    while remaining > 0:
        s = rng.choice([1, 2, 3, 3, 4])
        s = min(s, remaining)
        plan.append(s)
        remaining -= s
    rng.shuffle(plan)
    return plan


def _expand_groups(plan, values):
    """Expand a group-size plan over a list of distinct values (cycled)."""
    out = []
    if not values:
        return out
    i = 0
    for s in plan:
        v = values[i % len(values)]
        i += 1
        out.extend([v] * s)
    return out


def build_appended_rows(schema, literal_pool: dict, rng) -> dict:
    """Build appended rows per table (dict table -> dict column -> list of values)."""
    order = [t for lvl in schema.table_order for t in lvl]
    parent_rows = {t: {c.name: list(schema.original_values.get((t, c.name), []))
                       for c in schema.tables[t].columns} for t in schema.tables}
    generated = {t: {c.name: [] for c in schema.tables[t].columns} for t in schema.tables}

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            p = 0.0 if rng.random() < 0.3 else 0.2
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []), p, rng, len(tm.primary_key))

    sizes = {t: _table_size(schema, t, rng) for t in order}

    group_plans = {}
    for (t, c) in GROUP_SIZE_COLUMNS:
        if t in sizes:
            group_plans[(t, c)] = _group_size_plan(sizes[t], rng)

    for t in order:
        tm = schema.tables[t]
        n = sizes.get(t, 0)
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                existing = [v for v in schema.original_values.get((t, cm.name), []) if isinstance(v, int)]
                start = (max(existing) + 1) if existing else 1
                if t in POSITIVE_PK_TABLES:
                    start = max(start, 1)
                vals = [start + i for i in range(n)]
                cols[cm.name] = vals
                continue
            if (t, cm.name) == ('CMI_Cross_References', 'source_system_code'):
                vals = _source_system_values(n, rng)
                cols[cm.name] = vals
                continue
            if (t, cm.name) == ('Customer_Master_Index', 'cmi_details'):
                vals = _cmi_details_values(n, rng)
                cols[cm.name] = vals
                continue
            s = samplers[(t, cm.name)]
            vals = [s.sample() for _ in range(n)]
            observed = set(str(v) for v in schema.original_values.get((t, cm.name), []) if v is not None)
            if observed and n > 0:
                need = max(1, int(0.3 * n))
                fresh_idx = rng.sample(range(n), min(need, n))
                for i in fresh_idx:
                    if str(vals[i]) in observed:
                        vals[i] = _perturb_string(str(vals[i]), rng) if _is_text_type(cm.type_str) \
                            else _perturb_number(vals[i], rng)
            cols[cm.name] = vals

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = parent_rows.get(pt, {}).get(pc) or []
            if not pv:
                cols[cm.name] = [None] * n
                continue
            if key == UNMATCHED_CHILD:
                cols[cm.name] = [rng.choice(pv) for _ in range(n)]
                continue
            if key == ('CMI_Cross_References', 'master_customer_id'):
                plan = group_plans.get(key) or _group_size_plan(n, rng)
                distinct = sorted(set(pv), key=str)
                vals = _expand_groups(plan, distinct)
                vals = (vals + [rng.choice(pv) for _ in range(n)])[:n]
                cols[cm.name] = vals
                continue
            if key in group_plans:
                plan = group_plans[key]
                distinct = sorted(set(pv), key=str)
                vals = _expand_groups(plan, distinct)
                vals = (vals + [rng.choice(pv) for _ in range(n)])[:n]
                cols[cm.name] = vals
                continue
            cols[cm.name] = [rng.choice(pv) for _ in range(n)]

        if (t, 'cmi_cross_ref_id') == DUP_COLUMN and n > 1:
            share = rng.uniform(0.2, 0.5)
            k = max(1, int(share * n))
            idx = rng.sample(range(n), min(k, n))
            for i in idx:
                j = rng.randrange(n)
                if j != i:
                    cols['cmi_cross_ref_id'][i] = cols['cmi_cross_ref_id'][j]

        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            share = _null_share(schema, t, cm.name)
            cols[cm.name] = _apply_nulls(cols[cm.name], share, rng, True)

        names = [c.name for c in tm.columns]
        rows = [{c: cols[c][i] for c in names} for i in range(n)]
        rows = _dedupe_pk(rows, tm.primary_key)
        uniq_cols = [c.name for c in tm.columns if c.unique]
        rows = _dedupe_unique(rows, uniq_cols)
        rows = _dedupe_unique_tuples(rows, [u for (tt, u) in schema.unique_tuples if tt == t])

        if (t, 'cmi_cross_ref_id') == UNMATCHED_PARENT:
            pass

        for c in names:
            generated[t][c] = [r[c] for r in rows]
        for c in names:
            parent_rows[t][c].extend(generated[t][c])

    _ensure_unmatched(schema, parent_rows, generated, rng)

    return generated


def _source_system_values(n, rng):
    """Enum pool + case variants + comparison-boundary literals."""
    pool = list(SOURCE_SYSTEM_ENUM) + list(SOURCE_SYSTEM_BOUNDARY)
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.6:
            out.append(rng.choice(SOURCE_SYSTEM_ENUM))
        elif u < 0.85:
            out.append(rng.choice(SOURCE_SYSTEM_BOUNDARY))
        else:
            v = rng.choice(SOURCE_SYSTEM_ENUM)
            out.append(v.lower() if rng.random() < 0.5 else v.upper())
    return out


def _cmi_details_values(n, rng):
    """Boundary literals + case variants + fresh strings."""
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.5:
            out.append(rng.choice(CMI_DETAILS_BOUNDARY))
        elif u < 0.7:
            v = rng.choice(CMI_DETAILS_BOUNDARY)
            out.append(v.lower() if rng.random() < 0.5 else v.upper())
        else:
            out.append(''.join(rng.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ')
                               for _ in range(rng.randint(3, 15))))
    return out


def _ensure_unmatched(schema, parent_rows, generated, rng):
    """Ensure at least one CMI_Cross_References parent has no Parking_Fines child."""
    if 'CMI_Cross_References' not in generated or 'Parking_Fines' not in generated:
        return
    parent_ids = set(parent_rows['CMI_Cross_References'].get('cmi_cross_ref_id', []))
    child_ids = set(generated['Parking_Fines'].get('cmi_cross_ref_id', []))
    if not parent_ids:
        return
    unmatched = parent_ids - child_ids
    if unmatched:
        return
    n_child = len(generated['Parking_Fines'].get('cmi_cross_ref_id', []))
    if n_child > 0:
        for c in generated['Parking_Fines']:
            generated['Parking_Fines'][c] = generated['Parking_Fines'][c][:-1]
