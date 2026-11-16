"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec as _spec
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
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


def _spec_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (fixed, no jitter)."""
    base = _spec.DEFAULT_SPEC.get('table_sizes_per_instance', {})
    out = {}
    for t in schema.tables:
        out[t] = max(0, int(base.get(t, 0)))
    return out


def _fresh_pk_values(schema, table: str, n: int, rng) -> list:
    """Sequential integers above the compact maximum (int PK rule: 1..N, no NULL, no duplicates)."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) != 1:
        return [None] * n
    col = pk[0]
    existing = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    start = (max(existing) if existing else 0) + 1
    return list(range(start, start + n))


def _is_int_col(schema, table: str, column: str) -> bool:
    cm = next((c for c in schema.tables[table].columns if c.name == column), None)
    if cm is None:
        return False
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'year', 'bit'))


def _int_range(schema, table: str, column: str):
    """Integer range for a column: specification range, else observed min/max +- 2."""
    r = _spec.range_for(table, column)
    if r:
        return r
    ov = [v for v in schema.original_values.get((table, column), [])
          if isinstance(v, int) and not isinstance(v, bool)]
    if ov:
        return (min(ov) - 2, max(ov) + 2)
    return (0, 100)


def _text_pool(schema, table: str, column: str) -> list:
    """Observed non-NULL text values (near-duplicate pool)."""
    return [v for v in schema.original_values.get((table, column), []) if isinstance(v, str)]


def _planted_values(schema, table: str, column: str, n: int, rng) -> list:
    """Values that must appear by construction for this column (enum, boundary, near-duplicates)."""
    out = []
    enum = _spec.enum_for(table, column)
    if enum:
        out += list(enum)
    out += list(_spec.boundaries_for(table, column))
    if (table, column) in _spec.DUPLICATE_SHARE_COLUMNS:
        ov = [v for v in schema.original_values.get((table, column), []) if v is not None]
        if ov:
            k = max(1, int(round(0.3 * n)))
            out += [rng.choice(ov) for _ in range(k)]
    if (table, column) in _spec.TIE_COLUMNS:
        ov = [v for v in schema.original_values.get((table, column), []) if v is not None]
        if ov:
            out += [rng.choice(ov), rng.choice(ov)]
    if (table, column) in _spec.DIFFERENT_VALUES_COLUMNS:
        out += [0, 1, 2, 3]
    return out


def _fresh_int(schema, table: str, column: str, rng) -> int:
    lo, hi = _int_range(schema, table, column)
    return rng.randint(int(lo), int(hi))


def _fresh_text(schema, table: str, column: str, rng) -> str:
    pool = _text_pool(schema, table, column)
    if pool:
        v = rng.choice(pool)
        u = rng.random()
        if u < 0.25:
            return v + 'x'
        if u < 0.5:
            return 'x' + v
        if u < 0.75 and len(v) > 1:
            return v[:-1]
        return v
    return 'v%d' % rng.randrange(10 ** 6)


def _fresh_value(schema, table: str, column: str, rng):
    if _is_int_col(schema, table, column):
        return _fresh_int(schema, table, column, rng)
    return _fresh_text(schema, table, column, rng)


def _enforce_group_sizes(schema, table: str, column: str, values: list, rng, reserved: int = 0) -> list:
    """Make the value multiset contain groups of size 1, 2 and >= 3 (specification group_sizes)."""
    if len(values) - reserved < 6:
        return values
    vals = list(values)
    tail = vals[reserved:]
    uniq = []
    for v in tail:
        if v not in uniq:
            uniq.append(v)
    while len(uniq) < 3:
        uniq.append(_fresh_value(schema, table, column, rng))
    a, b, c = uniq[0], uniq[1], uniq[2]
    tail[0] = a
    tail[1] = b
    tail[2] = b
    tail[3] = c
    tail[4] = c
    tail[5] = c
    vals[reserved:] = tail
    return vals


def _enforce_duplicate_share(schema, table: str, column: str, values: list, rng, reserved: int = 0) -> list:
    """Keep the distinct/rows ratio in [0.5, 0.8] (duplicate share 20-50 %)."""
    n = len(values)
    if n - reserved < 4:
        return values
    vals = list(values)
    tail = vals[reserved:]
    distinct = len(set(tail))
    target_max = max(1, int(round(0.8 * len(tail))))
    target_min = max(1, int(round(0.5 * len(tail))))
    if distinct > target_max:
        seen = []
        for i, v in enumerate(tail):
            if v not in seen:
                seen.append(v)
            if len(seen) > target_max:
                tail[i] = rng.choice(seen[:target_max])
    elif distinct < target_min:
        seen = set()
        for i, v in enumerate(tail):
            if v in seen and rng.random() < 0.5:
                tail[i] = _fresh_value(schema, table, column, rng)
            seen.add(tail[i])
    vals[reserved:] = tail
    return vals


def _enforce_tie(values: list, rng, direction: str, reserved: int = 0) -> tuple:
    """Force a tie at rank 1 for ORDER BY direction (max for DESC, min for ASC)."""
    if len(values) - reserved < 2:
        return values, ()
    vals = list(values)
    tail = vals[reserved:]
    nums = [v for v in tail if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if nums:
        extreme = max(nums) if direction.upper() == 'DESC' else min(nums)
    else:
        strs = [v for v in tail if isinstance(v, str)]
        if strs:
            extreme = max(strs) if direction.upper() == 'DESC' else min(strs)
        else:
            extreme = tail[0]
    tail[0] = extreme
    tail[1] = extreme
    vals[reserved:] = tail
    return vals, (reserved, reserved + 1)


def _enforce_different_values(schema, table: str, column: str, values: list, rng, reserved: int = 0) -> list:
    """>= 2 rows per group with different values: make consecutive values differ (type-aware)."""
    vals = list(values)
    for i in range(max(1, reserved), len(vals)):
        if vals[i] == vals[i - 1]:
            if _is_int_col(schema, table, column):
                lo, hi = _int_range(schema, table, column)
                nv = vals[i] + 1
                vals[i] = nv if nv <= hi else max(lo, vals[i] - 1)
            else:
                vals[i] = str(vals[i]) + 'x'
    return vals


def _enforce_aggregate_boundary(schema, table: str, column: str, values: list, rng, reserved: int = 0) -> list:
    """Make the value multiset contain groups of size 1, 2, 3, 4 (aggregate boundary COUNT(*))."""
    targets = _spec.AGGREGATE_BOUNDARY_COLUMNS.get((table, column))
    if not targets:
        return values
    need = sum(targets)
    if len(values) - reserved < need:
        return values
    vals = list(values)
    tail = vals[reserved:]
    uniq = []
    for v in tail:
        if v not in uniq:
            uniq.append(v)
    while len(uniq) < len(targets):
        uniq.append(_fresh_value(schema, table, column, rng))
    pos = 0
    for k, size in zip(uniq, targets):
        for _ in range(size):
            if pos < len(tail):
                tail[pos] = k
                pos += 1
    vals[reserved:] = tail
    return vals


def _apply_null_rule(schema, table: str, column: str, values: list, rng, reserved: int = 0,
                     protected: tuple = ()) -> list:
    """NULL rule: nullable columns get NULL rows with the compact share, at least one NULL."""
    cm = next(c for c in schema.tables[table].columns if c.name == column)
    if cm.notnull or cm.pk_pos > 0 or (table, column) in _spec.NO_NULL_COLUMNS:
        return values
    share = schema.null_shares.get((table, column), 0.0)
    n = len(values)
    idx = [i for i in range(reserved, n) if i not in protected]
    if not idx:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, len(idx))
    vals = list(values)
    rng.shuffle(idx)
    for i in idx[:k]:
        vals[i] = None
    return vals


def _apply_column_patterns(schema, table: str, column: str, values: list, rng, reserved: int = 0) -> tuple:
    """Apply the specification's per-column patterns by construction (planted slots preserved)."""
    cm = next(c for c in schema.tables[table].columns if c.name == column)
    if cm.pk_pos > 0:
        return values, ()
    vals = list(values)
    tied = ()
    if (table, column) in _spec.GROUP_SIZE_COLUMNS:
        vals = _enforce_group_sizes(schema, table, column, vals, rng, reserved)
    if (table, column) in _spec.AGGREGATE_BOUNDARY_COLUMNS:
        vals = _enforce_aggregate_boundary(schema, table, column, vals, rng, reserved)
    if (table, column) in _spec.DUPLICATE_SHARE_COLUMNS:
        vals = _enforce_duplicate_share(schema, table, column, vals, rng, reserved)
    if (table, column) in _spec.TIE_COLUMNS:
        vals, tied = _enforce_tie(vals, rng, _spec.TIE_COLUMNS[(table, column)], reserved)
    if (table, column) in _spec.DIFFERENT_VALUES_COLUMNS:
        vals = _enforce_different_values(schema, table, column, vals, rng, reserved)
    return vals, tied


def _replant(values: list, planted: list, protected: tuple = ()) -> list:
    """Re-plant reserved values at the head of the column (they are never overwritten)."""
    if not planted:
        return values
    vals = list(values)
    for i, v in enumerate(planted):
        if i < len(vals) and i not in protected:
            vals[i] = v
    return vals


def _plant_null_fk_rows(schema, table: str, columns: dict, rng) -> dict:
    """Ensure at least one child row has a NULL FK (nullable FK only)."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or key not in _spec.NULL_FK_COLUMNS:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        vals = columns.get(cm.name)
        if vals:
            vals[0] = None
    return columns


def _fk_values(schema, table: str, column: str, n: int, parent_vals: list, rng,
               leave_unmatched: bool) -> list:
    """FK column: draw from parent values; optionally leave one parent value unused."""
    if not parent_vals:
        return [None] * n
    pool = list(parent_vals)
    if leave_unmatched and len(pool) > 1:
        pool = pool[:-1]
    return [rng.choice(pool) for _ in range(n)]


def _restrict_distinct_fk(schema, table: str, column: str, values: list, parent_vals: list, rng) -> list:
    """Restrict a child FK column to at most MAX_DISTINCT_FK distinct parent values (>= 1)."""
    cap = _spec.MAX_DISTINCT_FK.get((table, column))
    if cap is None or not parent_vals:
        return values
    pool = [v for v in parent_vals if v is not None]
    if not pool:
        return values
    usable = pool[:-1] if len(pool) > cap else pool
    if not usable:
        usable = pool
    k = min(cap, len(usable))
    chosen = rng.sample(usable, k) if k < len(usable) else list(usable)
    if not chosen:
        return values
    return [rng.choice(chosen) if v is not None else None for v in values]


def _repair_composite_pk(schema, table: str, columns: dict, parent_pools: dict, rng) -> dict:
    """Enforce composite PRIMARY KEY uniqueness by construction."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) < 2 or not columns:
        return columns
    n = len(next(iter(columns.values())))
    fk_cols = [c for c in pk if (table, c) in schema.fks]
    if not fk_cols:
        return columns
    cols = {c: list(v) for c, v in columns.items()}
    seen = set()
    for i in range(n):
        key = tuple(cols[c][i] for c in pk)
        if key not in seen:
            seen.add(key)
            continue
        repaired = False
        for c in fk_cols:
            pt, pc = schema.fks[(table, c)]
            pool = [v for v in parent_pools.get((pt, pc), []) if v is not None]
            if not pool:
                continue
            order = list(pool)
            rng.shuffle(order)
            for cand in order:
                trial = list(key)
                trial[pk.index(c)] = cand
                trial = tuple(trial)
                if trial not in seen:
                    cols[c][i] = cand
                    seen.add(trial)
                    repaired = True
                    break
            if repaired:
                break
        if not repaired:
            seen.add(key)
    return cols


def _enforce_different_values_per_group(schema, table: str, column: str, columns: dict, rng,
                                        group_col: str = 'School_ID') -> tuple:
    """For each group (by group_col) with >= 2 rows, assign >= 2 distinct values."""
    vals = list(columns.get(column, []))
    groups = columns.get(group_col, [])
    if not vals or not groups:
        return vals, ()
    lo, hi = _int_range(schema, table, column)
    by = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    protected = set()
    for g, idxs in by.items():
        if len(idxs) < 2:
            continue
        first = vals[idxs[0]]
        second = vals[idxs[1]]
        if first == second:
            nv = first + 1 if isinstance(first, int) else None
            if nv is None or nv > hi:
                nv = max(lo, (first - 1) if isinstance(first, int) else 0)
            vals[idxs[1]] = nv
        protected.add(idxs[0])
        protected.add(idxs[1])
    return vals, tuple(sorted(protected))


def _repair_unmatched_parents(schema, inst: dict, rng) -> None:
    """After FK assignment, force at least one parent row without children."""
    for (pt, pc) in _spec.UNMATCHED_PARENT_COLUMNS:
        if pt not in inst or pc not in inst[pt]:
            continue
        parent_vals = [v for v in inst[pt][pc] if v is not None]
        if not parent_vals:
            continue
        child_cols = [(ct, cc) for (ct, cc), (p_t, p_c) in schema.fks.items()
                      if p_t == pt and p_c == pc and ct in inst]
        if not child_cols:
            continue
        used = set()
        for ct, cc in child_cols:
            used |= {v for v in inst[ct].get(cc, []) if v is not None}
        missing = [v for v in parent_vals if v not in used]
        if missing:
            continue
        for ct, cc in child_cols:
            vals = inst[ct].get(cc)
            if not vals:
                continue
            counts = {}
            for v in vals:
                if v is not None:
                    counts[v] = counts.get(v, 0) + 1
            for v, c in counts.items():
                if c >= 2:
                    others = [p for p in parent_vals if p != v]
                    if others:
                        for i, x in enumerate(vals):
                            if x == v:
                                vals[i] = rng.choice(others)
                                break
                        break
            break


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = _spec_sizes(schema, rng)
    inst: dict = {}
    parent_pools: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        protected_by_col: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                cols[cm.name] = _fresh_pk_values(schema, t, n, rng)
                continue
            planted = _planted_values(schema, t, cm.name, n, rng)
            s = _init_sampler(cm, literal_pool.get(key, []), schema.original_values.get(key, []), p, rng,
                              len(tm.primary_key), planted=planted)
            vals = [s.sample() for _ in range(n)]
            reserved = min(len(planted), n)
            vals, tied = _apply_column_patterns(schema, t, cm.name, vals, rng, reserved)
            vals = _apply_null_rule(schema, t, cm.name, vals, rng, reserved, tied)
            vals = _replant(vals, planted, tied)
            cols[cm.name] = vals
            protected_by_col[cm.name] = tied
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = list(schema.original_values.get((pt, pc), []))
            parent_vals += list(inst.get(pt, {}).get(pc, []))
            parent_vals = [v for v in parent_vals if v is not None]
            parent_pools[(pt, pc)] = parent_vals
            leave_unmatched = (pt, pc) in _spec.UNMATCHED_PARENT_COLUMNS
            vals = _fk_values(schema, t, cm.name, n, parent_vals, rng, leave_unmatched)
            vals = _restrict_distinct_fk(schema, t, cm.name, vals, parent_vals, rng)
            cols[cm.name] = vals
        inst[t] = cols
        cols = _repair_composite_pk(schema, t, cols, parent_pools, rng)
        for (tt, cc) in _spec.DIFFERENT_VALUES_COLUMNS:
            if tt != t:
                continue
            vals, prot = _enforce_different_values_per_group(schema, t, cc, cols, rng)
            cols[cc] = vals
            protected_by_col[cc] = tuple(sorted(set(protected_by_col.get(cc, ())) | set(prot)))
        for (tt, cc) in _spec.DIFFERENT_VALUES_COLUMNS:
            if tt != t:
                continue
            cols[cc] = _apply_null_rule(schema, t, cc, cols[cc], rng, 0, protected_by_col.get(cc, ()))
        inst[t] = cols
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _plant_null_fk_rows(schema, t, cols, rng)
        inst[t] = cols
    _repair_unmatched_parents(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}


def verify_instance(schema, inst: dict) -> dict:
    """Per-instance post-condition counts (reported in the execution feedback)."""
    out: dict = {}
    for (pt, pc) in _spec.UNMATCHED_PARENT_COLUMNS:
        pv = [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
        child_cols = [(ct, cc) for (ct, cc), (p_t, p_c) in schema.fks.items()
                      if p_t == pt and p_c == pc and ct in inst]
        used = set()
        for ct, cc in child_cols:
            used |= {v for v in inst[ct].get(cc, []) if v is not None}
        out.setdefault('unmatched_parents', {})['%s.%s' % (pt, pc)] = \
            sum(1 for v in pv if v not in used)
    for (t, c), direction in _spec.TIE_COLUMNS.items():
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        if not vals:
            out.setdefault('ties', {})['%s.%s' % (t, c)] = 0
            continue
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums:
            ext = max(nums) if direction.upper() == 'DESC' else min(nums)
        else:
            strs = [v for v in vals if isinstance(v, str)]
            ext = (max(strs) if direction.upper() == 'DESC' else min(strs)) if strs else None
        out.setdefault('ties', {})['%s.%s' % (t, c)] = sum(1 for v in vals if v == ext)
    for (t, c) in _spec.GROUP_SIZE_COLUMNS:
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        counts = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        sizes = set(counts.values())
        out.setdefault('group_sizes', {})['%s.%s' % (t, c)] = {
            'has_1': 1 in sizes, 'has_2': 2 in sizes, 'has_ge3': any(s >= 3 for s in sizes)}
    for (t, c), targets in _spec.AGGREGATE_BOUNDARY_COLUMNS.items():
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        counts = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        sizes = set(counts.values())
        out.setdefault('aggregate_boundary', {})['%s.%s' % (t, c)] = {
            'has_%d' % k: k in sizes for k in targets}
    for (t, c), allowed in _spec.DISTINCT_COUNT_COLUMNS.items():
        vals = [v for v in inst.get(t, {}).get(c, []) if v is not None]
        n = len(set(vals))
        out.setdefault('distinct_count', {})['%s.%s' % (t, c)] = n
        out.setdefault('distinct_count_ok', {})['%s.%s' % (t, c)] = n in allowed
    for (t, c) in _spec.DIFFERENT_VALUES_COLUMNS:
        vals = inst.get(t, {}).get(c, [])
        groups = inst.get(t, {}).get('School_ID', [])
        by = {}
        for g, v in zip(groups, vals):
            if v is not None:
                by.setdefault(g, set()).add(v)
        out.setdefault('different_values', {})['%s.%s' % (t, c)] = \
            sum(1 for s in by.values() if len(s) >= 2)
    for t, tm in schema.tables.items():
        if len(tm.primary_key) >= 2 and t in inst:
            cols = inst[t]
            n = len(next(iter(cols.values()))) if cols else 0
            keys = [tuple(cols[c][i] for c in tm.primary_key) for i in range(n)]
            out.setdefault('composite_pk_unique', {})[t] = (len(set(keys)) == len(keys))
    for t, cols in inst.items():
        for c, vals in cols.items():
            if vals:
                out.setdefault('null_share', {}).setdefault('%s.%s' % (t, c), 0)
                out['null_share']['%s.%s' % (t, c)] += sum(1 for v in vals if v is None)
    return out
