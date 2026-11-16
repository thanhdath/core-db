"""Random instance construction (fuzz/fuzz.py:83-196), adapted to append to a compact database."""
from . import specification as spec
from .values import _init_sampler, compact_null_share


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, reserved: set) -> dict:
    """Drop rows whose PK tuple repeats (incl. compact rows), first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(reserved), []
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


def choose_table_sizes(schema, rng) -> dict:
    """Specification per-instance generated-row sizes (compact rows are additional)."""
    return {t: spec.table_size(t, 10) for lvl in schema.table_order for t in lvl}


def fresh_pk_sequence(schema, table: str, n: int, rng) -> list:
    """Sequential fresh primary-key integers beyond the compact maximum (int_primary_key rule)."""
    tm = schema.tables[table]
    pk_cols = [c.name for c in tm.columns if c.pk_pos > 0]
    if len(pk_cols) != 1:
        return None
    col = pk_cols[0]
    existing = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 1
    return list(range(start, start + n))


def _apply_relations(table: str, tm, cols: dict, rng) -> dict:
    """Specification formula constraints on sampled, non-NULL rows, repaired by construction."""
    n = len(next(iter(cols.values()))) if cols else 0
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        if table == 'mountain':
            h, p = row.get('Height'), row.get('Prominence')
            if h is not None and h <= 0:
                cols['Height'][i] = rng.uniform(1.0, 6000.0)
                h = cols['Height'][i]
            if p is not None:
                if p <= 0 or (h is not None and p > h):
                    hi = h if h is not None else 6000.0
                    cols['Prominence'][i] = rng.uniform(1.0, max(1.0, hi))
        elif table == 'climber':
            p = row.get('Points')
            if p is not None and p < 0:
                cols['Points'][i] = rng.uniform(0.0, 100.0)
    return cols


def _plant_unmatched_parents(parent_cols: dict, pk_col: str, child_fk_vals: list, rng,
                             null_budget: int = 0) -> None:
    """Ensure at least one parent key has no child (parent_rows_without_children)."""
    if not parent_cols or pk_col not in parent_cols:
        return
    used = {v for v in child_fk_vals if v is not None}
    keys = [k for k in parent_cols[pk_col] if k is not None]
    if keys and all(k in used for k in keys):
        current_nulls = sum(1 for v in child_fk_vals if v is None)
        if current_nulls >= null_budget:
            return
        for i, v in enumerate(child_fk_vals):
            if v is not None:
                child_fk_vals[i] = None
                break


def _plant_null_fk(fk_vals: list, share: float, rng) -> list:
    """Plant NULLs at the target share (at least one) for a nullable FK."""
    n = len(fk_vals)
    if n == 0:
        return fk_vals
    k = max(1, int(round(share * n)))
    k = min(k, n)
    for i in rng.sample(range(n), k):
        fk_vals[i] = None
    return fk_vals


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one generated-row set per table to be APPENDED to a copy of the compact database."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = choose_table_sizes(schema, rng) if size is None else dict(size)
    inst: dict = {}
    final_parent_keys: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = max(1, int(sizes.get(t, 10) * rng.uniform(0.9, 1.1)))
        cols = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            elif cm.pk_pos > 0:
                continue
            ov = schema.original_values.get(key, [])
            ns = compact_null_share(ov) if (not cm.notnull and cm.pk_pos == 0) else 0.0
            sampler = _init_sampler(cm, literal_pool.get(key, []), ov, 0.2, rng, len(tm.primary_key),
                                    null_share=ns)
            cols[cm.name] = sampler.sample_many(n)
        cols = _apply_relations(t, tm, cols, rng)
        pk = fresh_pk_sequence(schema, t, n, rng)
        if pk is not None:
            pkc = next(c.name for c in tm.columns if c.pk_pos > 0)
            cols[pkc] = pk
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = list(final_parent_keys.get(pt, []))
            if not parent_vals:
                parent_vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
            if not parent_vals:
                cols[cm.name] = [None] * n
                continue
            vals = [rng.choice(parent_vals) for _ in range(n)]
            if not cm.notnull:
                ov = schema.original_values.get(key, [])
                ns = spec.null_share(t, cm.name, compact_null_share(ov))
                vals = _plant_null_fk(vals, ns, rng)
            cols[cm.name] = vals
        reserved = {tuple([v]) for v in schema.original_values.get((t, tm.primary_key[0]), [])
                    if tm.primary_key} if tm.primary_key else set()
        cols = sample_fresh_primary_keys(tm, cols, reserved)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
        if tm.primary_key:
            pkc = tm.primary_key[0]
            final_parent_keys[t] = [v for v in schema.original_values.get((t, pkc), []) if v is not None] + \
                                   [v for v in cols.get(pkc, []) if v is not None]
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            if t in inst and cm.name in inst[t]:
                ov = schema.original_values.get(key, [])
                ns = spec.null_share(t, cm.name, compact_null_share(ov))
                budget = max(1, int(round(ns * len(inst[t][cm.name]))))
                _plant_unmatched_parents(inst.get(pt, {}), pc, inst[t][cm.name], rng, null_budget=budget)
    for t, cols in inst.items():
        n = len(next(iter(cols.values()))) if cols else 0
        for i in range(n):
            row = {c: cols[c][i] for c in cols}
            if not spec.formula_ok(t, row):
                raise AssertionError('formula violated in %s row %d: %r' % (t, i, row))
    return {t: inst[t] for t in schema.tables}
