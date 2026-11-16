"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec construction."""
from . import spec
from .values import spec_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_values(schema, table: str, column: str) -> list:
    return [v for v in schema.original_values.get((table, column), []) if v is not None]


def sample_fresh_primary_keys(table_meta, columns: dict, compact_keys: set = None) -> dict:
    """Drop rows whose PK tuple repeats (first occurrence kept) or collides with a compact row."""
    if not table_meta.primary_key or not columns:
        return columns
    compact_keys = compact_keys or set()
    n = len(next(iter(columns.values())))
    seen, keep = set(compact_keys), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_unique: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195), aware of compact rows."""
    compact_unique = compact_unique or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(compact_unique.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_keys(schema, table: str, column: str) -> list:
    return _compact_values(schema, table, column)


def _fresh_int_keys(schema, table: str, column: str, n: int, rng) -> list:
    """Sequential integers starting after the compact maximum (never NULL)."""
    used = set(_compact_keys(schema, table, column))
    start = (max(used) + 1) if used else 1
    out = []
    k = start
    while len(out) < n:
        if k not in used:
            out.append(k)
            used.add(k)
        k += 1
    return out


def _fresh_text_keys(schema, table: str, column: str, n: int, rng) -> list:
    used = {str(v) for v in _compact_keys(schema, table, column)}
    out = []
    k = 1
    while len(out) < n:
        v = 'g%d' % k
        if v not in used:
            out.append(v)
            used.add(v)
        k += 1
    return out


def _fresh_keys(schema, table: str, column: str, n: int, rng) -> list:
    cm = next(c for c in schema.tables[table].columns if c.name == column)
    t = (cm.type_str or '').lower()
    if 'int' in t or 'year' in t:
        return _fresh_int_keys(schema, table, column, n, rng)
    return _fresh_text_keys(schema, table, column, n, rng)


def _apply_duplicate_share(values: list, rng) -> list:
    """duplicates_for_distinct: repeat earlier values for ~DUPLICATE_SHARE of rows."""
    if len(values) < 2:
        return values
    out = list(values)
    for i in range(len(out)):
        if rng.random() < spec.DUPLICATE_SHARE:
            out[i] = out[rng.randrange(0, max(1, i))] if i else out[0]
    return out


def _apply_ties(values: list, rng) -> list:
    """ties_for_order_limit: at least two rows share the rank-1 value."""
    if len(values) < 2:
        return values
    top = max(values) if all(isinstance(v, (int, float)) for v in values) else max(values, key=str)
    out = list(values)
    out[0] = top
    out[1] = top
    return out


def _apply_different_values(values: list, rng) -> list:
    """rows_with_different_values: >= 2 rows with different values (already true for a pool)."""
    if len(values) >= 2 and len(set(values)) < 2:
        values = list(values)
        values[1] = values[0] + 1 if isinstance(values[0], int) else str(values[0]) + 'x'
    return values


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes per instance (rows appended), with a small per-instance jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 1 + int(rng.random() * 8)
        jitter = rng.choice([-1, 0, 0, 1])
        sizes[t] = max(0, base + jitter)
    return sizes


def _parent_pool(schema, instance: dict, table: str, column: str) -> list:
    """Parent key values available to children: compact rows + FINAL generated rows."""
    vals = list(_compact_keys(schema, table, column))
    vals += [v for v in instance.get(table, {}).get(column, []) if v is not None]
    return vals


def _fill_fk(schema, instance: dict, table: str, column: str, n: int, rng,
             allow_null: bool, null_rows: int) -> list:
    """FK child column draws from the parent's rows (compact or generated) or is NULL."""
    pt, pc = schema.fks[(table, column)]
    pool = _parent_pool(schema, instance, pt, pc)
    out = []
    for i in range(n):
        if allow_null and i < null_rows:
            out.append(None)
        elif pool:
            out.append(rng.choice(pool))
        else:
            out.append(None)
    return out


def _enforce_unmatched_parent(schema, inst: dict, rng) -> None:
    """unmatched_join_rows: guarantee at least one parent row without children."""
    for pt, pc in spec.UNMATCHED_PARENT.items():
        if pt not in inst:
            continue
        child = next(((ct, cc) for (ct, cc), (p_t, p_c) in schema.fks.items()
                      if p_t == pt and p_c == pc), None)
        if child is None:
            continue
        ct, cc = child
        if ct not in inst or cc not in inst[ct]:
            continue
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        if cm is None or cm.notnull:
            continue
        used = {v for v in inst[ct][cc] if v is not None}
        parents = [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
        if parents and all(v in used for v in parents):
            vals = inst[ct][cc]
            for i, v in enumerate(vals):
                if v in parents:
                    vals[i] = None
                    break


def _inject_nulls(inst: dict, null_plan: dict) -> None:
    """Plant the planned NULL rows for every nullable target column (never overwritten)."""
    for (t, c), k in null_plan.items():
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        for i in range(min(k, len(vals))):
            vals[i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one delta instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    null_plan = {}
    for (t, c) in spec.NULL_TARGETS:
        null_plan[(t, c)] = 1

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}

        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                cols[cm.name] = _fresh_keys(schema, t, cm.name, n, rng)
                continue
            vals = spec_sampler(t, cm.name, cm, literal_pool.get((t, cm.name), []),
                                schema.original_values.get((t, cm.name), []), n, rng)
            key = (t, cm.name)
            if key in spec.GROUP_PLANS:
                pass
            elif key in spec.TIE_COLUMNS:
                vals = _apply_ties(vals, rng)
            elif key in spec.DIFFERENT_VALUE_COLUMNS:
                vals = _apply_different_values(vals, rng)
            else:
                vals = _apply_duplicate_share(vals, rng)
            cols[cm.name] = vals

        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            allow_null = (t, cm.name) in null_plan
            cols[cm.name] = _fill_fk(schema, inst, t, cm.name, n, rng,
                                     allow_null, null_plan.get((t, cm.name), 0))

        compact_pk = set()
        if tm.primary_key:
            compact_pk = {tuple(v) for v in zip(*[_compact_values(schema, t, c) for c in tm.primary_key])}
        compact_unique = {cm.name: set(_compact_values(schema, t, cm.name))
                          for cm in tm.columns if cm.unique}
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, compact_pk)
        cols = drop_unique_duplicates(tm, cols, compact_unique)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]

        inst[t] = cols

    _inject_nulls(inst, null_plan)

    _enforce_unmatched_parent(schema, inst, rng)

    return {t: inst[t] for t in schema.tables}
