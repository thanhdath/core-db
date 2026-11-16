"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
from .spec import (DEFAULT_DUP_SHARE, DEFAULT_GROUP_SIZES, DEFAULT_NULL_SHARE, formula_kind, maxlen_of)
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


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """The specification's table_sizes_per_instance is a FIXED per-instance size (8/9/10)."""
    sizes = {}
    base = (spec or {}).get('table_sizes') or {}
    for lvl in schema.table_order:
        for t in lvl:
            b = base.get(t.lower())
            if b is None:
                b = int(1 + 30 * rng.random())
            sizes[t] = max(6, int(b))
    return sizes


def _constraints_for(schema, spec, t: str, c: str) -> dict:
    """Build the sampler constraint dict for one column from the specification."""
    key = (t.lower(), c.lower())
    cons: dict = {}
    f = (spec.get('formulas') or {}).get(key)
    if f:
        kind = formula_kind(f)
        if kind == 'positive':
            cons['positive'] = True
        elif kind == 'nonneg':
            cons['nonneg'] = True
        elif kind == 'nonzero':
            cons['nonzero'] = True
        elif kind == 'maxlen':
            cons['maxlen'] = maxlen_of(f)
    if key in (spec.get('comparison_boundary') or {}):
        cons['boundary'] = list(spec['comparison_boundary'][key])
    if key in (spec.get('domain') or {}):
        cons['domain'] = list(spec['domain'][key])
    if key in (spec.get('like_literals') or {}):
        cons['like_literals'] = list(spec['like_literals'][key])
        cons['like_variants'] = list(spec.get('like_variants', {}).get(key, []))
    if key in (spec.get('date_range') or {}) and key not in (spec.get('date_range_soft') or set()):
        cons['date_range'] = spec['date_range'][key]
    if key in (spec.get('ties_order') or {}):
        ties = [v for v in schema.original_values.get((t, c), []) if v is not None]
        if ties:
            cons['ties'] = [str(x) for x in ties]
    return cons


def _null_share(schema, spec, t: str, c: str) -> float:
    """NULL share for a nullable column: compact share, at least one NULL row, default 10%."""
    key = (t.lower(), c.lower())
    if key in (spec.get('null_share') or {}):
        return float(spec['null_share'][key])
    vals = schema.original_values.get((t, c), [])
    if vals:
        share = sum(1 for v in vals if v is None) / float(len(vals))
        if share > 0:
            return share
    return DEFAULT_NULL_SHARE


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs in a nullable column: at least one, share of the rows."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _ensure_one_null(values: list, rng) -> list:
    """Guarantee at least one NULL survives in a nullable column (post-filter re-plant)."""
    if not values:
        return values
    if any(v is None for v in values):
        return values
    out = list(values)
    out[rng.randrange(len(out))] = None
    return out


def _apply_duplicates(values: list, share: float, rng) -> list:
    """Allow ~share duplicate values among non-null rows (duplicates_for_distinct)."""
    nonnull = [i for i, v in enumerate(values) if v is not None]
    if len(nonnull) < 2:
        return values
    k = max(1, int(round(len(nonnull) * share)))
    k = min(k, len(nonnull) - 1)
    out = list(values)
    for i in rng.sample(nonnull, k):
        j = rng.choice([x for x in nonnull if x != i])
        out[i] = out[j]
    return out


def _dup_share_of(values: list) -> float:
    """Duplicate share among non-null values: 1 - distinct/nonnull."""
    nn = [v for v in values if v is not None]
    if not nn:
        return 0.0
    return 1.0 - len(set(map(str, nn))) / float(len(nn))


def _enforce_dup_share(values: list, lo: float, hi: float, rng) -> list:
    """Adjust a column so its duplicate share among non-null rows lands in [lo, hi]."""
    out = list(values)
    nn = [i for i, v in enumerate(out) if v is not None]
    if len(nn) < 2:
        return out
    share = _dup_share_of(out)
    if share < lo:
        need = int(round((lo + 0.05) * len(nn))) - (len(nn) - len({str(out[i]) for i in nn}))
        for i in rng.sample(nn, min(max(need, 0), len(nn) - 1)):
            j = rng.choice([x for x in nn if x != i])
            out[i] = out[j]
    elif share > hi:
        seen: dict = {}
        for i in nn:
            k = str(out[i])
            if k in seen and rng.random() < 0.5:
                v = out[i]
                out[i] = (v + 1) if isinstance(v, (int, float)) else str(v) + 'x'
            else:
                seen[k] = i
    return out


def _apply_group_sizes(values: list, targets, rng) -> list:
    """Force the multiset of values to contain groups of sizes 1, 2 and >= 3 (group_sizes)."""
    if not values or not targets:
        return values
    n = len(values)
    out = list(values)
    pool = sorted({v for v in out if v is not None}, key=lambda x: str(x))
    if not pool:
        return out
    bases = [pool[k % len(pool)] for k in range(len(targets))]
    pos = 0
    for size, base in zip(targets, bases):
        if pos + size > n:
            break
        for k in range(size):
            out[pos + k] = base
        pos += size
    return out


def _apply_agg_boundary(values: list, targets, rng) -> list:
    """Ensure COUNT(*) over the column takes values 0,1,2,3 (aggregate_boundary)."""
    if not values or not targets:
        return values
    out = list(values)
    n = len(out)
    pos = 0
    for tgt in sorted(targets):
        if tgt <= 0:
            continue
        if pos + tgt > n:
            break
        for k in range(tgt):
            out[pos + k] = (out[pos + k] if out[pos + k] is not None else 0) + k
        pos += tgt
    return out


def _apply_rows_diff_values(values: list, rng) -> list:
    """Ensure >= 2 rows per group with different values (rows_with_different_values)."""
    if len(values) < 2:
        return values
    out = list(values)
    if len(set(map(str, out))) < 2:
        out[-1] = (out[0] or 0) + 1 if isinstance(out[0], (int, float)) else str(out[0]) + 'x'
    return out


def _apply_rows_diff_values_per_group(values: list, groups: list, rng) -> list:
    """Ensure >= 2 rows with different values within each group (rows_with_different_values per partitionid)."""
    if not values or not groups:
        return values
    out = list(values)
    by_group: dict = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    for g, idxs in by_group.items():
        if len(idxs) < 2:
            continue
        vals = {str(out[i]) for i in idxs if out[i] is not None}
        if len(vals) >= 2:
            continue
        i = idxs[-1]
        v = out[i]
        if v is None:
            out[i] = 1
        elif isinstance(v, (int, float)):
            out[i] = v + 1
        else:
            out[i] = str(v) + 'x'
    return out


def _fresh_pk_start(schema, t: str, c: str) -> int:
    """First generated PK value: above the compact maximum (fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((t, c), []) if isinstance(v, (int, float))]
    return int(max(vals)) + 1 if vals else 1


def _apply_ties(values: list, rng) -> list:
    """Force at least two rows to share one value (ties_for_order_limit)."""
    if len(values) < 2:
        return values
    out = list(values)
    i, j = rng.sample(range(len(out)), 2)
    out[j] = out[i]
    return out


def _plant_boundary(values: list, boundary: list, rng) -> list:
    """Guarantee each boundary literal appears at least once (comparison_boundary)."""
    if not values or not boundary:
        return values
    out = list(values)
    n = len(out)
    for k, b in enumerate(boundary):
        if b in out:
            continue
        out[k % n] = b
    return out


def _post_verify(schema, spec, inst: dict, rng) -> dict:
    """Re-plant any per-column target that a later step (dedup) would have lost."""
    for t, cols in inst.items():
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t.lower(), cm.name.lower())
            if cm.name not in cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                continue
            vals = cols[cm.name]
            if not cm.notnull:
                vals = _ensure_one_null(vals, rng)
            if key in (spec.get('group_sizes') or {}):
                vals = _apply_group_sizes(vals, spec['group_sizes'][key], rng)
            if key in (spec.get('agg_values') or {}) and key not in _agg_as_child_count():
                vals = _apply_agg_boundary(vals, spec['agg_values'][key], rng)
            if key in (spec.get('dup_share') or {}):
                vals = _enforce_dup_share(vals, 0.20, 0.50, rng)
            if key in (spec.get('ties_order') or {}):
                vals = _apply_ties(vals, rng)
            if key in (spec.get('comparison_boundary') or {}):
                vals = _plant_boundary(vals, spec['comparison_boundary'][key], rng)
            cols[cm.name] = vals
    return inst


def _agg_as_child_count() -> set:
    from .spec import AGG_AS_CHILD_COUNT
    return AGG_AS_CHILD_COUNT


def _child_count_plan(n_parent: int, n_child: int, rng) -> list:
    """Child counts per parent hitting 0, 1, 2 and >=3 (unmatched_join_rows + aggregate_boundary)."""
    counts = [0] * n_parent
    if n_parent == 0 or n_child == 0:
        return counts
    childless = rng.randrange(n_parent)
    remaining = n_child
    others = [i for i in range(n_parent) if i != childless]
    rng.shuffle(others)
    for tgt in (1, 2, 3):
        if not others or remaining < tgt:
            break
        p = others.pop()
        counts[p] = tgt
        remaining -= tgt
    pool = [i for i in range(n_parent) if i != childless]
    if not pool:
        pool = [childless]
    k = 0
    while remaining > 0:
        counts[pool[k % len(pool)]] += 1
        remaining -= 1
        k += 1
    return counts


def _extend_parent_pool_for_domain(schema, spec, inst: dict) -> None:
    """Reconcile a closed-domain FK (follows.f2 in {-1,1}) with the FK reference."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        dom = (spec.get('domain') or {}).get((ct.lower(), cc.lower()))
        if not dom:
            continue
        pv = inst.get(pt, {}).get(pc) or []
        missing = [d for d in dom if d not in pv]
        if not missing:
            continue
        ptm = schema.tables[pt]
        pcols = inst.setdefault(pt, {})
        n_existing = len(pv)
        for d in missing:
            for cm in ptm.columns:
                arr = pcols.setdefault(cm.name, [])
                if cm.name == pc:
                    arr.append(d)
                elif cm.pk_pos > 0:
                    start = _fresh_pk_start(schema, pt, cm.name)
                    arr.append(start + n_existing)
                elif not cm.notnull:
                    arr.append(None)
                else:
                    arr.append(0)
            n_existing += 1


def _composite_pk_plan(schema, t: str, cols: dict, n: int, rng) -> list:
    """Plan composite-PK tuples that do not collide with compact tuples (before insert)."""
    tm = schema.tables[t]
    if len(tm.primary_key) < 2:
        return list(range(n))
    compact = set()
    for i in range(len(schema.original_values.get((t, tm.primary_key[0]), []))):
        try:
            compact.add(tuple(schema.original_values[(t, c)][i] for c in tm.primary_key))
        except (KeyError, IndexError):
            pass
    seen, keep = set(), []
    for i in range(n):
        k = tuple(cols[c][i] for c in tm.primary_key)
        if k in compact or k in seen:
            continue
        seen.add(k)
        keep.append(i)
    return keep


def _verify_targets(schema, spec, inst: dict) -> list:
    """Post-build verification of the numeric/pattern targets; returns a list of unmet target names."""
    unmet = []
    for (ct, cc), (pt, pc) in schema.fks.items():
        pv = inst.get(pt, {}).get(pc) or []
        cv = inst.get(ct, {}).get(cc) or []
        if pv and cv:
            if not any(v not in set(cv) for v in pv):
                unmet.append('childless:%s.%s' % (pt, pc))
    for (ct, cc), (pt, pc) in schema.fks.items():
        pv = inst.get(pt, {}).get(pc) or []
        cv = inst.get(ct, {}).get(cc) or []
        if not pv or not cv:
            continue
        counts = {v: cv.count(v) for v in pv}
        sizes = set(counts.values())
        if not ({1, 2} <= sizes and any(s >= 3 for s in sizes)):
            unmet.append('group_sizes:%s.%s' % (ct, cc))
    fv = inst.get('user_profiles', {}).get('followers') or []
    if fv and not {999, 1000, 1001} <= set(fv):
        unmet.append('followers_boundary')
    f2 = inst.get('follows', {}).get('f2') or []
    if f2:
        if not set(f2) <= {-1, 1} or not {-1, 1} <= set(f2):
            unmet.append('f2_domain')
    cd = inst.get('tweets', {}).get('createdate') or []
    if cd and len(set(map(str, cd))) >= len(cd):
        unmet.append('createdate_tie')
    for t, c in (('user_profiles', 'email'), ('tweets', 'uid')):
        vals = inst.get(t, {}).get(c) or []
        if vals:
            s = _dup_share_of(vals)
            if not (0.20 <= s <= 0.50):
                unmet.append('dup_share:%s.%s' % (t, c))
    parts = inst.get('user_profiles', {}).get('partitionid') or []
    if fv and parts:
        by = {}
        for i, g in enumerate(parts):
            by.setdefault(g, []).append(fv[i])
        for g, vs in by.items():
            if len(vs) >= 2 and len({str(v) for v in vs}) < 2:
                unmet.append('followers_diff:%s' % g)
    return unmet


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    constraints = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                cons = _constraints_for(schema, spec, t, cm.name)
                constraints[(t, cm.name)] = cons
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), constraints=cons)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                start = _fresh_pk_start(schema, t, cm.name)
                cols[cm.name] = [start + i for i in range(n)]
        inst[t] = cols
        for cm in tm.columns:
            key = (t.lower(), cm.name.lower())
            if cm.name not in cols:
                continue
            if cm.pk_pos > 0:
                continue
            if not cm.notnull:
                share = _null_share(schema, spec, t, cm.name)
                cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
            if key in (spec.get('dup_share') or {}):
                cols[cm.name] = _apply_duplicates(cols[cm.name], spec['dup_share'][key], rng)
            if key in (spec.get('group_sizes') or {}):
                cols[cm.name] = _apply_group_sizes(cols[cm.name], spec['group_sizes'][key], rng)
            if key in (spec.get('agg_values') or {}) and key not in _agg_as_child_count():
                cols[cm.name] = _apply_agg_boundary(cols[cm.name], spec['agg_values'][key], rng)
            if key in (spec.get('rows_diff_values') or {}):
                cols[cm.name] = _apply_rows_diff_values(cols[cm.name], rng)
            if key in (spec.get('comparison_boundary') or {}):
                cols[cm.name] = _plant_boundary(cols[cm.name], spec['comparison_boundary'][key], rng)
        if 'partitionid' in cols and 'followers' in cols:
            cols['followers'] = _apply_rows_diff_values_per_group(cols['followers'], cols['partitionid'], rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    _extend_parent_pool_for_domain(schema, spec, inst)
    childless_keys: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        pv = inst.get(pt, {}).get(pc) or []
        if pv:
            childless_keys[(pt, pc, ct)] = pv[rng.randrange(len(pv))]
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = list(inst.get(pt, {}).get(pc) or [])
            blocked = childless_keys.get((pt, pc, t))
            pool = [v for v in pv if v != blocked]
            if not pool:
                pool = pv
            if not pool:
                inst[t][cm.name] = [None] * n
                continue
            dom = (spec.get('domain') or {}).get((t.lower(), cm.name.lower()))
            if dom:
                dom_pool = [v for v in pool if v in dom]
                if dom_pool:
                    pool = dom_pool
            if cm is next(c for c in tm.columns if (t, c.name) in schema.fks):
                counts = _child_count_plan(len(pool), n, rng)
                vals = []
                for pv_val, cnt in zip(pool, counts):
                    vals.extend([pv_val] * cnt)
                while len(vals) < n:
                    vals.append(rng.choice(pool))
                rng.shuffle(vals)
                inst[t][cm.name] = vals[:n]
            else:
                inst[t][cm.name] = [rng.choice(pool) for _ in range(n)]
    for t in order:
        tm = schema.tables[t]
        if len(tm.primary_key) >= 2 and inst.get(t):
            n = len(next(iter(inst[t].values())))
            keep = _composite_pk_plan(schema, t, inst[t], n, rng)
            if len(keep) < n:
                inst[t] = _filter(inst[t], keep)
    inst = _post_verify(schema, spec, inst, rng)
    return {t: inst[t] for t in schema.tables}
