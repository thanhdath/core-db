"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec implementation."""
from . import spec
from .values import spec_sampler


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


def _compact_max(schema, table: str, col: str):
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _fresh_pk_values(schema, table: str, col: str, n: int, rng) -> list:
    """Sequential integers starting after the compact maximum (never NULL, unique)."""
    start = _compact_max(schema, table, col) + 1
    return list(range(start, start + n))


def _parent_value_set(schema, instance: dict, table: str, col: str, exclude: list = None) -> list:
    """Final surviving (compact + generated) parent values, NULLs removed."""
    vals = list(schema.original_values.get((table, col), [])) + list(instance.get(table, {}).get(col) or [])
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's final surviving values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_value_set(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes (spec.TABLE_SIZES), honored exactly (no jitter)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 6)
        sizes[t] = max(0, min(2500, base))
    return sizes


def _is_pk_member(table: str, col: str, schema) -> bool:
    tm = schema.tables.get(table)
    return bool(tm and col in tm.primary_key)


def _is_not_null(table: str, col: str, schema) -> bool:
    tm = schema.tables.get(table)
    if not tm:
        return False
    for cm in tm.columns:
        if cm.name == col:
            return cm.notnull or cm.pk_pos > 0
    return False


def _plant_nulls(schema, table: str, col: str, values: list, rng, always: bool = False) -> list:
    """NULL rule: every nullable column gets >=1 NULL, sparse share (spec.NULL_SHARE)."""
    if not values:
        return values
    if _is_not_null(table, col, schema) or _is_pk_member(table, col, schema):
        return values
    n = len(values)
    k = max(1, int(round(n * spec.NULL_SHARE)))
    if always:
        k = max(k, 1)
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _ensure_unmatched_parents(schema, inst: dict, rng) -> None:
    """Unmatched-join targets: ensure >=1 parent row without children."""
    for (ct, cc), (pt, pc) in spec.UNMATCHED:
        if ct not in inst or pt not in inst:
            continue
        child_vals = inst[ct].get(cc)
        parent_vals = _parent_value_set(schema, inst, pt, pc)
        if not parent_vals or not child_vals:
            continue
        referenced = {v for v in child_vals if v is not None}
        missing = [p for p in parent_vals if p not in referenced]
        if missing:
            continue
        if (ct, cc) in spec.UNMATCHED_NO_NULL or _is_not_null(ct, cc, schema):
            continue
        keep_parent = rng.choice(parent_vals)
        for i, v in enumerate(child_vals):
            if v is not None and v == keep_parent:
                others = [p for p in parent_vals if p != keep_parent]
                child_vals[i] = rng.choice(others) if others else None
                break


def _ensure_ties(schema, inst: dict, rng) -> None:
    """Ties for ORDER BY COUNT(*) DESC: at least two clubs with equal child counts."""
    t, gcol = spec.TIE_TABLE, spec.TIE_GROUP_COL
    if t not in inst or gcol not in inst[t]:
        return
    tm = schema.tables.get(t)
    if not tm:
        return
    ranks = inst[t].get('Rank')
    clubs = inst[t].get(gcol)
    if not ranks or not clubs or len(ranks) < 2:
        return
    by_rank: dict = {}
    for i, r in enumerate(ranks):
        by_rank.setdefault(r, []).append(i)
    ranks_list = sorted(by_rank)
    if len(ranks_list) < 2:
        return
    i0 = by_rank[ranks_list[0]][0]
    i1 = by_rank[ranks_list[1]][0]
    clubs[i1] = clubs[i0]


def _ensure_gender_both(inst: dict) -> None:
    """Gender aggregate boundary: both 'F' and 'M' present in player."""
    t, c = spec.GENDER_BOTH
    if t not in inst or c not in inst[t]:
        return
    vals = inst[t][c]
    if not vals:
        return
    has_f = any(isinstance(v, str) and v.upper() == 'F' for v in vals)
    has_m = any(isinstance(v, str) and v.upper() == 'M' for v in vals)
    if not has_f:
        vals[0] = 'F'
    if not has_m:
        vals[-1] = 'M'


def _trace_rank_nulls(schema, table: str, col: str, values: list, rng) -> list:
    """Ensure a nullable text/other column (e.g. player.Rank) receives NULLs."""
    return _plant_nulls(schema, table, col, values, rng, always=True)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                cols[cm.name] = _fresh_pk_values(schema, t, cm.name, n, rng)
                continue
            s = spec_sampler(t, cm, literal_pool.get(key, []), schema.original_values.get(key, []), rng, n)
            cols[cm.name] = [s.sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols

    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            if cm.name in inst.get(t, {}):
                always = (t, cm.name) in spec.NULL_TARGETS
                inst[t][cm.name] = _plant_nulls(schema, t, cm.name, inst[t][cm.name], rng, always=always)

    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            if cm.name in inst.get(t, {}):
                vals = inst[t][cm.name]
                if vals and all(v is not None for v in vals):
                    inst[t][cm.name] = _trace_rank_nulls(schema, t, cm.name, vals, rng)

    _ensure_unmatched_parents(schema, inst, rng)
    _ensure_ties(schema, inst, rng)
    _ensure_gender_both(inst)

    return {t: inst[t] for t in schema.tables}
