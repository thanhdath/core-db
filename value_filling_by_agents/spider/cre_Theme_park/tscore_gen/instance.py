"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for pk in table_meta.primary_key:
        if pk not in columns:
            return columns
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


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Final parent values: compact values + generated rows that survived the finalize."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _next_pk_start(schema, table: str, col: str) -> int:
    """First fresh integer above the compact maximum for a single-column integer PK."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _child_fk_columns(schema, pt: str, pc: str) -> list:
    """All (child_table, child_col) whose FK points at (pt, pc)."""
    return [(ct, cm.name) for ct, tm in schema.tables.items() for cm in tm.columns
            if schema.fks.get((ct, cm.name)) == (pt, pc)]


def _reserved_parent_values(schema, inst: dict, pt: str, pc: str) -> set:
    """Choose >=1 *generated* parent value to leave unmatched (never chosen by any child)."""
    gen_vals = list(dict.fromkeys(v for v in inst.get(pt, {}).get(pc, []) if v is not None))
    if not gen_vals:
        return set()
    return set(gen_vals[:2])


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   reserved: dict) -> dict:
    """FK child columns draw from the parent's final values, excluding reserved (unmatched) parents."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = [v for v in _parent_values(instance, schema, pt, pc) if v not in reserved.get((pt, pc), set())]
        if not pv:
            pv = _parent_values(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _apply_group_sizes(values: list, rng) -> list:
    """Force group sizes 1, 2 and >= 3 on a grouping column (by construction, non-key only)."""
    n = len(values)
    if n < 6:
        return values
    pool = list(dict.fromkeys(values))
    if len(pool) < 3:
        return values
    g1, g2, g3 = rng.sample(pool, 3)
    out = list(values)
    slots = list(range(n))
    rng.shuffle(slots)
    for k, v in enumerate([g1] + [g2, g2] + [g3, g3, g3]):
        out[slots[k]] = v
    return out


def _apply_aggregate_boundary(values: list, rng) -> list:
    """Ensure COUNT in {1,2} is reachable: at least one value with count 1 and one with count 2."""
    n = len(values)
    if n < 3:
        return values
    pool = list(dict.fromkeys(values))
    if len(pool) < 2:
        return values
    a, b = rng.sample(pool, 2)
    out = list(values)
    slots = list(range(n))
    rng.shuffle(slots)
    out[slots[0]] = a
    out[slots[1]] = b
    out[slots[2]] = b
    return out


def _apply_group_and_agg(values: list, rng) -> list:
    """Combined pass for a column carrying BOTH group_sizes and aggregate_boundary."""
    n = len(values)
    if n < 6:
        return _apply_aggregate_boundary(_apply_group_sizes(values, rng), rng)
    pool = list(dict.fromkeys(values))
    if len(pool) < 3:
        return _apply_aggregate_boundary(values, rng)
    g1, g2, g3 = rng.sample(pool, 3)
    out = list(values)
    slots = list(range(n))
    rng.shuffle(slots)
    for k, v in enumerate([g1, g2, g2, g3, g3, g3]):
        out[slots[k]] = v
    return out


def _shape_fk_distribution(instance: dict, schema, ct: str, cc: str, rng,
                           want_group_sizes: bool, want_agg: bool) -> None:
    """Reshape ONE specific child FK column (ct, cc) to realize child-count group sizes (1, 2, >=3) and aggregate
    boundaries (COUNT in {1,2}) BY CONSTRUCTION, without rewriting PK/FK parent values."""
    key = (ct, cc)
    if key not in schema.fks:
        return
    pt, pc = schema.fks[key]
    parents = [v for v in _parent_values(instance, schema, pt, pc) if v is not None]
    parents = list(dict.fromkeys(parents))
    if len(parents) < 3:
        return
    col = instance.get(ct, {}).get(cc)
    if not col:
        return
    n = len(col)
    if n < 3:
        return
    g1, g2, g3 = rng.sample(parents, 3)
    desired = [g1] + [g2, g2] + [g3, g3, g3]
    idx = list(range(n))
    rng.shuffle(idx)
    filled = 0
    for val in desired:
        if filled >= n:
            break
        col[idx[filled]] = val
        filled += 1
    if want_agg and filled < n:
        col[idx[filled]] = g1
        filled += 1


def choose_table_sizes(schema, rng) -> dict:
    """Specification table_sizes_per_instance (generated rows per instance)."""
    return {t: int(spec.TABLE_SIZES.get(t, 0)) for t in schema.tables}


def _finalize(schema, inst: dict, t: str, rng) -> None:
    """Finalize a table's PK: PK dedupe, unique dedupe, fresh integer PKs."""
    tm = schema.tables[t]
    cols = {cm.name: inst[t][cm.name] for cm in tm.columns if cm.name in inst[t]}
    cols = sample_fresh_primary_keys(tm, cols)
    cols = drop_unique_duplicates(tm, cols)
    inst[t] = cols
    if t in spec.PK_IS_FK:
        return
    if len(tm.primary_key) == 1:
        pk = tm.primary_key[0]
        cm = next((c for c in tm.columns if c.name == pk), None)
        if cm is not None and 'int' in (cm.type_str or '').lower() and pk in cols:
            start = _next_pk_start(schema, t, pk)
            cols[pk] = [start + i for i in range(len(cols[pk]))]


def _plant_nulls(schema, inst: dict, t: str, c: str, rng) -> None:
    """Plant NULLs: at least one, plus a 5-30% share for the listed columns."""
    if t not in inst or c not in inst[t] or not inst[t][c]:
        return
    col = inst[t][c]
    n = len(col)
    share = rng.uniform(0.05, 0.30)
    if (t, c) in spec.NULL_SHARE:
        k = max(1, int(round(n * share)))
        for i in rng.sample(range(n), min(k, n)):
            col[i] = None
    elif all(v is not None for v in col):
        col[rng.randrange(n)] = None


def _fill_pk_is_fk(instance: dict, schema, t: str, rng) -> None:
    """Fill a PK-is-FK child table's PK by copying parent PK values not already present in the compact child table
    (so no PK collision with copied compact rows)."""
    pk = spec.PK_IS_FK[t]
    key = (t, pk)
    if key not in schema.fks:
        return
    pt, pc = schema.fks[key]
    compact = set(v for v in schema.original_values.get((t, pk), []) if v is not None)
    parents = [v for v in _parent_values(instance, schema, pt, pc)
               if v is not None and v not in compact]
    parents = list(dict.fromkeys(parents))
    n = len(instance.get(t, {}).get(pk, []))
    if n == 0:
        return
    if not parents:
        instance[t][pk] = [None] * n
        return
    rng.shuffle(parents)
    chosen = parents[:n]
    while len(chosen) < n:
        chosen.append(rng.choice(parents))
    instance[t][pk] = chosen


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) appended to the compact database."""
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
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    reserved: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        _finalize(schema, inst, t, rng)
        for (pt, pc) in spec.UNMATCHED_PARENT:
            if pt == t and pc in inst[t]:
                reserved[(pt, pc)] = _reserved_parent_values(schema, inst, pt, pc)
        cols = inst[t]
        fk = fill_foreign_keys_consistently(inst, schema, t, n, rng, reserved)
        for k, v in fk.items():
            cols[k] = v
        inst[t] = cols
        if t in spec.PK_IS_FK:
            _fill_pk_is_fk(inst, schema, t, rng)

    fkg = set(spec.FK_GROUP_SIZES)
    fka = set(spec.FK_AGG_BOUNDARY)
    for (ct, cc) in sorted(fkg | fka):
        if ct in inst and cc in inst[ct] and inst[ct][cc]:
            _shape_fk_distribution(inst, schema, ct, cc, rng,
                                   want_group_sizes=(ct, cc) in fkg, want_agg=(ct, cc) in fka)

    gs = set(spec.GROUP_SIZES)
    ab = set(spec.AGG_BOUNDARY)
    for t, c in spec.GROUP_SIZES:
        if t in inst and c in inst[t] and inst[t][c]:
            if (t, c) in ab:
                inst[t][c] = _apply_group_and_agg(inst[t][c], rng)
            else:
                inst[t][c] = _apply_group_sizes(inst[t][c], rng)
    for t, c in spec.AGG_BOUNDARY:
        if (t, c) in gs:
            continue
        if t in inst and c in inst[t] and inst[t][c]:
            inst[t][c] = _apply_aggregate_boundary(inst[t][c], rng)

    for t, c in spec.NULL_TARGETS:
        _plant_nulls(schema, inst, t, c, rng)
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            if t in inst and cm.name in inst[t] and inst[t][cm.name]:
                if all(v is not None for v in inst[t][cm.name]):
                    inst[t][cm.name][rng.randrange(len(inst[t][cm.name]))] = None

    return {t: inst[t] for t in schema.tables}
