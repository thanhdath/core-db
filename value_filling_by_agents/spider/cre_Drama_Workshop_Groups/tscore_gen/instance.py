"""Random instance construction: rows APPENDED to a copy of the compact database."""
import datetime as dt

from .values import (CURRENCIES, PAYMENT_DESC, PAYMENT_METHODS, REGION_DESCS, SERVICE_TYPES,
                     STATUS, _init_sampler, make_column_sampler)

ENUM_TARGETS = {
    ('Ref_Payment_Methods', 'payment_method_code'): PAYMENT_METHODS,
    ('Ref_Payment_Methods', 'payment_method_description'): PAYMENT_DESC,
    ('Ref_Service_Types', 'Service_Type_Code'): ['1', '2', '3', '4'],
    ('Ref_Service_Types', 'Parent_Service_Type_Code'): ['1'],
    ('Ref_Service_Types', 'Service_Type_Description'): SERVICE_TYPES,
    ('Marketing_Regions', 'Marketing_Region_Code'): ['CA', 'CN', 'ES', 'FR', 'IN', 'MX', 'RU', 'US'],
    ('Marketing_Regions', 'Marketing_Region_Descriptrion'): REGION_DESCS,
    ('Drama_Workshop_Groups', 'Currency_Code'): CURRENCIES,
    ('Bookings', 'Status_Code'): STATUS,
}

SERVICES_PRICE_EDGES = [-39.0001, -39.0, -38.9999, 99.9999, 100.0, 100.0001]

PRODUCTS_AVG_LO = 999999.0
PRODUCTS_AVG_HI = 1000002.0


def _spec_map(spec: dict) -> dict:
    return {(e['table'], e['column']): e for e in (spec or {}).get('per_column_exceptions', [])}


def _group_sizes(values, rng, want=(1, 2, 3)):
    """Allocate at least groups of sizes 1, 2, >=3 across distinct values when n permits."""
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    distinct = sorted(set(out), key=lambda x: str(x))
    if not distinct:
        return out
    dlist = list(distinct)
    if n < 6 or len(dlist) < 3:
        if n >= 3:
            res = [dlist[0], dlist[1 % len(dlist)], dlist[2 % len(dlist)]]
            res += [rng.choice(dlist) for _ in range(n - len(res))]
            rng.shuffle(res)
            return res[:n]
        return out
    sizes = []
    remaining = n
    for i, sz in enumerate(want):
        if i < len(dlist) and remaining >= sz:
            sizes.append(sz)
            remaining -= sz
        else:
            sizes.append(0)
    if remaining > 0:
        sizes[-1] += remaining
        remaining = 0
    extra = len(dlist) - len(sizes)
    for _ in range(max(0, extra)):
        if remaining >= 1:
            sizes.append(1)
            remaining -= 1
        else:
            sizes.append(0)
    if remaining > 0:
        sizes[-1] += remaining
    res = []
    for k, sz in enumerate(sizes):
        res.extend([dlist[k % len(dlist)]] * sz)
    rng.shuffle(res)
    return res[:n]


def _duplicates_for_distinct(values, rng):
    """Inject a 20-50% duplicate share for DISTINCT columns."""
    n = len(values)
    if n == 0:
        return values
    share = rng.uniform(0.2, 0.5)
    sources = list(values)
    out = []
    while len(out) < n:
        if out and rng.random() < share:
            out.append(rng.choice(out))
        elif sources:
            out.append(sources.pop(0))
        else:
            out.append(rng.choice(out) if out else '')
    return out[:n]


def _force_aggregate_mean(vals, target_lo=PRODUCTS_AVG_LO, target_hi=PRODUCTS_AVG_HI, rng=None):
    """Force AVG of non-null numeric values into [target_lo, target_hi] while keeping a broad distribution: draw most
    values uniformly, then adjust a small number of values to hit the target sum (rather than collapsing
    everything to the midpoint)."""
    if not vals:
        return vals
    numeric = [float(v) for v in vals if v is not None]
    if not numeric:
        return vals
    n = len(numeric)
    mid = (target_lo + target_hi) / 2.0
    target_sum = mid * n
    out = [float(v) for v in vals]
    cur = sum(out)
    delta = target_sum - cur
    k = min(len(out), max(1, len(out) // 4))
    if k > 0:
        step = delta / k
        for i in range(k):
            out[i] = max(0.0, out[i] + step)
    cur = sum(out)
    out[0] = max(0.0, out[0] + (target_sum - cur))
    return [round(v, 4) for v in out]


def _repair_aggregate_mean(vals, target_lo=PRODUCTS_AVG_LO, target_hi=PRODUCTS_AVG_HI):
    """Post-pass: nudge non-null numeric values so their mean lands in [lo, hi]."""
    idx = [i for i, v in enumerate(vals) if v is not None]
    if not idx:
        return vals
    nums = [float(vals[i]) for i in idx]
    n = len(nums)
    mid = (target_lo + target_hi) / 2.0
    target_sum = mid * n
    cur = sum(nums)
    delta = target_sum - cur
    if abs(delta) < 1e-9:
        return vals
    out = list(vals)
    k = min(n, max(1, n // 4))
    step = delta / k
    for j in range(k):
        i = idx[j]
        out[i] = round(max(0.0, float(out[i]) + step), 4)
    cur = sum(float(out[i]) for i in idx)
    out[idx[0]] = round(max(0.0, float(out[idx[0]]) + (target_sum - cur)), 4)
    return out


def _apply_comparison_boundary(vals, edges):
    """Place boundary values at the front of the list so they survive."""
    if not edges:
        return vals
    out = list(vals)
    for i, e in enumerate(edges):
        if i < len(out):
            out[i] = float(e)
    return out


def _safe_rule_check(rules, t, name, vals, order_dates=None):
    """Apply simple in-Python semantic rules that never touch SQL."""
    out = list(vals)
    if t == 'Bookings' and name == 'Status_Code':
        out = [v if v in STATUS else None for v in out]
    if name == 'Quantity' or name == 'Order_Quantity':
        cleaned = []
        for v in out:
            try:
                iv = int(float(v))
            except (TypeError, ValueError):
                iv = 1
            if iv <= 0:
                iv = 1
            cleaned.append(str(iv) if isinstance(v, str) else iv)
        out = cleaned
    if t in ('Products', 'Services') and name == 'Product_Price':
        if t == 'Services':
            out = [max(-39.0001, float(v)) if v is not None else None for v in out]
        else:
            out = [max(0.0, float(v)) if v is not None else None for v in out]
        out = [round(v, 4) if v is not None else None for v in out]
    return out


def _inject_nulls(vals, rate, rng):
    """Plant NULLs at the given share, but never make the whole column NULL and never leave a nullable column with
    zero NULLs (when n >= 2)."""
    if not vals:
        return vals
    n = len(vals)
    rate = min(max(rate, 0.0), 0.95)
    m = max(1, int(round(rate * n)))
    m = min(m, n - 1) if n >= 2 else 0
    if m <= 0:
        return list(vals)
    idx = rng.sample(range(n), m)
    out = list(vals)
    for i in idx:
        out[i] = None
    return out


def _parse_dt(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v
    try:
        return dt.datetime.strptime(str(v).strip(), '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None


def _fmt_dt(d):
    return d.strftime('%Y-%m-%d %H:%M:%S')


def _draw_after(base, rng, lo_days=0, hi_days=400):
    if base is None:
        return None
    return base + dt.timedelta(days=rng.randint(lo_days, hi_days),
                               seconds=rng.randint(0, 86399))


def _child_null_rate(schema, t, name, null_targets):
    """NULL share for a nullable column, computed from the CHILD column's own compact share."""
    orig = schema.original_values.get((t, name), [])
    if orig:
        rate = sum(1 for v in orig if v is None) / len(orig)
    else:
        rate = 0.0
    if rate <= 0.0:
        rate = 0.1
    return rate


def _parent_pool(schema, inst, pt, pc):
    """Union of compact original keys and generated keys for a parent column."""
    pool = []
    seen = set()
    for v in schema.original_values.get((pt, pc), []):
        if v is not None and v not in seen:
            seen.add(v)
            pool.append(v)
    for v in inst.get(pt, {}).get(pc, []):
        if v is not None and v not in seen:
            seen.add(v)
            pool.append(v)
    return pool


def build_random_instance(schema, literal_pool: dict, size, rng, specification: dict = None) -> dict:
    spec = specification or {}
    sizes = spec.get('table_sizes_per_instance') or {}
    null_targets = set(tuple(x.split('.')) for x in spec.get('null_targets', []))
    exc_map = _spec_map(spec)
    order = [t for lvl in schema.table_order for t in lvl]

    plan = {}
    for t in order:
        n_compact = schema.original_sizes.get(t, 0)
        n = max(4, n_compact if n_compact < 40 else 12) + int(rng.random() * 15)
        if t in sizes:
            n = max(4, int(sizes[t]) + rng.randint(0, 3))
        plan[t] = n

    p = 0.0 if rng.random() < 0.3 else 0.2

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if (t, cm.name) in ENUM_TARGETS:
                continue
            taken = set(str(v) for v in schema.original_values.get((t, cm.name), []) if v is not None)
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), taken_ids=taken)

    inst: dict = {}

    for t in order:
        tm = schema.tables[t]
        n = plan[t]
        cols: dict = {}
        pk = tm.primary_key
        pk_int = len(pk) == 1 and any(c.name == pk[0] and 'int' in (c.type_str or '').lower() for c in tm.columns)
        if pk_int:
            vals = [v for v in schema.original_values.get((t, pk[0]), []) if isinstance(v, (int, float))]
            base = int(max(vals)) if vals else 0
            cols[pk[0]] = list(range(base + 1, base + 1 + n))
        else:
            for cm in tm.columns:
                if cm.name in pk:
                    s = samplers.get((t, cm.name))
                    if s is None:
                        taken = set(str(v) for v in schema.original_values.get((t, cm.name), []) if v is not None)
                        s = make_column_sampler(cm, [], 1.0, float('inf'), rng, taken_ids=taken)
                    cols[cm.name] = [s.sample() for _ in range(n)]

        composite = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks and cm.name not in pk:
                pt, pc = schema.fks[(t, cm.name)]
                composite.setdefault((pt, pc), []).append(cm.name)

        for cm in tm.columns:
            if cm.name in cols or cm.name in pk:
                continue
            if (t, cm.name) not in schema.fks:
                continue
            pt, pc = schema.fks[(t, cm.name)]
            pv = _parent_pool(schema, inst, pt, pc)
            nullable = (not cm.notnull) or ((t, cm.name) in null_targets)
            vals = []
            for _ in range(n):
                if pv:
                    vals.append(rng.choice(pv))
                else:
                    vals.append(None)
            if nullable:
                rate = _child_null_rate(schema, t, cm.name, null_targets)
                vals = _inject_nulls(vals, rate, rng)
            else:
                vals = [v for v in vals if v is not None]
                while len(vals) < n:
                    vals.append(rng.choice(pv) if pv else 0)
                vals = vals[:n]
            cols[cm.name] = vals

        for (pt, pc), child_cols in composite.items():
            if not child_cols:
                continue
            pv = _parent_pool(schema, inst, pt, pc)
            if pv:
                chosen = [rng.choice(pv) for _ in range(n)]
                for cc in child_cols:
                    cols[cc] = list(chosen)
            else:
                for cc in child_cols:
                    cols.setdefault(cc, [None] * n)

        for cm in tm.columns:
            if cm.name in cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            if (t, cm.name) in ENUM_TARGETS:
                targets = ENUM_TARGETS[(t, cm.name)]
                exc = exc_map.get((t, cm.name), {})
                if exc.get('pattern') == 'group_sizes':
                    raw = [targets[i % len(targets)] for i in range(n)]
                    vals = _group_sizes(raw, rng)
                else:
                    vals = [targets[i % len(targets)] for i in range(n)]
                    rng.shuffle(vals)
                if not cm.notnull or (t, cm.name) in null_targets:
                    rate = _child_null_rate(schema, t, cm.name, null_targets)
                    vals = _inject_nulls(vals, rate, rng)
                cols[cm.name] = vals
                continue

            s = samplers[(t, cm.name)]
            exc = exc_map.get((t, cm.name), {})
            pattern = exc.get('pattern')
            vals = []
            if pattern == 'duplicates_for_distinct' and hasattr(s, 'with_duplicates'):
                vals = s.with_duplicates(n)
            elif pattern == 'group_sizes':
                raw = [s.sample() for _ in range(n)]
                vals = _group_sizes(raw, rng)
            elif pattern == 'ties_for_order_limit':
                raw = [s.sample() for _ in range(max(2, n))]
                if raw and n >= 4:
                    first = raw[0]
                    raw[0] = raw[1] = raw[2] = first
                vals = raw[:n]
            elif pattern == 'aggregate_boundary':
                raw = [s.sample() for _ in range(n)]
                vals = _force_aggregate_mean(raw, rng=rng)
            elif pattern == 'comparison_boundary':
                edges = exc.get('targets') or []
                raw = [s.sample() for _ in range(n)]
                try:
                    edges_f = [float(x) for x in edges]
                    vals = _apply_comparison_boundary(raw, edges_f)
                except (TypeError, ValueError):
                    vals = raw
            else:
                vals = [s.sample() for _ in range(n)]

            vals = _safe_rule_check(None, t, cm.name, vals)

            date_cols = ('Order_Date', 'Planned_Delivery_Date', 'Actual_Delivery_Date')
            if t in ('Bookings', 'Customer_Orders') and cm.name in date_cols:
                if len(vals) < n:
                    vals = vals + [None] * (n - len(vals))
                elif len(vals) > n:
                    vals = vals[:n]
                od = cols.get('Order_Date')
                if od is None:
                    od = list(schema.original_values.get((t, 'Order_Date'), []))
                fixed = []
                for i, v in enumerate(vals):
                    base = _parse_dt(od[i]) if i < len(od) else None
                    if cm.name == 'Order_Date':
                        fixed.append(v)
                    elif base is not None:
                        fixed.append(_fmt_dt(_draw_after(base, rng)))
                    else:
                        fixed.append(v)
                vals = fixed

            nullable = (not cm.notnull) or ((t, cm.name) in null_targets)
            if nullable:
                rate = _child_null_rate(schema, t, cm.name, null_targets)
                vals = _inject_nulls(vals, rate, rng)
            if len(vals) < n:
                vals += [None] * (n - len(vals))
            elif len(vals) > n:
                vals = vals[:n]
            cols[cm.name] = vals

        for cm in tm.columns:
            if cm.name not in cols:
                if cm.notnull:
                    s = samplers.get((t, cm.name))
                    if s is not None:
                        cols[cm.name] = [s.sample() for _ in range(n)]
                else:
                    cols[cm.name] = [None] * n

        lens = [len(v) for v in cols.values()]
        m = min(lens) if lens else 0
        inst[t] = {c: v[:m] for c, v in cols.items() if v is not None}

    if 'Services' in inst and 'Product_Price' in inst['Services']:
        pp = inst['Services']['Product_Price']
        for i, e in enumerate(SERVICES_PRICE_EDGES):
            if i < len(pp):
                pp[i] = round(float(e), 4)

    if 'Products' in inst and 'Product_Price' in inst['Products']:
        inst['Products']['Product_Price'] = _repair_aggregate_mean(inst['Products']['Product_Price'])

    return {t: inst[t] for t in schema.tables if t in inst}


def v_list_nonnull(lst):
    return [v for v in lst if v is not None]
