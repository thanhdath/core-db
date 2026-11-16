"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt

from .values import make_spec_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_max(schema, table: str, col: str):
    """Maximum non-NULL value of a compact column (for fresh PK allocation)."""
    vals = [v for v in schema.original_values.get((table, col), []) if v is not None]
    try:
        return max(vals) if vals else 0
    except TypeError:
        return 0


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set, schema=None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated values of a parent column."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        nullable = (not cm.notnull) and cm.pk_pos == 0 and key in spec['null_targets']
        col = []
        for _ in range(n):
            if not pv:
                col.append(None)
            elif nullable and rng.random() < 0.05:
                col.append(None)
            else:
                col.append(rng.choice(pv))
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Per-instance table sizes: exact spec sizes with a small variation, else the upstream rule."""
    sizes = {}
    spec_sizes = spec.get('sizes') or {}
    if spec_sizes:
        for t in schema.tables:
            base = int(spec_sizes.get(t, 0))
            if base <= 0:
                sizes[t] = 0
            else:
                lo = max(1, base - 2)
                hi = min(2500, base + 2)
                sizes[t] = rng.randint(lo, hi)
        return sizes
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


def _apply_null_rule(table: str, columns: dict, schema, spec: dict, rng) -> dict:
    """Ensure every nullable column (per spec null_targets) has at least one NULL and a NULL share near the compact
    share."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.name not in columns:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        if (table, cm.name) not in spec['null_targets']:
            columns[cm.name] = [v for v in columns[cm.name] if v is not None] + \
                               [None] * sum(1 for v in columns[cm.name] if v is None)
            ov = [v for v in schema.original_values.get((table, cm.name), []) if v is not None]
            if ov:
                columns[cm.name] = [v if v is not None else rng.choice(ov) for v in columns[cm.name]]
            continue
        col = columns[cm.name]
        ov = schema.original_values.get((table, cm.name), [])
        share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.05
        share = max(share, 1.0 / n)
        target = max(1, int(round(share * n)))
        have = sum(1 for v in col if v is None)
        if have < target:
            idxs = [i for i, v in enumerate(col) if v is not None]
            rng.shuffle(idxs)
            for i in idxs[:target - have]:
                col[i] = None
    return columns


def _enforce_rules(table: str, columns: dict, instance: dict, schema, spec: dict, rng) -> dict:
    """Enforce semantic rules in Python (non-NULL operands only)."""
    if table == 'order_history' and 'status_date' in columns and 'order_id' in columns:
        order_dates = {}
        for oid, od in zip(instance.get('cust_order', {}).get('order_id', []),
                           instance.get('cust_order', {}).get('order_date', [])):
            if od is not None:
                order_dates[oid] = od
        for oid, od in zip(schema.original_values.get(('cust_order', 'order_id'), []),
                           schema.original_values.get(('cust_order', 'order_date'), [])):
            if od is not None:
                order_dates.setdefault(oid, od)
        col = columns['status_date']
        for i, (oid, sd) in enumerate(zip(columns['order_id'], col)):
            if oid is None or sd is None:
                continue
            od = order_dates.get(oid)
            if od is None:
                continue
            try:
                od_dt = dt.datetime.strptime(str(od), '%Y-%m-%d %H:%M:%S')
                sd_dt = dt.datetime.strptime(str(sd), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            if sd_dt < od_dt:
                delta = dt.timedelta(seconds=rng.randint(60, 3 * 86400))
                col[i] = (od_dt + delta).strftime('%Y-%m-%d %H:%M:%S')
    return columns


def _fresh_pk_columns(table: str, tm, n: int, schema, rng) -> dict:
    """Allocate fresh PK values above the compact maximum (single-column integer PKs)."""
    out = {}
    if len(tm.primary_key) != 1:
        return out
    pk = tm.primary_key[0]
    cm = next((c for c in tm.columns if c.name == pk), None)
    if cm is None:
        return out
    t = (cm.type_str or '').lower()
    if 'int' not in t:
        return out
    base = _compact_max(schema, table, pk)
    start = int(base) + 1 if base else 1
    out[pk] = list(range(start, start + n))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict) -> dict:
    """Build one random instance (fuzz.py:111-196) honouring the specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = make_spec_sampler(
                    t, cm.name, cm, spec, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), rng)
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
        fresh = _fresh_pk_columns(t, tm, n, schema, rng)
        for c, vals in fresh.items():
            cols[c] = vals
        existing = set()
        if tm.primary_key:
            pk_vals = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            if pk_vals and all(pk_vals):
                existing = set(zip(*pk_vals))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing, schema)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(t, cols, schema, spec, rng)
        cols = _enforce_rules(t, cols, inst, schema, spec, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
