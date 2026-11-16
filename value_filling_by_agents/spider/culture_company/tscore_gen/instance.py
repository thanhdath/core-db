"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
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


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specification sizes with per-instance variation; else upstream rand_lin / level sizes."""
    spec = spec or {}
    fixed = spec.get('table_sizes') or {}
    if fixed:
        sizes = {}
        for t in schema.tables:
            base = int(fixed.get(t, 0))
            if base <= 0:
                sizes[t] = 0
                continue
            lo = max(1, int(base * 0.75))
            hi = min(230, max(lo, int(base * 1.25)))
            sizes[t] = rng.randint(lo, hi)
        return sizes
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


def _null_share(schema, key, rng) -> float:
    """NULL share following the compact database's share for the column (0 if none observed)."""
    vals = schema.original_values.get(key) or []
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _plant_nulls(cols: dict, schema, table: str, spec: dict, rng) -> None:
    """NULL rule: for every nullable column, at least one NULL and a share of NULLs."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    null_cols = set(spec.get('null_columns') or [])
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        key = (table, cm.name)
        share = _null_share(schema, key, rng)
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None


def _apply_group_sizes(cols: dict, table: str, spec: dict, rng) -> None:
    """GROUP BY column: make group sizes 1, 2 and >= 3 (specification group_sizes)."""
    for key, sizes in (spec.get('group_sizes') or {}).items():
        t, c = key.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 3:
            continue
        seq = []
        for s in sizes:
            seq.extend([None] * s)
        while len(seq) < n:
            seq.append(None)
        seq = seq[:n]
        rng.shuffle(seq)
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        pool = list(dict.fromkeys(vals))
        gi = 0
        cur = None
        for i in range(n):
            if seq[i] is None:
                cur = pool[gi % len(pool)]
                gi += 1
            cols[c][i] = cur


def _apply_aggregate_boundary(cols: dict, table: str, spec: dict, rng) -> None:
    """HAVING COUNT(*) boundary: ensure groups of size 1, 2 and 3 exist for the column."""
    for key, rule in (spec.get('aggregate_boundary') or {}).items():
        t, c = key.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 3:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        pool = list(dict.fromkeys(vals))
        seq = [1, 2, 3] + [1] * max(0, n - 6)
        seq = seq[:n]
        rng.shuffle(seq)
        out, gi = [], 0
        for s in seq:
            v = pool[gi % len(pool)]
            gi += 1
            out.extend([v] * s)
        cols[c] = out[:n]


def _apply_order_ties(cols: dict, table: str, spec: dict, rng) -> None:
    """ORDER BY column: at least two rows with the same value at the target rank."""
    for key, rule in (spec.get('order_ties') or {}).items():
        t, c = key.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        direction = (rule.get('direction') or 'desc').lower()
        try:
            top = max(vals) if direction == 'desc' else min(vals)
        except TypeError:
            top = vals[0]
        idx = [i for i, v in enumerate(cols[c]) if v == top]
        if len(idx) < 2:
            for i in range(n):
                if cols[c][i] != top:
                    cols[c][i] = top
                    break


def _apply_duplicates(cols: dict, table: str, spec: dict, rng) -> None:
    """DISTINCT column: duplicate share 20-50 % (duplicate values after joins and filters)."""
    for key, col in (spec.get('columns') or {}).items():
        t, c = key.split('.', 1)
        if t != table or c not in cols or 'duplicate_share' not in col:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        lo, hi = col['duplicate_share']
        share = rng.uniform(lo, hi)
        k = max(1, int(round(share * n)))
        k = min(k, n - 1)
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        for i in rng.sample(range(n), k):
            cols[c][i] = rng.choice(vals)


def _apply_join_targets(inst: dict, schema, spec: dict, rng) -> None:
    """Join targets: parent rows without children and child rows with NULL FK."""
    for j in spec.get('joins') or []:
        left, right = j.get('left'), j.get('right')
        if not left or not right:
            continue
        lt, lc = left.split('.', 1)
        rt, rc = right.split('.', 1)
        if lt not in inst or rt not in inst:
            continue
        lvals = set(v for v in inst[lt].get(lc, []) if v is not None)
        rvals = set(v for v in inst[rt].get(rc, []) if v is not None)
        if j.get('parent_rows_without_children') and lvals:
            unmatched = lvals - rvals
            if not unmatched:
                for i, v in enumerate(inst[rt].get(rc, [])):
                    if v is not None:
                        inst[rt][rc][i] = max(lvals) + 1 + i
                        break
        if j.get('child_rows_with_null_fk') and inst[rt].get(rc):
            if all(v is not None for v in inst[rt][rc]):
                inst[rt][rc][rng.randrange(len(inst[rt][rc]))] = None


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                spec_col = (spec.get('columns') or {}).get('%s.%s' % (t, cm.name))
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec_col=spec_col)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
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
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        if t not in inst:
            continue
        _apply_group_sizes(inst[t], t, spec, rng)
        _apply_aggregate_boundary(inst[t], t, spec, rng)
        _apply_order_ties(inst[t], t, spec, rng)
        _apply_duplicates(inst[t], t, spec, rng)
        _plant_nulls(inst[t], schema, t, spec, rng)
    _apply_join_targets(inst, schema, spec, rng)
    return {t: inst[t] for t in schema.tables}
