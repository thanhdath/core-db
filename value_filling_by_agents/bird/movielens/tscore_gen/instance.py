"""Random instance construction (fuzz/fuzz.py:83-196), round 1: append to a copy of the compact DB."""
from .spec import boundary_for, size_for
from .values import _init_sampler

FRESH_P = 0.2


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
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        if not pv:
            if cm.notnull:
                raise ValueError('empty parent pool for NOT NULL FK %s.%s -> %s.%s' % (table, cm.name, pt, pc))
            out[cm.name] = [None] * n
        else:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specification sizes with per-instance variation (0-230 rows per table)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = size_for(spec, t, rng) if spec is not None else int(30 * rng.random() + int(rng.random() * 200))
    return sizes


def _fresh_pk_start(schema, table: str, rng) -> int:
    """First generated key: above the compact max (or 1), with a small random gap."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1 + rng.randint(0, 3)) if vals else 1


def _parent_pk_pool(schema, table: str, col: str, inst: dict) -> set:
    """All key values a child may reference: compact values plus generated parent values."""
    pool = {v for v in schema.original_values.get((table, col), []) if v is not None}
    pool |= {v for v in (inst.get(table, {}).get(col) or []) if v is not None}
    return pool


def _plant_parent_keys(schema, inst: dict, spec, rng) -> None:
    """Co-generate FK boundary literals as parent PKs so child boundary rows resolve."""
    if spec is None:
        return
    for (ct, cc), (pt, pc) in sorted(schema.fks.items()):
        targets = [v for v in boundary_for(spec, ct, cc) if isinstance(v, int) and not isinstance(v, bool)]
        if not targets:
            continue
        pcols = inst.get(pt)
        if not pcols or pc not in pcols:
            continue
        existing = set(pcols[pc]) | {v for v in schema.original_values.get((pt, pc), []) if v is not None}
        for v in targets:
            if v in existing:
                continue
            for cname, vals in pcols.items():
                if cname == pc:
                    vals.append(v)
                elif vals:
                    vals.append(rng.choice(vals))
                else:
                    vals.append(None)
            existing.add(v)


def _plant_exceptions(table: str, cols: dict, spec, rng, fk_cols: set) -> None:
    """Plant boundary / near-variant literals in a few rows (comparison_boundary pattern)."""
    if spec is None or not cols:
        return
    n = len(next(iter(cols.values())))
    if n == 0:
        return
    for cname in list(cols):
        if cname in fk_cols:
            continue
        vals = boundary_for(spec, table, cname)
        if not vals:
            continue
        k = min(len(vals), max(1, n // 10))
        idx = rng.sample(range(n), k)
        for j, i in enumerate(idx):
            cols[cname][i] = vals[j % len(vals)]


def _plant_ties(table: str, cols: dict, rng, fk_cols: set) -> None:
    """Duplicate a few rows' non-key values to create ties at rank 1 and duplicate groups."""
    if not cols:
        return
    n = len(next(iter(cols.values())))
    if n < 4:
        return
    for cname in list(cols):
        if cname in fk_cols:
            continue
        if rng.random() < 0.5:
            continue
        a, b = rng.sample(range(n), 2)
        cols[cname][b] = cols[cname][a]


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification domains by construction."""
    p = FRESH_P
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec=spec)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            start = _fresh_pk_start(schema, t, rng)
            cols[tm.primary_key[0]] = [start + i for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        fk_cols = {cm.name for cm in tm.columns if (t, cm.name) in schema.fks}
        _plant_exceptions(t, cols, spec, rng, fk_cols)
        _plant_ties(t, cols, rng, fk_cols)
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
    _plant_parent_keys(schema, inst, spec, rng)
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pool = _parent_pk_pool(schema, pt, pc, inst)
            if not pool:
                continue
            vals = inst[t].get(cm.name) or []
            inst[t][cm.name] = [v if v in pool else rng.choice(sorted(pool, key=str)) for v in vals]
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
