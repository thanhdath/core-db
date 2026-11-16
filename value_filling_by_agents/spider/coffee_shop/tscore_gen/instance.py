"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven construction."""
from .spec import spec_key
from .values import _init_sampler

_MAX_RETRY = 100


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(cols: dict) -> int:
    return len(next(iter(cols.values()))) if cols else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    if any(c not in columns for c in table_meta.primary_key):
        return columns
    n = _nrows(columns)
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


def _fk_groups(schema, table: str) -> dict:
    """Group FK columns of `table` by parent table: {parent: [(child_col, parent_col), ...]}."""
    groups: dict = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key in schema.fks:
            pt, pc = schema.fks[key]
            groups.setdefault(pt, []).append((cm.name, pc))
    return groups


def _parent_tuples(instance: dict, schema, pt: str, pairs: list, reserved: dict) -> list:
    """Parent rows (as tuples of the referenced columns) usable as FK targets."""
    pcols = instance.get(pt) or {}
    if not pcols:
        return []
    plen = _nrows(pcols)
    ptm = schema.tables[pt]
    ref_cols = [pc for _, pc in pairs]
    res_col = ref_cols[0] if ref_cols else None
    skip = reserved.get(pt, set())
    tuples = []
    for i in range(plen):
        if res_col is not None and res_col in pcols and pcols[res_col][i] in skip:
            continue
        if any(pc not in pcols for pc in ref_cols):
            continue
        t = tuple(pcols[pc][i] for pc in ref_cols)
        if any(v is None for v in t):
            continue
        tuples.append(t)
    return tuples


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   reserved: dict = None) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
    reserved = reserved or {}
    out = {}
    for pt, pairs in _fk_groups(schema, table).items():
        tuples = _parent_tuples(instance, schema, pt, pairs, reserved)
        if not tuples:
            for cc, _ in pairs:
                out[cc] = [None] * n
            continue
        picks = [rng.choice(tuples) for _ in range(n)]
        for j, (cc, _) in enumerate(pairs):
            out[cc] = [p[j] for p in picks]
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification table sizes (per instance); fall back to the upstream rand_lin / level sizes."""
    sizes = {}
    ts = (spec or {}).get('table_sizes') or {}
    if ts:
        for t in schema.tables:
            sizes[t] = int(ts.get(t, 0))
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


def _next_pk_start(schema, table: str) -> int:
    """First integer above the compact rows' max PK (keys fresh against the compact rows)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    vals = schema.original_values.get((table, tm.primary_key[0]), [])
    ints = [v for v in vals if isinstance(v, int)]
    return (max(ints) + 1) if ints else 1


def _null_share(schema, table: str, column: str) -> float:
    """NULL share following the compact database's share for that column (at least one NULL row)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.1
    n_null = sum(1 for v in vals if v is None)
    return max(n_null / len(vals), 1.0 / max(1, len(vals)))


def _apply_null_rule(schema, table: str, cols: dict, spec: dict, rng) -> dict:
    """Plant NULLs in every nullable column: share from the compact db, at least one NULL row per column."""
    tm = schema.tables[table]
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        share = _null_share(schema, table, cm.name)
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _distinct_values(pool: list, sampler, want: int) -> list:
    """Up to `want` distinct non-NULL values from the pool, topped up from the sampler (bounded)."""
    vals = []
    for v in pool:
        if v is not None and v not in vals:
            vals.append(v)
        if len(vals) >= want:
            return vals
    tries = 0
    while len(vals) < want and sampler is not None and tries < _MAX_RETRY:
        tries += 1
        v = sampler.sample()
        if v is not None and v not in vals:
            vals.append(v)
    return vals


def _apply_group_sizes(schema, table: str, cols: dict, spec: dict, rng, samplers: dict) -> dict:
    """Ensure groups of size 1, 2 and >=3 exist for the listed GROUP columns (by construction)."""
    gs = (spec or {}).get('group_sizes') or {}
    tm = schema.tables[table]
    n = _nrows(cols)
    for cm in tm.columns:
        key = spec_key(table, cm.name)
        if key not in gs or cm.name not in cols or n < 6:
            continue
        if cm.pk_pos > 0 and len(tm.primary_key) == 1:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        vals = _distinct_values(pool, samplers.get((table, cm.name)), 3)
        if len(vals) < 3:
            continue
        assign = [vals[0]] * 1 + [vals[1]] * 2 + [vals[2]] * 3
        rest = n - len(assign)
        if rest < 0:
            continue
        assign += [rng.choice(pool) for _ in range(rest)]
        rng.shuffle(assign)
        cols[cm.name] = assign
    return cols


def _apply_tie_order(schema, table: str, cols: dict, spec: dict, rng) -> dict:
    """Enforce a tie at the listed rank for COUNT(*) groupings (two groups share the tie count)."""
    to = (spec or {}).get('tie_order') or {}
    tm = schema.tables[table]
    n = _nrows(cols)
    for cm in tm.columns:
        key = spec_key(table, cm.name)
        if key not in to or cm.name not in cols or n < 6:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        vals = []
        for v in pool:
            if v not in vals:
                vals.append(v)
            if len(vals) >= 2:
                break
        if len(vals) < 2:
            continue
        tie = max(1, (n - 2) // 3)
        assign = [vals[0]] * tie + [vals[1]] * tie
        rest = n - len(assign)
        assign += [rng.choice(pool) for _ in range(rest)]
        rng.shuffle(assign)
        cols[cm.name] = assign
    return cols


def _apply_aggregate_boundary(schema, table: str, cols: dict, spec: dict, rng, samplers: dict) -> dict:
    """Ensure at least one group has count equal to each listed boundary value (by construction)."""
    ab = (spec or {}).get('aggregate_boundary') or {}
    tm = schema.tables[table]
    n = _nrows(cols)
    for cm in tm.columns:
        key = spec_key(table, cm.name)
        if key not in ab or cm.name not in cols or n < 2:
            continue
        if cm.pk_pos > 0 and len(tm.primary_key) == 1:
            continue
        bounds = sorted({int(b) for b in ab[key] if isinstance(b, (int, float)) and int(b) >= 1})
        if not bounds:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        sizes = []
        for c in bounds:
            for s in (c - 1, c, c + 1):
                if s >= 1 and s <= n and s not in sizes:
                    sizes.append(s)
        if not sizes:
            continue
        vals = _distinct_values(pool, samplers.get((table, cm.name)), len(sizes))
        if len(vals) < len(sizes):
            continue
        assign = []
        for s, v in zip(sizes, vals):
            if len(assign) + s > n:
                break
            assign += [v] * s
        if not assign:
            continue
        rest = n - len(assign)
        assign += [rng.choice(pool) for _ in range(rest)]
        rng.shuffle(assign)
        cols[cm.name] = assign
    return cols


def _reserved_parent_keys(schema, spec: dict, rng) -> dict:
    """Reserve at least one parent referenced-column value per unmatched-join target."""
    uj = (spec or {}).get('unmatched_join') or {}
    reserved: dict = {}
    for key in uj:
        t, c = key.split('.', 1)
        tm = schema.tables.get(t)
        if tm is None or not tm.primary_key:
            continue
        ref = tm.primary_key[0]
        vals = schema.original_values.get((t, ref), [])
        ints = [v for v in vals if isinstance(v, int)]
        if ints:
            reserved.setdefault(t, set()).add(rng.choice(ints))
    return reserved


def _check_row(schema, table: str, row: dict, seen_pk: set, seen_unique: dict,
               parent_keys: dict) -> bool:
    """Python-side validation of NOT NULL / PK / UNIQUE / FK / CHECK (never SQL)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        v = row.get(cm.name)
        if v is None and (cm.notnull or cm.pk_pos > 0):
            return False
    pk = tuple(row.get(c) for c in tm.primary_key)
    if pk in seen_pk:
        return False
    for cm in tm.columns:
        if cm.unique and cm.name in row:
            v = row[cm.name]
            if v is not None and v in seen_unique.get(cm.name, set()):
                return False
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        v = row.get(cm.name)
        if v is None:
            continue
        pt, pc = schema.fks[key]
        if v not in parent_keys.get((pt, pc), set()):
            return False
    return True


def _finalize_table(schema, table: str, cols: dict, spec: dict, rng, samplers: dict) -> dict:
    """PK/unique dedup + group/tie/aggregate construction for one table (before any child FK fill)."""
    tm = schema.tables[table]
    cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
    cols = drop_unique_duplicates(tm, cols)
    cols = _apply_group_sizes(schema, table, cols, spec, rng, samplers)
    cols = _apply_tie_order(schema, table, cols, spec, rng)
    cols = _apply_aggregate_boundary(schema, table, cols, spec, rng, samplers)
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification-driven construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    domains = spec.get('domains') or {}
    pools = spec.get('pools') or {}
    boundaries = spec.get('boundaries') or {}
    like_variants = spec.get('like_variants') or {}
    dup_share = spec.get('duplicate_share') or {}
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                key = spec_key(t, cm.name)
                dom = dict(domains.get(key) or {})
                if key in pools:
                    dom['pool'] = pools[key]
                ds = dup_share.get(key)
                ds = (ds[0] + ds[1]) / 2.0 if isinstance(ds, (list, tuple)) and len(ds) == 2 else ds
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                    p, rng, len(tm.primary_key), domain=dom or None,
                    boundaries=boundaries.get(key), like_variants=like_variants.get(key),
                    duplicate_share=ds)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    reserved = _reserved_parent_keys(schema, spec, rng)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            start = _next_pk_start(schema, t)
            cols[tm.primary_key[0]] = list(range(start, start + n))
        inst[t] = _finalize_table(schema, t, cols, spec, rng, samplers)

    parent_keys: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 or cm.unique:
                parent_keys[(t, cm.name)] = {v for v in inst.get(t, {}).get(cm.name, []) if v is not None}

    for t in order:
        tm = schema.tables[t]
        n = _nrows(inst[t])
        cols = inst[t]
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, reserved))
        cols = _apply_group_sizes(schema, t, cols, spec, rng, samplers)
        cols = _apply_tie_order(schema, t, cols, spec, rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(schema, t, cols, spec, rng)
        inst[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = _nrows(cols)
        seen_pk, seen_unique, keep = set(), {}, []
        for i in range(n):
            row = {c: cols[c][i] for c in cols}
            if _check_row(schema, t, row, seen_pk, seen_unique, parent_keys):
                keep.append(i)
                seen_pk.add(tuple(row.get(c) for c in tm.primary_key))
                for cm in tm.columns:
                    if cm.unique and row.get(cm.name) is not None:
                        seen_unique.setdefault(cm.name, set()).add(row[cm.name])
        if len(keep) != n:
            inst[t] = _filter(cols, keep)
    return {t: inst[t] for t in schema.tables}
