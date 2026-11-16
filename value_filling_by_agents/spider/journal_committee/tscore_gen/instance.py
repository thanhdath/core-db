"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 append-to-compact semantics."""
from .values import _init_sampler, plan_multiset


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


def _compact_max(schema, table: str, column: str):
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, (int, float))]
    return max(vals) if vals else 0


def _null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   spec: dict = None) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    spec = spec or {}
    null_targets = set(spec.get('null_targets', []))
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        nullable = (not cm.notnull) and cm.pk_pos == 0
        share = _null_share(schema, table, cm.name) if nullable else 0.0
        if key in null_targets and nullable:
            share = max(share, 0.1)
        vals = []
        for _ in range(n):
            if nullable and pv and rng.random() < share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if nullable and pv and n > 0 and all(v is not None for v in vals):
            vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict = None) -> dict:
    """Specification sizes per instance (table_sizes_per_instance), else upstream rand_lin / level sizes."""
    spec = spec or {}
    fixed = spec.get('table_sizes') or {}
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


def _plant_nulls(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """NULL rule: nullable columns get a NULL share from the compact DB and at least one NULL row."""
    null_targets = set(spec.get('null_targets', []))
    for cm in schema.tables[table].columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
            continue
        if (table, cm.name) in schema.fks:
            continue
        share = _null_share(schema, table, cm.name)
        if (table, cm.name) in null_targets:
            share = max(share, 0.1)
        if share <= 0.0:
            continue
        for i in range(n):
            if rng.random() < share:
                cols[cm.name][i] = None
        if n > 0 and all(v is not None for v in cols[cm.name]):
            cols[cm.name][rng.randrange(n)] = None


def _pattern_columns(spec: dict) -> set:
    """Columns whose per_column_exceptions ask for group-size / duplicate-share targets."""
    out = set()
    for exc in spec.get('pattern_columns') or []:
        out.add(tuple(exc))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) to be appended to the compact database."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
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
    pattern_cols = _pattern_columns(spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) not in samplers:
                continue
            s = samplers[(t, cm.name)]
            if (t, cm.name) in pattern_cols and n > 0:
                cols[cm.name] = plan_multiset(s, n, rng)
            else:
                cols[cm.name] = [s.sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                base = _compact_max(schema, t, cm.name)
                cols[cm.name] = [base + 1 + i for i in range(n)]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _plant_nulls(schema, t, cols, len(cols.get(tm.columns[0].name, [])) if tm.columns else 0, rng, spec)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
