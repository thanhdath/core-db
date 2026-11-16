"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from .spec import key as _k
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _equalize(columns: dict, n: int) -> dict:
    """Force every column list to length n (pad with None / truncate)."""
    out = {}
    for c, vals in columns.items():
        vals = list(vals)
        if len(vals) < n:
            vals = vals + [None] * (n - len(vals))
        out[c] = vals[:n]
    return out


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


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes when present, else the upstream rand_lin / level x4 choice."""
    fixed = (spec or {}).get('table_sizes') or {}
    if fixed:
        return {t: int(fixed.get(t, 0)) for t in schema.tables}
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


def _compact_rows(schema, table: str) -> dict:
    """Compact rows of a table as {column: [values]} (read-only snapshot from the schema)."""
    tm = schema.tables[table]
    return {c.name: list(schema.original_values.get((table, c.name), [])) for c in tm.columns}


def _plant_group_sizes(values: list, rng, sizes=(1, 2, 3)) -> list:
    """Reorder/duplicate a value list so that groups of the requested sizes exist."""
    if not values:
        return values
    out = []
    pool = list(values)
    rng.shuffle(pool)
    i = 0
    for s in sizes:
        for _ in range(s):
            out.append(pool[i % len(pool)])
        i += 1
    while len(out) < len(values):
        out.append(pool[i % len(pool)])
        i += 1
    return out[:len(values)]


def _plant_duplicates(values: list, rng, share: float) -> list:
    """Ensure roughly ``share`` of the values repeat an earlier value (DISTINCT targets)."""
    if len(values) < 2:
        return values
    n_dup = max(1, int(len(values) * share))
    for i in range(len(values) - n_dup, len(values)):
        values[i] = values[rng.randrange(0, max(1, len(values) - n_dup))]
    return values


def _boundary_pool(spec: dict, table: str, column: str) -> list:
    return list(((spec or {}).get('boundary_values') or {}).get(_k(table, column), []))


def _probe_only(spec: dict, table: str, column: str) -> set:
    return set(((spec or {}).get('boundary_probe_only') or {}).get(_k(table, column), []))


def _domain_pool(spec: dict, table: str, column: str) -> list:
    return list(((spec or {}).get('domains') or {}).get(_k(table, column), []))


def _null_share(spec: dict) -> float:
    return float((spec or {}).get('null_share', 0.05))


def _plant_nulls(values: list, rng, share: float) -> list:
    """Plant NULLs in a nullable column: at least one, share ~ compact share."""
    if not values:
        return values
    n_null = max(1, int(round(len(values) * share)))
    idx = rng.sample(range(len(values)), min(n_null, len(values)))
    for i in idx:
        values[i] = None
    return values


def _extend_parent_pk(schema, inst: dict, table: str, pk: str, needed: list, rng) -> None:
    """Ensure the parent PK pool (compact + generated) contains the needed literals."""
    have = set(v for v in inst[table].get(pk, []) if v is not None)
    for v in needed:
        if v not in have:
            inst[table].setdefault(pk, []).append(v)
            have.add(v)


def _group_counts(keys: list) -> dict:
    """Count occurrences of each non-NULL key."""
    out: dict = {}
    for k in keys:
        if k is None:
            continue
        out[k] = out.get(k, 0) + 1
    return out


def _plant_aggregate_ties(keys: list, rng, ranks=(1,)) -> list:
    """Adjust group membership so that the group counts tie at the listed ranks."""
    if not keys:
        return keys
    counts = _group_counts(keys)
    if len(counts) < 2:
        return keys
    ordered = sorted(counts.items(), key=lambda kv: kv[1])
    max_rank = max(ranks)
    if max_rank >= len(ordered):
        return keys
    target = ordered[max_rank - 1][1]
    raise_groups = [g for g, c in ordered[:max_rank] if c < target]
    if not raise_groups:
        return keys
    donors = [g for g, c in ordered if c > target]
    if not donors:
        return keys
    out = list(keys)
    for g in raise_groups:
        need = target - counts[g]
        for _ in range(need):
            if not donors:
                break
            d = donors[0]
            for i, v in enumerate(out):
                if v == d:
                    out[i] = g
                    counts[d] -= 1
                    counts[g] += 1
                    if counts[d] <= target:
                        donors.pop(0)
                    break
    return out


def _build_taughtby_aggregate_groups(schema, inst: dict, t: str, n: int, rng, spec: dict) -> dict:
    """Construct taughtBy rows so that COUNT(*) / COUNT(col) / COUNT(DISTINCT col) straddle the HAVING thresholds for
    *both* grouping columns (p_id and course_id)."""
    tm = schema.tables[t]
    agg = (spec or {}).get('aggregate_boundaries') or {}
    group_cols = [c.name for c in tm.columns if _k(t, c.name) in agg]
    if not group_cols:
        return {}
    pools = {}
    for c in tm.columns:
        if (t, c.name) in schema.fks:
            pt, pc = schema.fks[(t, c.name)]
            pools[c.name] = [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
    if not pools:
        return {}
    gcol = None
    for c in group_cols:
        if pools.get(c):
            gcol = c
            break
    if gcol is None:
        return {}
    gp = pools[gcol]
    thr = sorted(set(int(x) for x in agg[_k(t, gcol)].get('thresholds', [])))
    sizes = []
    for x in thr:
        sizes += [x, x + 1]
    sizes = sorted(set(s for s in sizes if s >= 1))
    if not sizes:
        sizes = [1, 2, 3]
    rows = {c.name: [] for c in tm.columns}
    used_pairs = set()
    gi = 0
    while len(rows[gcol]) < n:
        gkey = gp[gi % len(gp)]
        gsize = sizes[gi % len(sizes)]
        for _ in range(gsize):
            if len(rows[gcol]) >= n:
                break
            rows[gcol].append(gkey)
            for c in tm.columns:
                if c.name == gcol:
                    continue
                if c.name in pools:
                    cand = [v for v in pools[c.name] if (gkey, v) not in used_pairs]
                    if not cand:
                        cand = list(pools[c.name])
                    v = rng.choice(cand)
                    used_pairs.add((gkey, v))
                    rows[c.name].append(v)
                else:
                    rows[c.name].append(None)
        gi += 1
    for c in group_cols:
        if c == gcol:
            continue
        info = agg[_k(t, c)]
        dt = info.get('distinct_threshold')
        if dt is None or c not in pools or not pools[c]:
            continue
        distinct_vals = list(dict.fromkeys(pools[c]))
        if len(distinct_vals) <= dt:
            continue
        counts = _group_counts(rows[gcol])
        if not counts:
            continue
        big = max(counts.items(), key=lambda kv: kv[1])[0]
        idxs = [i for i, v in enumerate(rows[gcol]) if v == big]
        for j, i in enumerate(idxs[:dt + 1]):
            rows[c][i] = distinct_vals[j % len(distinct_vals)]
    return rows


def _plant_ties_on_group_counts(rows: dict, gcol: str, rng, ranks) -> None:
    """Plant ties on the aggregate group counts of ``gcol`` in-place."""
    keys = rows.get(gcol)
    if not keys:
        return
    new_keys = _plant_aggregate_ties(keys, rng, tuple(ranks))
    rows[gcol] = new_keys


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance: compact rows + appended generated rows (fuzz.py:111-196)."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)

    inst: dict = {}
    for t in schema.tables:
        inst[t] = _compact_rows(schema, t)

    null_targets = set((spec or {}).get('null_targets') or [])
    dup_share = float((spec or {}).get('duplicate_share', 0.35))
    tie_ranks = (spec or {}).get('tie_ranks') or {}
    group_sizes = tuple((spec or {}).get('group_sizes') or (1, 2, 3))
    dup_targets = set((spec or {}).get('duplicates_for_distinct') or [])
    group_targets = set((spec or {}).get('group_sizes_targets') or [])
    fk_boundary = (spec or {}).get('fk_boundary_targets') or {}

    for child_key, parent_key in fk_boundary.items():
        ct, cc = child_key.split('.', 1)
        pt, pc = parent_key.split('.', 1)
        if pt not in inst or ct not in schema.tables:
            continue
        needed = [v for v in _boundary_pool(spec, ct, cc) if isinstance(v, int)]
        if needed:
            _extend_parent_pk(schema, inst, pt, pc, needed, rng)

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            continue

        agg_rows = _build_taughtby_aggregate_groups(schema, inst, t, n, rng, spec) if t == 'taughtBy' else {}

        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.name in agg_rows and agg_rows[cm.name] and all(v is not None for v in agg_rows[cm.name]):
                cols[cm.name] = list(agg_rows[cm.name])
                continue
            dom = _domain_pool(spec, t, cm.name)
            bnd = _boundary_pool(spec, t, cm.name)
            probe = _probe_only(spec, t, cm.name)
            pool = list(literal_pool.get((t, cm.name), []))
            if dom:
                pool = dom + [b for b in bnd if b not in dom and b not in probe] + pool
            else:
                pool = [b for b in bnd if b not in probe] + pool
            enum = bool(dom)
            sampler = _init_sampler(cm, pool, schema.original_values.get((t, cm.name), []), p, rng,
                                    len(tm.primary_key), enum=enum)
            vals = [sampler.sample() for _ in range(n)]
            if bnd and not enum:
                inject = [b for b in bnd if b not in probe]
                for j, b in enumerate(inject):
                    if j < n:
                        vals[j] = b
            cols[cm.name] = vals

        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            existing = set(v for v in inst[t].get(pk, []) if v is not None)
            if all(isinstance(v, int) for v in existing) or not existing:
                start = (max(existing) + 1) if existing else 1
                fresh = []
                v = start
                for _ in range(n):
                    while v in existing:
                        v += 1
                    fresh.append(v)
                    existing.add(v)
                    v += 1
                cols[pk] = fresh
            else:
                cols[pk] = [rng.choice(list(existing)) if existing else i for i in range(n)]

        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            if cm.name in agg_rows and agg_rows[cm.name]:
                cols[cm.name] = list(agg_rows[cm.name])
                continue
            pt, pc = schema.fks[(t, cm.name)]
            pv = [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
            if not pv:
                raise RuntimeError('empty parent pool for FK %s.%s -> %s.%s' % (t, cm.name, pt, pc))
            cols[cm.name] = [rng.choice(pv) for _ in range(n)]

        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            bnd = [v for v in _boundary_pool(spec, t, cm.name) if isinstance(v, int)]
            if not bnd or cm.name not in cols:
                continue
            pt, pc = schema.fks[(t, cm.name)]
            parent_vals = set(v for v in inst.get(pt, {}).get(pc, []) if v is not None)
            inject = [v for v in bnd if v in parent_vals]
            for j, v in enumerate(inject):
                if j < len(cols[cm.name]):
                    cols[cm.name][j] = v

        cols = _equalize(cols, n)

        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if cm.pk_pos > 0 or cm.notnull:
                continue
            if (t, cm.name) in schema.fks:
                continue
            if _k(t, cm.name) in null_targets:
                cols[cm.name] = _plant_nulls(cols[cm.name], rng, _null_share(spec))

        for cm in tm.columns:
            if cm.name not in cols:
                continue
            k = _k(t, cm.name)
            vals = cols[cm.name]
            if k in dup_targets:
                vals = _plant_duplicates(vals, rng, dup_share)
            if k in group_targets:
                vals = _plant_group_sizes(vals, rng, group_sizes)
            cols[cm.name] = vals

        for cm in tm.columns:
            k = _k(t, cm.name)
            if k in tie_ranks and cm.name in cols:
                _plant_ties_on_group_counts(cols, cm.name, rng, tie_ranks[k])

        if t == 'advisedBy' and (spec or {}).get('advisedby_no_self', True):
            a, b = 'p_id', 'p_id_dummy'
            if a in cols and b in cols:
                for i in range(len(cols[a])):
                    if cols[a][i] is not None and cols[a][i] == cols[b][i]:
                        pt, pc = schema.fks.get((t, b), (None, None))
                        pv = [v for v in inst.get(pt, {}).get(pc, []) if v is not None and v != cols[a][i]]
                        if pv:
                            cols[b][i] = rng.choice(pv)

        cols = _equalize(cols, n)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)

        for c in tm.columns:
            if c.name in cols:
                inst[t].setdefault(c.name, [])
                inst[t][c.name] = list(inst[t][c.name]) + list(cols[c.name])

    return {t: inst[t] for t in schema.tables}
