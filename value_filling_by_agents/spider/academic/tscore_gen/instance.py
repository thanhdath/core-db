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


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent key values: compact rows first, then generated rows (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's values; NULL on nullable, no dangling keys."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        nullable = not spec['notnull'].get(key, False)
        null_share = spec['null_share'].get(key, 0.0) if nullable else 0.0
        col = []
        for _ in range(n):
            u = rng.random()
            if nullable and u < null_share:
                col.append(None)
            elif pv:
                col.append(rng.choice(pv))
            else:
                col.append(None if nullable else 0)
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Honour spec['sizes'] exactly (review item 3)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = max(0, int(spec['sizes'].get(t, 20)))
    return sizes


def _fresh_pk_start(schema, table: str, column: str) -> int:
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _apply_duplicates(cols: dict, key: tuple, share: float, rng) -> None:
    """Repeat a share of the values of a DISTINCT-target column (COUNT(DISTINCT) < COUNT(*))."""
    t, c = key
    if c not in cols or not cols[c]:
        return
    n = len(cols[c])
    k = int(n * share)
    if k <= 0:
        return
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:k]:
        j = rng.randrange(n)
        cols[c][i] = cols[c][j]


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows only."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            samplers[key] = _init_sampler(
                cm, literal_pool.get(key, []), schema.original_values.get(key, []), p, rng,
                len(tm.primary_key),
                domain=spec['ranges'].get(key),
                boundaries=spec['boundary_numeric'].get(key),
                near=spec['near_variants'].get(key),
                like=spec['like_patterns'].get(key),
                enum=spec['enums'].get(key),
                type_hint=spec['types'].get(key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for c in tm.primary_key:
            if c in cols and (t, c) not in schema.fks:
                start = _fresh_pk_start(schema, t, c)
                cols[c] = [start + i for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for cm in tm.columns:
            key = (t, cm.name)
            if spec['notnull'].get(key, False) or cm.name not in cols:
                continue
            if cols[cm.name] and all(v is not None for v in cols[cm.name]):
                cols[cm.name][rng.randrange(len(cols[cm.name]))] = None
        for key, share in spec['dup_share'].items():
            if key[0] == t:
                _apply_duplicates(cols, key, share, rng)
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
    return {t: inst[t] for t in schema.tables}
