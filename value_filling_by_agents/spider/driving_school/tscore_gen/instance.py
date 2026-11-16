"""Build one random instance: parent tables first (PK dedupe), then children with valid FKs."""
import datetime
import random

from . import spec
from .values import random_values_for_a_column

_DATE_FMT = '%Y-%m-%d %H:%M:%S'


def _parse_dt(s):
    try:
        return datetime.datetime.strptime(str(s), _DATE_FMT)
    except Exception:
        return None


def _fmt_dt(d):
    return d.strftime(_DATE_FMT)


def _table_size(table, rng):
    """Exact per-table generated-row count from the specification."""
    return spec.TABLE_SIZES.get(table, 15)


def _null_share(rng):
    return rng.uniform(0.05, 0.30)


def _plant_nulls(values, rng, share):
    """Plant NULLs in a fraction of positions; at least one."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def _ensure_one_null(values, rng):
    """Guarantee at least one NULL and at least one non-NULL in a nullable column."""
    n = len(values)
    if n == 0:
        return values
    if all(v is None for v in values):
        values[rng.randrange(n)] = 'x'
    if not any(v is None for v in values):
        values[rng.randrange(n)] = None
    return values


def _plant_duplicates(values, rng, share):
    """Ensure ~share of non-NULL values repeat an earlier value."""
    n = len(values)
    nonnull = [i for i, v in enumerate(values) if v is not None]
    if len(nonnull) < 2:
        return values
    k = max(1, int(round(len(nonnull) * share)))
    targets = rng.sample(nonnull, min(k, len(nonnull)))
    for i in targets:
        j = rng.choice([x for x in nonnull if x < i] or nonnull)
        values[i] = values[j]
    return values


def _plant_group_sizes(values, rng):
    """Ensure groups of size 1, 2 and >=3 exist (never applied to PK columns)."""
    n = len(values)
    if n < 6:
        return values
    distinct = list({v for v in values if v is not None})
    if not distinct:
        return values
    a = distinct[0]
    b = distinct[min(1, len(distinct) - 1)]
    c = distinct[min(2, len(distinct) - 1)]
    order = list(range(n))
    rng.shuffle(order)
    values[order[0]] = a
    values[order[1]] = b
    values[order[2]] = b
    values[order[3]] = c
    values[order[4]] = c
    values[order[5]] = c
    return values


def _plant_different_values(values, rng):
    """Ensure >=2 rows per group with different values (vary adjacent pairs)."""
    n = len(values)
    for i in range(0, n - 1, 2):
        if values[i] is not None and values[i] == values[i + 1]:
            d = _parse_dt(values[i])
            if d:
                values[i + 1] = _fmt_dt(d + datetime.timedelta(days=1))
    return values


def _fix_date_order(rows, col_later, col_earlier):
    """Ensure later >= earlier when both non-NULL."""
    for r in rows:
        a = _parse_dt(r.get(col_earlier))
        b = _parse_dt(r.get(col_later))
        if a and b and b < a:
            r[col_later] = _fmt_dt(a + datetime.timedelta(days=1))


def _apply_formula(table, col, v):
    """Repair a single value against its semantic formula."""
    if v is None:
        return v
    if table == 'Customers' and col == 'customer_status_code':
        return v if v in ('Good Customer', 'Bad Customer') else 'Good Customer'
    if table == 'Customer_Payments' and col == 'payment_method_code':
        return v if v in ('Direct Debit', 'Credit Card') else 'Direct Debit'
    if table == 'Lessons' and col == 'lesson_status_code':
        return v if v in ('Completed', 'Cancelled') else 'Completed'
    if table == 'Vehicles' and col == 'vehicle_details':
        return v if v in ('Van', 'Truck', 'Car') else 'Van'
    if col in ('amount_outstanding', 'amount_payment', 'price'):
        try:
            f = float(v)
            return f if f >= 0 else abs(f)
        except Exception:
            return 0.0
    return v


def _max_l0_for(table, col):
    """Distinct-value cap that still permits group_sizes / duplicates targets."""
    if (table, col) in spec.GROUP_SIZE_COLUMNS:
        return 3
    if (table, col) in spec.DUPLICATE_COLUMNS:
        return 4
    return float('inf')


def _build_table(schema, table, pool, rng, parent_keys):
    """Build rows for one table; parent_keys maps parent table -> list of PK tuples."""
    tm = schema.tables[table]
    n = _table_size(table, rng)
    cols = [c.name for c in tm.columns]
    data = {c: [] for c in cols}
    fk_cols = {fk[0] for fk in tm.fks}
    for c in tm.columns:
        if c.pk_pos > 0:
            continue
        if c.name in fk_cols:
            continue
        lp = pool.get(table, {}).get(c.name, [])
        vals = random_values_for_a_column(c, lp, n, rng,
                                          max_l0=_max_l0_for(table, c.name))
        for i in range(n):
            vals[i] = _apply_formula(table, c.name, vals[i])
        data[c.name] = vals
    pk_cols = tm.pk
    if len(pk_cols) == 1:
        data[pk_cols[0]] = list(range(1, n + 1))
    else:
        for pc in pk_cols:
            data[pc] = [None] * n
    for (child, pt, _pcol) in tm.fks:
        pool_keys = parent_keys.get(pt, [])
        c = tm.col(child)
        if c is not None and c.nullable:
            share = _null_share(rng)
            k = max(1, int(round(n * share)))
            k = min(k, n)
            null_idx = set(rng.sample(range(n), k))
            vals = []
            for i in range(n):
                if i in null_idx or not pool_keys:
                    vals.append(None)
                else:
                    vals.append(rng.choice(pool_keys))
            if pool_keys and all(v is None for v in vals):
                vals[rng.randrange(n)] = rng.choice(pool_keys)
        else:
            if pool_keys:
                vals = [rng.choice(pool_keys) for _ in range(n)]
            else:
                vals = [None] * n
        data[child] = vals
    if len(pk_cols) > 1:
        for pc in pk_cols:
            if all(v is None for v in data[pc]):
                data[pc] = list(range(1, n + 1))
    if table == 'Customer_Payments' and 'datetime_payment' in pk_cols:
        _unique_datetime_per_group(data, rng)
    for c in tm.columns:
        if c.name in data and c.nullable and (table, c.name) in spec.NULL_SHARE_COLUMNS:
            _plant_nulls(data[c.name], rng, _null_share(rng))
    for c in tm.columns:
        if c.name in data and (table, c.name) in spec.DUPLICATE_COLUMNS:
            _plant_duplicates(data[c.name], rng, rng.uniform(0.20, 0.50))
    for c in tm.columns:
        if c.name in data and c.pk_pos == 0 and (table, c.name) in spec.GROUP_SIZE_COLUMNS:
            _plant_group_sizes(data[c.name], rng)
    for c in tm.columns:
        if c.name in data and (table, c.name) in spec.DIFFERENT_VALUE_COLUMNS:
            _plant_different_values(data[c.name], rng)
    rows = []
    for i in range(n):
        rows.append({c: data[c][i] for c in cols})
    if table == 'Staff':
        _fix_date_order(rows, 'date_joined_staff', 'date_of_birth')
        _fix_date_order(rows, 'date_left_staff', 'date_joined_staff')
    if table == 'Customers':
        _fix_date_order(rows, 'date_became_customer', 'date_of_birth')
    seen = set()
    out = []
    for r in rows:
        key = tuple(r.get(pc) for pc in pk_cols)
        if any(v is None for v in key):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _unique_datetime_per_group(data, rng):
    """Make datetime_payment unique within each customer_id group."""
    fk = data.get('customer_id', [])
    dts = data.get('datetime_payment', [])
    seen = {}
    for i in range(len(dts)):
        g = fk[i] if i < len(fk) else None
        d = _parse_dt(dts[i])
        if d is None:
            d = datetime.datetime(2016, 1, 1) + datetime.timedelta(seconds=rng.randrange(10 ** 7))
        used = seen.setdefault(g, set())
        while d in used:
            d = d + datetime.timedelta(seconds=rng.randint(1, 86400))
        used.add(d)
        dts[i] = _fmt_dt(d)
    data['datetime_payment'] = dts


def _pk_values(rows, pk_cols):
    return [tuple(r.get(pc) for pc in pk_cols) for r in rows]


def _ensure_unmatched(parent_rows, parent_pk, child_rows, child_fk, child_nullable):
    """Ensure at least one parent row has no child and at least one child points to a parent."""
    if not parent_rows or not child_rows:
        return
    parent_keys = [r.get(parent_pk) for r in parent_rows]
    used = {r.get(child_fk) for r in child_rows if r.get(child_fk) is not None}
    if parent_keys and all(k in used for k in parent_keys):
        victim = parent_keys[0]
        alt = parent_keys[1] if len(parent_keys) > 1 else None
        for r in child_rows:
            if r.get(child_fk) == victim:
                if child_nullable:
                    r[child_fk] = None
                elif alt is not None:
                    r[child_fk] = alt
                else:
                    break
    if parent_keys and not any(r.get(child_fk) in parent_keys for r in child_rows):
        child_rows[0][child_fk] = parent_keys[0]


def _plant_aggregate_boundary(parent_rows, parent_pk, child_rows, child_fk,
                              counted_col, rng):
    """Plant child-row counts per parent so that COUNT(*) and COUNT(counted_col) take the values 1, 2 and >=3 across
    parent groups."""
    if not parent_rows or not child_rows:
        return
    parent_keys = [r.get(parent_pk) for r in parent_rows]
    if len(parent_keys) < 3:
        return
    idx = list(range(len(parent_keys)))
    rng.shuffle(idx)
    p1, p2, p3 = parent_keys[idx[0]], parent_keys[idx[1]], parent_keys[idx[2]]
    assign = [p1] + [p2, p2] + [p3, p3, p3]
    for i, r in enumerate(child_rows):
        if i < len(assign):
            r[child_fk] = assign[i]
    if counted_col in child_rows[0]:
        for r in child_rows[1:3]:
            if r.get(child_fk) == p2:
                r[counted_col] = None
                break


def build_random_instance(schema, pool, _unused, rng):
    """Build all tables in FK order; return {table: {col: [values]}}."""
    parent_keys = {}
    tables_rows = {}
    for table in schema.order:
        tm = schema.tables[table]
        rows = _build_table(schema, table, pool, rng, parent_keys)
        tables_rows[table] = rows
        parent_keys[table] = _pk_values(rows, tm.pk)
    for (ptable, ppk, ctable, cfk, ccol) in spec.AGGREGATE_BOUNDARY:
        if ptable in tables_rows and ctable in tables_rows:
            _plant_aggregate_boundary(tables_rows[ptable], ppk,
                                      tables_rows[ctable], cfk, ccol, rng)
    for ptable, pcol in spec.UNMATCHED_JOIN.items():
        if ptable not in tables_rows:
            continue
        for ctable, ctm in schema.tables.items():
            for (child, pt, _pc) in ctm.fks:
                if pt == ptable and ctable in tables_rows:
                    c = ctm.col(child)
                    _ensure_unmatched(tables_rows[ptable], pcol,
                                      tables_rows[ctable], child,
                                      bool(c is not None and c.nullable))
    for table, rows in tables_rows.items():
        tm = schema.tables[table]
        for c in tm.columns:
            if c.nullable and (table, c.name) in spec.NULL_SHARE_COLUMNS:
                vals = [r.get(c.name) for r in rows]
                _ensure_one_null(vals, rng)
                for r, v in zip(rows, vals):
                    r[c.name] = v
    inst = {}
    for table, rows in tables_rows.items():
        tm = schema.tables[table]
        cols = [c.name for c in tm.columns]
        inst[table] = {c: [r.get(c) for r in rows] for c in cols}
    return inst
