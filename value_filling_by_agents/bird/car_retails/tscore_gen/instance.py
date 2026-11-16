"""Random instance construction (fuzz/fuzz.py:83-196), spec-aware."""
import datetime as dt

from .values import _init_sampler


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   spec=None) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        share = spec.fk_null_share(table, cm.name) if spec is not None else 0.0
        vals = []
        for _ in range(n):
            if pv and (share <= 0.0 or rng.random() >= share):
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Spec sizes (compact row counts) with small variation; fallback to upstream rand_lin/level sizes."""
    if spec is not None and spec.table_sizes:
        return {t: spec.size_for(t, rng) for t in schema.tables}
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


def _observed_range(schema, table: str, column: str):
    vals = [v for v in schema.original_values.get((table, column), []) if v is not None]
    nums = []
    for v in vals:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            pass
    if not nums:
        return None, None
    return min(nums), max(nums)


def _is_nonneg_column(table: str, column: str) -> bool:
    return (table, column) in {
        ('customers', 'creditLimit'), ('orderdetails', 'quantityOrdered'),
        ('orderdetails', 'priceEach'), ('orderdetails', 'orderLineNumber'),
        ('products', 'quantityInStock'), ('products', 'buyPrice'), ('products', 'MSRP'),
        ('payments', 'amount'),
    }


def _is_positive_column(table: str, column: str) -> bool:
    return (table, column) in {
        ('orderdetails', 'quantityOrdered'), ('orderdetails', 'orderLineNumber'),
    }


def _apply_null_rule(table: str, column: str, values: list, spec, rng) -> list:
    """Apply the NULL rule: at least one NULL row and non-NULL rows, share per spec."""
    if spec is None:
        return values
    share = spec.null_share(table, column)
    if share <= 0.0:
        return values
    n = len(values)
    if n == 0:
        return values
    n_null = max(1, int(round(share * n)))
    n_null = min(n_null, n - 1) if n > 1 else n
    idx = list(range(n))
    rng.shuffle(idx)
    null_set = set(idx[:n_null])
    return [None if i in null_set else v for i, v in enumerate(values)]


def _inject_boundary_and_variants(table: str, column: str, values: list, spec, rng) -> list:
    """Replace some values with boundary literals / near-variants / enum values."""
    if spec is None or not values:
        return values
    n = len(values)
    pool = []
    pool += spec.boundary_values(table, column)
    pool += spec.near_variant_values(table, column)
    enum = spec.enum_values(table, column)
    if enum:
        pool += list(enum)
    if not pool:
        return values
    k = max(1, int(0.3 * n))
    idx = list(range(n))
    rng.shuffle(idx)
    for j in idx[:k]:
        values[j] = rng.choice(pool)
    return values


def _enforce_rules(table: str, columns: dict, spec, rng) -> dict:
    """Post-fix semantic rules by construction (no SQL)."""
    if spec is None:
        return columns
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    if table == 'orders' and 'orderDate' in columns:
        od = columns['orderDate']
        if 'requiredDate' in columns:
            rd = columns['requiredDate']
            for i in range(n):
                if od[i] is not None and rd[i] is not None and rd[i] < od[i]:
                    rd[i] = od[i]
        if 'shippedDate' in columns:
            sd = columns['shippedDate']
            for i in range(n):
                if od[i] is not None and sd[i] is not None and sd[i] < od[i]:
                    sd[i] = od[i]
    if table == 'customers' and 'creditLimit' in columns:
        cl = columns['creditLimit']
        for i in range(n):
            if cl[i] is not None and cl[i] < 0:
                cl[i] = 0.0
    if table == 'orderdetails':
        if 'quantityOrdered' in columns:
            q = columns['quantityOrdered']
            for i in range(n):
                if q[i] is not None and q[i] <= 0:
                    q[i] = 1
        if 'orderLineNumber' in columns:
            ln = columns['orderLineNumber']
            for i in range(n):
                if ln[i] is not None and ln[i] <= 0:
                    ln[i] = 1
        if 'priceEach' in columns:
            p = columns['priceEach']
            for i in range(n):
                if p[i] is not None and p[i] < 0:
                    p[i] = 0.0
    if table == 'products':
        for c in ('quantityInStock', 'buyPrice', 'MSRP'):
            if c in columns:
                vals = columns[c]
                for i in range(n):
                    if vals[i] is not None and vals[i] < 0:
                        vals[i] = 0
    if table == 'payments' and 'amount' in columns:
        a = columns['amount']
        for i in range(n):
            if a[i] is not None and a[i] < 0:
                a[i] = 0.0
    if table == 'employees' and 'reportsTo' in columns and 'employeeNumber' in columns:
        r = columns['reportsTo']
        e = columns['employeeNumber']
        for i in range(n):
            if r[i] is not None and e[i] is not None and r[i] == e[i]:
                r[i] = None
    return columns


def _ensure_unmatched_parents(instance: dict, schema, spec, rng) -> None:
    """Guarantee parent rows without children for the listed joins (parent-without-child)."""
    if spec is None:
        return
    for parent, children in spec.unmatched_parents.items():
        if parent not in instance:
            continue
        pcols = instance[parent]
        if not pcols:
            continue
        n = len(next(iter(pcols.values())))
        if n == 0:
            continue
        tm = schema.tables.get(parent)
        if tm is None or not tm.primary_key:
            continue
        pk = tm.primary_key[0]
        if pk not in pcols:
            continue
        child_vals = set()
        for child in children:
            if child not in instance:
                continue
            for cm in schema.tables[child].columns:
                key = (child, cm.name)
                if key in schema.fks and schema.fks[key][0] == parent:
                    child_vals.update(v for v in instance[child].get(cm.name, []) if v is not None)
        parent_vals = [v for v in pcols[pk] if v is not None]
        if not parent_vals:
            continue
        unreferenced = [v for v in parent_vals if v not in child_vals]
        if unreferenced:
            continue
        for child in children:
            if child not in instance:
                continue
            for cm in schema.tables[child].columns:
                key = (child, cm.name)
                if key in schema.fks and schema.fks[key][0] == parent:
                    vals = instance[child].get(cm.name, [])
                    for i, v in enumerate(vals):
                        if v in parent_vals:
                            vals[i] = None
                            return


def build_random_instance(schema, literal_pool: dict, spec, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), spec-aware."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                obs_min, obs_max = _observed_range(schema, t, cm.name)
                nonneg = _is_nonneg_column(t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), observed_min=obs_min, observed_max=obs_max,
                    nonneg=nonneg, date_format=spec.date_format if spec else '%Y-%m-%d')
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt is not None and pt != t:
                final = inst.get(pt, {}).get(pc) or []
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
            elif pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_null_rule(t, cm.name, cols[cm.name], spec, rng)
                cols[cm.name] = _inject_boundary_and_variants(t, cm.name, cols[cm.name], spec, rng)
        cols = _enforce_rules(t, cols, spec, rng)
        inst[t] = cols
    _ensure_unmatched_parents(inst, schema, spec, rng)
    return {t: inst[t] for t in schema.tables}
