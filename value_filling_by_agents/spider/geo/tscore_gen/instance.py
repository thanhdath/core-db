"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import null_share, table_size
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats a compact or generated key, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        share = null_share(spec, table, cm.name) if not cm.notnull and cm.pk_pos == 0 else 0.0
        vals = []
        for _ in range(n):
            if share and rng.random() < share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if share and n and all(v is not None for v in vals) and pv:
            vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def apply_null_rule(table: str, columns: dict, schema, rng, spec) -> dict:
    """NULL is a value: every nullable column gets NULL rows per its share and at least one NULL row."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in columns:
            continue
        vals = columns[cm.name]
        n = len(vals)
        if not n:
            continue
        share = null_share(spec, table, cm.name)
        for i in range(n):
            if rng.random() < share:
                vals[i] = None
        if all(v is not None for v in vals):
            vals[rng.randrange(n)] = None
    return columns


def apply_semantic_rules(table: str, columns: dict, schema, rng, spec) -> dict:
    """state_name <> border: a border row never names its own state (re-draw the border from other states)."""
    if table == 'border_info' and 'state_name' in columns and 'border' in columns:
        states = list(schema.original_values.get(('state', 'state_name'), []))
        states = [s for s in states if s is not None]
        for i in range(len(columns['state_name'])):
            if columns['border'][i] is not None and columns['border'][i] == columns['state_name'][i]:
                others = [s for s in states if s != columns['state_name'][i]]
                columns['border'][i] = rng.choice(others) if others else None
    return columns


def choose_table_sizes(schema, rng, spec) -> dict:
    """Specification table sizes with per-instance variation (0-230 rows per table)."""
    return {t: table_size(spec, t, rng) for t in schema.tables}


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) to be appended to the compact database."""
    if spec is None:
        from .spec import spec_from_columns
        spec = spec_from_columns()
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
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        cols = apply_null_rule(t, cols, schema, rng, spec)
        cols = apply_semantic_rules(t, cols, schema, rng, spec)
        taken = set()
        if tm.primary_key:
            ov = schema.original_values
            m = len(ov.get((t, tm.primary_key[0]), [])) if tm.primary_key else 0
            for i in range(m):
                taken.add(tuple(ov.get((t, c), [None] * m)[i] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
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
