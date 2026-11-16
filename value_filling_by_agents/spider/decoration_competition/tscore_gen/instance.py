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
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
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
    """Spec sizes when given; else uniform rand_lin w.p."""
    if spec is not None and spec.sizes:
        return {t: spec.size(t) for t in schema.tables}
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


def _compact_cols(schema, t: str) -> dict:
    """Compact rows of table t as {col: [values]} (read-only copy)."""
    tm = schema.tables[t]
    return {c.name: list(schema.original_values.get((t, c.name), [])) for c in tm.columns}


def _compact_n(schema, t: str) -> int:
    return int(schema.original_sizes.get(t, 0))


def _apply_enum(spec, t, col, values, rng):
    dom = spec.enum(t, col)
    if not dom:
        return values
    return [rng.choice(dom) if v is not None else None for v in values]


def _apply_range(spec, t, col, values, rng):
    r = spec.rng(t, col)
    if not r:
        return values
    lo, hi = r
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            out.append(v)
            continue
        out.append(max(lo, min(hi, iv)))
    return out


def _apply_literals(spec, t, col, values, rng):
    lits = spec.lits(t, col)
    if not lits:
        return values
    out = list(values)
    for x in lits:
        for cand in (x - 1, x, x + 1):
            if cand > 0 and cand not in out:
                out.append(cand)
    return out


def _apply_dup_share(spec, t, col, values, rng):
    """Force the duplicate share of distinct values into the target range."""
    share = spec.dup(t, col)
    if not share or not values:
        return values
    lo, hi = share
    n = len(values)
    distinct = [v for v in dict.fromkeys(values) if v is not None]
    if not distinct:
        return values
    target_dup = int(round(n * rng.uniform(lo, hi)))
    target_dup = max(0, min(n - 1, target_dup))
    keep_n = max(1, n - target_dup)
    head = distinct[:keep_n]
    out = list(head)
    while len(out) < n:
        out.append(rng.choice(head))
    rng.shuffle(out)
    return out


def _apply_ties(spec, t, col, values, rng):
    """Ensure at least two rows share the same value at the ORDER rank."""
    if not spec.tie_dir(t, col) or len(values) < 2:
        return values
    out = list(values)
    i, j = rng.sample(range(len(out)), 2)
    out[j] = out[i]
    return out


def _apply_agg_boundary(spec, t, col, values, rng):
    """Make group counts hit 1, 2 and >= 3 for the aggregate-boundary column."""
    counts = spec.agg(t, col)
    if not counts or not values:
        return values
    dom = spec.enum(t, col) or list(dict.fromkeys(v for v in values if v is not None))
    if not dom:
        return values
    sizes = [1, 2, max(counts)]
    plan = []
    for k, sz in enumerate(sizes):
        g = dom[k % len(dom)]
        plan.extend([g] * sz)
    out = list(values)
    for idx, g in enumerate(plan):
        if idx < len(out):
            out[idx] = g
        else:
            out.append(g)
    return out


def _apply_null_rule(spec, schema, t, col, values, rng):
    """At least one NULL for every nullable column; share follows the compact share."""
    if not spec.is_null_target(t, col):
        return values
    if not values:
        return values
    ov = schema.original_values.get((t, col), [])
    share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.0
    n = len(values)
    n_null = max(1, int(round(n * share)))
    n_null = min(n_null, n)
    out = list(values)
    idxs = list(range(n))
    rng.shuffle(idxs)
    for k in idxs[:n_null]:
        out[k] = None
    return out


def _apply_rules(spec, t, col, values):
    """Apply simple semantic rules (e.g. col > 0) to non-NULL operands only."""
    out = list(values)
    for (rt, rc, kind, payload) in spec.rules:
        if rt != t or rc != col:
            continue
        if kind == 'gt':
            out = [v if v is None or (isinstance(v, (int, float)) and v > payload) else
                   (payload + 1 if v is not None else None) for v in out]
    return out


def _fresh_keys(schema, t, n, rng):
    """Fresh integer keys for a single-column integer PK, above the compact max."""
    tm = schema.tables[t]
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    cm = next((c for c in tm.columns if c.name == pk), None)
    if cm is None or 'int' not in (cm.type_str or '').lower():
        return None
    ov = [v for v in schema.original_values.get((t, pk), []) if isinstance(v, int)]
    start = (max(ov) if ov else 0) + 1
    return list(range(start, start + n))


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as compact rows + appended generated rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)

    compact = {t: _compact_cols(schema, t) for t in schema.tables}
    gen: dict = {}

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            dom = spec.enum(t, cm.name) if spec is not None else None
            bounds = spec.rng(t, cm.name) if spec is not None else None
            lits = spec.lits(t, cm.name) if spec is not None else None
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), domain=dom, bounds=bounds, literals=lits)

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}

        fk = _fresh_keys(schema, t, n, rng)
        if fk is not None:
            cols[tm.primary_key[0]] = fk

        parent_pool = {}
        for pt in schema.tables:
            parent_pool[pt] = {}
            for pc in schema.tables[pt].columns:
                vals = list(compact.get(pt, {}).get(pc.name, []))
                vals += list(gen.get(pt, {}).get(pc.name, []))
                parent_pool[pt][pc.name] = vals
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = parent_pool.get(pt, {}).get(pc, [])
            cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n

        if spec is not None:
            for cm in tm.columns:
                if cm.name not in cols:
                    continue
                vals = cols[cm.name]
                vals = _apply_enum(spec, t, cm.name, vals, rng)
                vals = _apply_range(spec, t, cm.name, vals, rng)
                vals = _apply_literals(spec, t, cm.name, vals, rng)
                vals = _apply_dup_share(spec, t, cm.name, vals, rng)
                vals = _apply_ties(spec, t, cm.name, vals, rng)
                vals = _apply_agg_boundary(spec, t, cm.name, vals, rng)
                vals = _apply_rules(spec, t, cm.name, vals)
                vals = _apply_null_rule(spec, schema, t, cm.name, vals, rng)
                cols[cm.name] = vals

        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]

        gen[t] = cols

    inst: dict = {}
    for t in schema.tables:
        tm = schema.tables[t]
        merged = {}
        for cm in tm.columns:
            merged[cm.name] = list(compact[t].get(cm.name, [])) + list(gen[t].get(cm.name, []))
        inst[t] = merged
    return {t: inst[t] for t in schema.tables}
