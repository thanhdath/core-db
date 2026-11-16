"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
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


def _existing_pk_tuples(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _final_pk_values(inst: dict, schema, table: str, pk_col: str) -> list:
    """Final parent PK values: compact rows + generated rows (after dedup)."""
    compact = [v for v in schema.original_values.get((table, pk_col), []) if v is not None]
    gen = inst.get(table, {}).get(pk_col) or []
    return compact + [v for v in gen if v is not None]


def fill_foreign_keys_consistently(inst: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's FINAL PK set (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _final_pk_values(inst, schema, pt, pc)
        if not pv:
            out[cm.name] = [None] * n
            continue
        share = spec.FK_NULL_SHARE if (key in spec.NULL_SHARE and not cm.notnull) else 0.0
        vals = []
        for _ in range(n):
            if share and rng.random() < share:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        if share and n and all(v is not None for v in vals):
            vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes (TABLE_SIZES) with a small per-instance jitter."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            if t in spec.TABLE_SIZES:
                base = spec.TABLE_SIZES[t]
                sizes[t] = max(0, int(base * rng.uniform(0.75, 1.25)))
    if len(sizes) == sum(len(lvl) for lvl in schema.table_order):
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _apply_null_rule(table: str, columns: dict, schema, rng) -> dict:
    """NULL rule: only columns listed in spec.NULL_SHARE (the spec's null_targets) receive NULLs; each gets a share
    of generated rows and at least one NULL row."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if not n:
        return columns
    for cm in tm.columns:
        if cm.name not in columns or cm.notnull or cm.pk_pos > 0:
            continue
        key = (table, cm.name)
        if key in schema.fks:
            continue
        share = spec.NULL_SHARE.get(key)
        if share is None:
            continue
        vals = columns[cm.name]
        for i in range(n):
            if rng.random() < share:
                vals[i] = None
        if all(v is not None for v in vals):
            vals[rng.randrange(n)] = None
    return columns


def _apply_different_values(table: str, columns: dict, rng) -> dict:
    """rows_with_different_values: ensure >= 2 distinct non-NULL values per group."""
    if not columns:
        return columns
    n = len(next(iter(columns.values())))
    for (t, col), group_col in spec.DIFFERENT_VALUES.items():
        if t != table or col not in columns:
            continue
        vals = columns[col]
        if group_col is not None and group_col in columns:
            groups: dict = {}
            for i in range(n):
                groups.setdefault(columns[group_col][i], []).append(i)
        else:
            groups = {None: list(range(n))}
        for idxs in groups.values():
            if len(idxs) < 2:
                continue
            nonnull = [i for i in idxs if vals[i] is not None]
            if len(nonnull) < 2:
                continue
            distinct = {vals[i] for i in nonnull}
            if len(distinct) >= 2:
                continue
            base = vals[nonnull[0]]
            if isinstance(base, bool):
                alt = not base
            elif isinstance(base, (int, float)):
                alt = base + 1
            elif isinstance(base, str):
                alt = base + 'x'
            else:
                alt = str(base) + 'x'
            vals[nonnull[-1]] = alt
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) on top of the compact database."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), table=t)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        cols = _apply_null_rule(t, cols, schema, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns
                                              if cm.name in cols},
                                         _existing_pk_tuples(schema, t))
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        n = len(inst[t].get(tm.columns[0].name, [])) if tm.columns else 0
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        inst[t].update(fk_cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and cm.name in inst[t]:
                final = inst[t].get(pc) or []
                fs = set(final)
                inst[t][cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                    for v in inst[t][cm.name]]
    for t in order:
        inst[t] = _apply_different_values(t, inst[t], rng)
    return {t: inst[t] for t in schema.tables}
