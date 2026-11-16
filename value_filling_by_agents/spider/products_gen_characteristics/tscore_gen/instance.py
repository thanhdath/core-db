"""Random instance construction (fuzz/fuzz.py:83-196)."""
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


def _is_int_type(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'integer'))


def _fresh_primary_keys(tm, cols: dict, schema, table: str, rng) -> dict:
    """Shift generated integer PKs above the compact maximum so keys never collide."""
    if not tm.primary_key or not cols:
        return cols
    for pk in tm.primary_key:
        if pk not in cols:
            continue
        orig = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
        if not orig:
            continue
        base = max(orig)
        vals = cols[pk]
        new = []
        nxt = base
        for v in vals:
            if isinstance(v, int) and v > base:
                new.append(v)
            else:
                nxt += 1
                new.append(nxt)
        cols[pk] = new
    return cols


def _finalize_parent_table(schema, inst: dict, table: str, rng) -> None:
    """Filter a parent table to its FINAL written key set (PK dedup, unique dedup, fresh PKs)."""
    tm = schema.tables[table]
    cols = inst[table]
    cols = _fresh_primary_keys(tm, cols, schema, table, rng)
    cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
    cols = drop_unique_duplicates(tm, cols)
    for cm in tm.columns:
        pt, pc = schema.fks.get((table, cm.name), (None, None))
        if pt == table and pc in cols and cm.name in cols:
            final = cols[pc]
            fs = set(final)
            cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                             for v in cols[cm.name]]
    inst[table] = cols


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw ONLY from the parent's FINAL key set (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        vals = []
        for i in range(n):
            if pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None if (not cm.notnull and cm.pk_pos == 0) else 0)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec_sizes: dict = None) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if spec_sizes:
        for t in schema.tables:
            base = int(spec_sizes.get(t, 0))
            sizes[t] = max(0, base + rng.randint(-2, 2))
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


def _apply_duplicates(values: list, share: float, rng) -> list:
    """Repeat earlier values for ~share of the rows (duplicate share on DISTINCT columns)."""
    if not values or share <= 0:
        return values
    out = list(values)
    n = len(out)
    k = int(round(n * share))
    for _ in range(k):
        i = rng.randrange(n)
        j = rng.randrange(n)
        if i != j:
            out[i] = out[j]
    return out


def _apply_nulls(values: list, share: float, force: bool, rng) -> list:
    """Plant NULLs: at least one when ``force``, share following the compact database."""
    if not values:
        return values
    out = list(values)
    n = len(out)
    k = max(1 if force else 0, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k) if k else []
    for i in idx:
        out[i] = None
    return out


def _apply_group_targets(values: list, rng) -> list:
    """Ensure at least two distinct groups with different sizes (group_sizes target)."""
    if len(values) < 3:
        return values
    out = list(values)
    a, b = out[0], out[1]
    if a == b:
        out[1] = out[2] if out[2] != a else out[1]
    return out


def _apply_tie(values: list, rng) -> list:
    """Ensure at least two rows share the ORDER-column value (ties_for_order_limit)."""
    if len(values) >= 2:
        out = list(values)
        out[1] = out[0]
        return out
    return values


def _apply_agg(values: list, rng) -> list:
    """Ensure at least one group of size >= 2 (aggregate_boundary)."""
    if len(values) >= 2:
        out = list(values)
        out[1] = out[0]
        return out
    return values


def _parent_rows_without_children(schema, inst: dict, parent_table: str, rng) -> None:
    """Restrict child FK columns that reference ``parent_table`` to a strict subset of its keys."""
    ptm = schema.tables[parent_table]
    if not ptm.primary_key:
        return
    pk = ptm.primary_key[0]
    pv = inst.get(parent_table, {}).get(pk) or []
    if len(pv) < 2:
        return
    k = max(1, int(len(pv) * 0.8))
    keep = sorted(set(rng.sample(pv, k)))
    for ct, tm in schema.tables.items():
        if ct == parent_table:
            continue
        for cm in tm.columns:
            if schema.fks.get((ct, cm.name)) == (parent_table, pk) and cm.name in inst.get(ct, {}):
                inst[ct][cm.name] = [v if v is None or v in keep else rng.choice(keep)
                                     for v in inst[ct][cm.name]]


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    spec = spec or {}
    enums = spec.get('enums', {})
    enum_strict = spec.get('enum_strict', set())
    boundaries = spec.get('boundaries', {})
    query_only = spec.get('query_only', {})
    dup = spec.get('dup', {})
    null_share = spec.get('null_share', {})
    force_null = spec.get('force_null', set())
    fk_null = spec.get('fk_null', set())
    agg = spec.get('agg', set())
    tie = spec.get('tie', set())
    group = spec.get('group', set())
    unmatched_parents = spec.get('unmatched_parents', set())
    all_null = spec.get('all_null', set())

    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                bnd = boundaries.get((t, cm.name))
                if bnd and _is_int_type(cm):
                    bnd = None
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key),
                    enum_pool=enums.get((t, cm.name)),
                    boundary=bnd,
                    enum_strict=(t, cm.name) in enum_strict,
                    query_only=query_only.get((t, cm.name)))
    if size is None:
        size = choose_table_sizes(schema, rng, spec.get('sizes'))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            k = (t, cm.name)
            if k in dup and cm.name in cols:
                cols[cm.name] = _apply_duplicates(cols[cm.name], dup[k], rng)
        for cm in tm.columns:
            k = (t, cm.name)
            if cm.name not in cols:
                continue
            if k in group:
                cols[cm.name] = _apply_group_targets(cols[cm.name], rng)
            if k in tie:
                cols[cm.name] = _apply_tie(cols[cm.name], rng)
            if k in agg:
                cols[cm.name] = _apply_agg(cols[cm.name], rng)
        for cm in tm.columns:
            k = (t, cm.name)
            if cm.name not in cols or cm.notnull or cm.pk_pos > 0:
                continue
            if k in all_null:
                cols[cm.name] = [None] * len(cols[cm.name])
                continue
            share = null_share.get(k, 0.0)
            cols[cm.name] = _apply_nulls(cols[cm.name], share, True, rng)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for cm in tm.columns:
            k = (t, cm.name)
            if cm.name in fk_cols:
                vals = fk_cols[cm.name]
                if k in fk_null and vals and not cm.notnull and cm.pk_pos == 0:
                    vals[0] = None
                cols[cm.name] = vals
        _finalize_parent_table(schema, inst, t, rng)
    for parent in sorted(unmatched_parents):
        if parent in inst:
            _parent_rows_without_children(schema, inst, parent, rng)
    return {t: inst[t] for t in schema.tables}
