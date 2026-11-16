"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import exception_for, formula_for, is_null_target, table_size
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set = None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen = set(existing or ())
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    existing = existing or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing.get(cm.name, ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent key values: compact rows (from schema.original_values) + generated rows."""
    vals = list(schema.original_values.get((pt, pc), []) or [])
    vals += list(instance.get(pt, {}).get(pc, []) or [])
    return [v for v in vals if v is not None]


def _null_share(schema, table: str, column: str, exc: dict) -> float:
    """NULL share for a nullable column: spec null_share, else compact share, else 0-5%."""
    if 'null_share' in exc:
        lo, hi = exc['null_share']
        return (lo + hi) / 2.0
    ov = schema.original_values.get((table, column), []) or []
    if ov:
        share = sum(1 for v in ov if v is None) / float(len(ov))
        if share > 0:
            return share
    return 0.02


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's rows (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        exc = exception_for(spec, table, cm.name)
        if is_null_target(spec, table, cm.name):
            null_share = _null_share(schema, table, cm.name, exc)
        else:
            null_share = 0.0
        col = []
        for _ in range(n):
            if null_share > 0.0 and (rng.random() < null_share or not pv):
                col.append(None)
            else:
                col.append(rng.choice(pv) if pv else None)
        if n > 0 and null_share > 0.0 and all(v is not None for v in col):
            col[rng.randrange(n)] = None
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Per-instance table sizes from the specification (jittered), else the generic rule."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = table_size(spec, t, rng)
    return sizes


def _existing_keys(schema, table: str) -> dict:
    """Compact PK tuples and unique column values per table (to keep generated keys fresh)."""
    tm = schema.tables[table]
    pk = set()
    if tm.primary_key:
        cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
        n = min((len(c) for c in cols), default=0)
        for i in range(n):
            pk.add(tuple(c[i] for c in cols))
    uniq = {}
    for cm in tm.columns:
        if cm.unique:
            uniq[cm.name] = set(v for v in schema.original_values.get((table, cm.name), []) if v is not None)
    return {'pk': pk, 'uniq': uniq}


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                exc = exception_for(spec, t, cm.name)
                formula = formula_for(spec, t, cm.name)
                nullable = is_null_target(spec, t, cm.name) and cm.pk_pos == 0 and not cm.notnull
                null_share = _null_share(schema, t, cm.name, exc) if nullable else 0.0
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), exc=exc, formula=formula,
                                                       nullable=nullable, null_share=null_share)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        existing = _existing_keys(schema, t)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing['pk'])
        cols = drop_unique_duplicates(tm, cols, existing['uniq'])
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
