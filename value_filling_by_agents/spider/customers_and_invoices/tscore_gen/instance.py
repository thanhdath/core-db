"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from . import spec
from .values import _init_sampler


def _sample_primary_keys(table_meta, n, rng, existing, literal_pool):
    """Draw n distinct primary-key tuples for a table (resample on collision)."""
    pk = table_meta.primary_key
    if len(pk) != 1:
        return None
    pk = pk[0]
    cm = next(c for c in table_meta.columns if c.name == pk)
    is_int = 'int' in (cm.type_str or '').lower()
    if is_int:
        start = (max(existing) if existing else 0) + 1
        return list(range(start, start + n))
    sampler = _init_sampler(cm, literal_pool, existing, 0.0, rng, 1)
    seen = set(existing)
    out = []
    for _ in range(n):
        for _try in range(10000):
            v = sampler.sample()
            if v not in seen:
                break
        seen.add(v)
        out.append(v)
    return out


def _fill_foreign_keys(instance, reserved, schema, table, n, rng):
    """FK child columns draw from the parent's PK values (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pvals = instance.get(pt, {}).get(pc) or []
        pvals = [v for v in pvals if v is not None]
        if not pvals:
            out[cm.name] = [None] * n
            continue
        res = reserved.get(pt, set())
        pool = [v for v in pvals if v not in res]
        if not pool:
            pool = pvals
        out[cm.name] = [rng.choice(pool) for _ in range(n)]
    return out


def _reserve_parents(instance, reserved, schema, table, rng):
    """Reserve explicit PKs of the parent table that no child references."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return
    pk = tm.primary_key[0]
    vals = instance.get(table, {}).get(pk)
    if not vals:
        return
    k = max(1, len(vals) // 8)
    if len(vals) > k:
        reserved[table] = {vals[i] for i in rng.sample(range(len(vals)), k)}


def _choose_nulls(instance, schema, table, cols, rng):
    """Plant NULLs per column following the compact database's NULL share."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cname, vals in cols.items():
        key = (table, cname)
        if key in spec.NOT_NULL:
            continue
        if key in spec.ALL_NULL:
            cols[cname] = [None] * n
            continue
        share = schema.null_share.get(key, 0.0)
        if share <= 0.0:
            continue
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            vals[i] = None


def _apply_copied(inst, schema, table, rng):
    """Copied columns (Invoice_Line_Items.product_title <- Products.product_name)."""
    cols = inst.get(table, {})
    for (ct, cc), (pt, pc) in spec.COPIED.items():
        if ct != table or cc not in cols:
            continue
        fk = schema.fks.get((ct, 'product_id'))
        if fk is None:
            continue
        pvals = inst.get(pt, {}).get(pc, [])
        pids = inst.get(pt, {}).get(fk[1], [])
        lookup = {pid: name for pid, name in zip(pids, pvals)}
        child_pids = cols.get('product_id', [])
        out = []
        for i, pid in enumerate(child_pids):
            cur = cols[cc][i]
            if cur is None:
                out.append(None)
            else:
                out.append(lookup.get(pid, cur))
        cols[cc] = out


def _apply_invoice_date(inst, schema, rng):
    """Invoices.invoice_date >= Orders.date_order_placed (computed in Python)."""
    inv = inst.get('Invoices', {})
    if not inv.get('invoice_date'):
        return
    orders = inst.get('Orders', {})
    odates = dict(zip(orders.get('order_id', []), orders.get('date_order_placed', [])))
    fmt = '%Y-%m-%d %H:%M:%S'
    out = []
    for oid, d in zip(inv.get('order_id', []), inv['invoice_date']):
        if d is None:
            out.append(None)
            continue
        base = odates.get(oid)
        if base is None:
            out.append(d)
            continue
        try:
            b = dt.datetime.strptime(str(base), fmt)
            cur = dt.datetime.strptime(str(d), fmt)
        except ValueError:
            out.append(d)
            continue
        if cur < b:
            cur = b + dt.timedelta(seconds=rng.randint(0, 86400 * 30))
        out.append(cur.strftime(fmt))
    inv['invoice_date'] = out


def _apply_quantity_positive(inst, table, rng):
    """CAST(product_quantity AS INTEGER) > 0."""
    cols = inst.get(table, {})
    if 'product_quantity' not in cols:
        return
    cols['product_quantity'] = [None if v is None else str(rng.randint(1, 9)) for v in cols['product_quantity']]


def _apply_duplicate_share(inst, table, rng):
    """20-50% duplicate share for DISTINCT-targeted columns (non-key columns only)."""
    cols = inst.get(table, {})
    for (t, c) in spec.DUP_TARGETED:
        if t != table or c not in cols:
            continue
        vals = cols[c]
        n = len(vals)
        if n < 2:
            continue
        k = max(1, int(round(rng.uniform(0.20, 0.50) * n)))
        src = [v for v in vals if v is not None]
        if not src:
            continue
        for i in rng.sample(range(n), min(k, n)):
            vals[i] = rng.choice(src)


def _apply_group_mix(inst, table, rng):
    """Ensure groups of size 1, 2 and >= 3 for GROUP-targeted columns (non-key columns only)."""
    cols = inst.get(table, {})
    for (t, c) in spec.GROUP_TARGETED:
        if t != table or c not in cols:
            continue
        vals = cols[c]
        n = len(vals)
        if n < 6:
            continue
        src = [v for v in vals if v is not None]
        if not src:
            continue
        a, b, d = rng.choice(src), rng.choice(src), rng.choice(src)
        vals[0] = a
        vals[1] = b
        vals[2] = b
        vals[3] = d
        vals[4] = d
        vals[5] = d


def _finalize_instances(inst, schema, rng):
    """Re-apply group/duplicate mix after NULL planting so the final rows satisfy the size-1/2/>=3 and duplicate
    targets."""
    for t in schema.tables:
        _apply_duplicate_share(inst, t, rng)
        _apply_group_mix(inst, t, rng)


def build_random_instance(schema, literal_pool, size, rng):
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
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
        size = {t: spec.TABLE_SIZES.get(t, 20) for t in schema.tables}
    inst = {}
    reserved: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        if tm.primary_key:
            pk = tm.primary_key[0]
            existing = schema.original_values.get((t, pk), [])
            pk_vals = _sample_primary_keys(tm, n, rng, existing, literal_pool.get((t, pk), []))
            if pk_vals is not None:
                cols[pk] = pk_vals
        cols.update(_fill_foreign_keys(inst, reserved, schema, t, n, rng))
        _reserve_parents(inst, reserved, schema, t, rng)
        inst[t] = {c: cols[c] for c in [cm.name for cm in tm.columns]}
    for t in order:
        _apply_quantity_positive(inst, t, rng)
        _apply_copied(inst, schema, t, rng)
    _apply_invoice_date(inst, schema, rng)
    for t in order:
        _choose_nulls(inst, schema, t, inst.get(t, {}), rng)
    _finalize_instances(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
