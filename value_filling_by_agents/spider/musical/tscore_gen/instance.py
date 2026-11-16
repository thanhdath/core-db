"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def fresh_pk_start(schema, table: str, col: str) -> int:
    """Offset above max(original PK) so generated keys never collide with compact rows."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


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


def _logical_fk(schema, table: str, col: str):
    """Schema FK, else the specification's logical FK (actor.Musical_ID -> musical)."""
    key = (table, col)
    if key in schema.fks:
        return schema.fks[key]
    return spec.LOGICAL_FKS.get(key)


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        fk = _logical_fk(schema, table, cm.name)
        if fk is None:
            continue
        pt, pc = fk
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table_sizes_per_instance (exact, no jitter)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        sizes[t] = max(1, base)
    return sizes


def _plant_nulls(columns: dict, table: str, rng) -> dict:
    """NULL rule: at least one NULL and a 5-30 % share for every nullable column."""
    for cm in columns:
        share = spec.NULL_SHARE.get((table, cm))
        if share is None:
            continue
        vals = columns[cm]
        n = len(vals)
        if n == 0:
            continue
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            vals[i] = None
    return columns


def _free_positions(vals: list, used: set) -> list:
    """Positions that are non-NULL and not already claimed by another pass."""
    return [i for i, v in enumerate(vals) if v is not None and i not in used]


def _force_group_sizes(columns: dict, table: str, col: str, rng, used: set) -> set:
    """Ensure groups of size 1, 2 and >= 3 exist on the GROUP column (generated rows)."""
    vals = columns.get(col)
    if not vals:
        return used
    n = len(vals)
    if n < 6:
        return used
    pool = [v for v in vals if v is not None]
    if not pool:
        return used
    free = _free_positions(vals, used)
    if len(free) < 6:
        return used
    rng.shuffle(free)
    if len(set(pool)) >= 3:
        a, b, c = rng.sample(sorted(set(pool), key=str), 3)
    else:
        a = b = c = pool[0]
    vals[free[0]] = a
    vals[free[1]] = b
    vals[free[2]] = b
    vals[free[3]] = c
    vals[free[4]] = c
    vals[free[5]] = c
    used.update(free[:6])
    return used


def _force_duplicates(columns: dict, table: str, col: str, rng, used: set) -> set:
    """20-50 % duplicate share on DISTINCT-targeted columns."""
    vals = columns.get(col)
    if not vals:
        return used
    n = len(vals)
    k = int(round(spec.DUP_SHARE * n))
    if k < 2:
        return used
    pool = [v for v in vals if v is not None]
    if not pool:
        return used
    free = _free_positions(vals, used)
    if not free:
        return used
    k = min(k, len(free))
    idx = rng.sample(free, k)
    for i in idx:
        vals[i] = rng.choice(pool)
    used.update(idx)
    return used


def _force_order_tie(columns: dict, table: str, col: str, direction: str, rng, used: set) -> set:
    """At least two rows share the top ORDER value (rank-1 tie)."""
    vals = columns.get(col)
    if not vals or len(vals) < 2:
        return used
    nonnull = [v for v in vals if v is not None]
    if not nonnull:
        return used
    try:
        top = min(nonnull) if direction.upper() == 'ASC' else max(nonnull)
    except TypeError:
        top = nonnull[0]
    free = _free_positions(vals, used)
    if len(free) < 2:
        free = [i for i, v in enumerate(vals) if v is not None]
        if len(free) < 2:
            return used
    i, j = rng.sample(free, 2)
    vals[i] = top
    vals[j] = top
    used.update((i, j))
    return used


def _inject_unmatched_fk(columns: dict, table: str, col: str, parent_vals: set, rng, used: set) -> set:
    """Plant at least one non-NULL child FK value that matches no parent."""
    vals = columns.get(col)
    if not vals:
        return used
    free = _free_positions(vals, used)
    if not free:
        return used
    cand = None
    for _ in range(50):
        v = rng.randint(1, 10 ** 6)
        if v not in parent_vals:
            cand = v
            break
    if cand is None:
        cand = (max(parent_vals) + 1) if parent_vals else 1
    i = rng.choice(free)
    vals[i] = cand
    used.add(i)
    return used


def _check_targets(inst: dict, schema) -> dict:
    """Report unmet group-size / duplicate / order-tie targets on the generated batch."""
    unmet: dict = {}
    for (t, c) in spec.GROUP_SIZE_COLUMNS:
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        if not vals:
            continue
        sizes = {}
        for v in vals:
            sizes[v] = sizes.get(v, 0) + 1
        have = set(sizes.values())
        if not (1 in have and 2 in have and any(s >= 3 for s in have)):
            unmet['group:%s.%s' % (t, c)] = 1
    for (t, c) in spec.DUP_COLUMNS:
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        if len(vals) < 2:
            continue
        share = 1.0 - len(set(vals)) / len(vals)
        if share < 0.20:
            unmet['dup:%s.%s' % (t, c)] = 1
    for (t, c, d) in spec.ORDER_TIES:
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        if len(vals) < 2:
            continue
        try:
            top = min(vals) if d.upper() == 'ASC' else max(vals)
        except TypeError:
            continue
        if vals.count(top) < 2:
            unmet['tie:%s.%s.%s' % (t, c, d)] = 1
    return unmet


def build_random_instance(schema, literal_pool: dict, size, rng):
    """Build one random instance (fuzz.py:111-196) implementing the specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    pk_ranges: dict = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if cm.pk_pos > 0 and (t, cm.name) in spec.RANGES:
                lo, hi = spec.RANGES[(t, cm.name)]
                off = fresh_pk_start(schema, t, cm.name) - 1
                pk_ranges[(t, cm.name)] = (lo + off, hi + off)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if _logical_fk(schema, t, cm.name) is None:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key),
                                                       pk_range=pk_ranges.get((t, cm.name)))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            fk = _logical_fk(schema, t, cm.name)
            if fk is not None and fk[0] == t:
                final = cols[fk[1]]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        used: set = set()
        for (gt, gc) in spec.GROUP_SIZE_COLUMNS:
            if gt == t and gc in cols:
                used = _force_group_sizes(cols, t, gc, rng, used)
        for (dt_, dc) in spec.DUP_COLUMNS:
            if dt_ == t and dc in cols:
                used = _force_duplicates(cols, t, dc, rng, used)
        for (ot, oc, odir) in spec.ORDER_TIES:
            if ot == t and oc in cols:
                used = _force_order_tie(cols, t, oc, odir, rng, used)
        for (ut, uc) in spec.UNMATCHED_FK_NONNULL:
            if ut == t and uc in cols:
                fk = _logical_fk(schema, t, uc)
                if fk is not None:
                    pt, pc = fk
                    pv = set(inst.get(pt, {}).get(pc) or [])
                    pv |= {v for v in schema.original_values.get((pt, pc), []) if v is not None}
                    used = _inject_unmatched_fk(cols, t, uc, pv, rng, used)
        cols = _plant_nulls(cols, t, rng)
        inst[t] = cols
    inst = {t: inst[t] for t in schema.tables}
    return inst, {'unmet': _check_targets(inst, schema)}
