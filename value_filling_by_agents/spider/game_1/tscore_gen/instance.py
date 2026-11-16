"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import spec_sampler, null_share_for


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


def _parent_pool(instance, schema, table, col):
    """Parent key pool = compact values (from schema.original_values) + generated values."""
    pt, pc = schema.fks[(table, col)]
    compact = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    gen = [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return compact + gen


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pv = _parent_pool(instance, schema, table, cm.name)
        nullable = not cm.notnull and cm.pk_pos == 0
        if nullable:
            share = null_share_for(cm, schema.original_values.get(key, []))
            n_null = max(1, int(round(share * n)))
            n_null = min(n_null, n)
            vals = [None] * n_null
            vals += [rng.choice(pv) if pv else None for _ in range(n - n_null)]
            rng.shuffle(vals)
            out[cm.name] = vals
        else:
            out[cm.name] = [rng.choice(pv) if pv else None for _ in range(n)]
    return out


def _fresh_pk_values(table, tm, n, rng, schema):
    """Sequential integers starting at 1, unique per table, fresh against compact rows."""
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    compact = {v for v in schema.original_values.get((table, pk), []) if v is not None}
    start = 1
    if compact:
        try:
            start = max(int(v) for v in compact) + 1
        except (TypeError, ValueError):
            start = 1
    return [start + i for i in range(n)]


def _apply_group_structure(table, col, values, rng):
    """Ensure groups of size 1, 2 and >=3 exist on a GROUP-targeted column (group_sizes)."""
    n = len(values)
    if n < 6:
        return values
    uniq = list(dict.fromkeys(values))
    if len(uniq) < 3:
        return values
    g1, g2, g3 = rng.sample(uniq, 3)
    rest = n - 3
    if rest < 3:
        return values
    new = [g1] + [g2, g2] + [g3] * rest
    rng.shuffle(new)
    return new


def _apply_duplicate_share(table, col, values, rng):
    """Allow 20-50% duplicate values on DISTINCT-targeted columns (duplicate_distinct)."""
    n = len(values)
    if n < 4:
        return values
    uniq = list(dict.fromkeys(values))
    if len(uniq) < 2:
        return values
    target_dup = rng.uniform(0.2, 0.5)
    n_dup = int(round(target_dup * n))
    keep = values[:max(1, n - n_dup)]
    out = list(keep)
    while len(out) < n:
        out.append(rng.choice(keep))
    rng.shuffle(out)
    return out


def _apply_tie(table, col, values, rng):
    """Ensure at least two rows share the top value of the ORDER column (tie_order)."""
    n = len(values)
    if n < 2:
        return values
    try:
        top = max(values)
    except TypeError:
        return values
    idx = [i for i, v in enumerate(values) if v == top]
    if len(idx) >= 2:
        return values
    other = [i for i in range(n) if i not in idx]
    if other:
        values[other[0]] = top
    return values


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (table_sizes_per_instance), with small variation."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 10)
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as *generated rows only*."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t, cm.name)
            ov = schema.original_values.get(key, [])
            pv = literal_pool.get(key, [])
            sampler = spec_sampler(t, cm.name, rng, ov, pv)
            vals = [sampler() for _ in range(n)]
            if cm.pk_pos > 0 and len(tm.primary_key) == 1 and cm.name == tm.primary_key[0]:
                pk = _fresh_pk_values(t, tm, n, rng, schema)
                if pk is not None:
                    vals = pk
            cols[cm.name] = vals
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for (gt, gc) in spec.GROUP_COLS:
            if gt == t and gc in cols:
                cols[gc] = _apply_group_structure(t, gc, cols[gc], rng)
        for (dt_, dc) in spec.DISTINCT_COLS:
            if dt_ == t and dc in cols:
                cols[dc] = _apply_duplicate_share(t, dc, cols[dc], rng)
        for (tt, tc) in spec.TIE_COLS:
            if tt == t and tc in cols:
                cols[tc] = _apply_tie(t, tc, cols[tc], rng)
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            if cm.name not in cols:
                continue
            vals = cols[cm.name]
            if not vals:
                continue
            if not any(v is None for v in vals):
                share = null_share_for(cm, schema.original_values.get((t, cm.name), []))
                n_null = max(1, int(round(share * len(vals))))
                n_null = min(n_null, len(vals))
                for i in rng.sample(range(len(vals)), n_null):
                    vals[i] = None
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
