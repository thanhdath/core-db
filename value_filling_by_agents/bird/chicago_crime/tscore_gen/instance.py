"""Random instance construction (fuzz/fuzz.py:83-196), adapted for append-to-compact instances."""
from .spec import column_spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact key), first occurrence kept."""
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


def _parent_keys(schema, instance, pt, pc):
    """Compact parent keys plus generated parent keys (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec) -> dict:
    """FK child columns draw from the parent's keys; a share is NULL (unmatched-join rule)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_keys(schema, instance, pt, pc)
        col = []
        for _ in range(n):
            u = rng.random()
            if u < spec.get('fk_null', 0.05) or not pv:
                col.append(None)
            else:
                col.append(rng.choice(pv))
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng, spec) -> dict:
    """Sizes from the specification (table_sizes_per_instance), varied per instance."""
    sizes = {}
    for t in schema.tables:
        base = spec.get('sizes', {}).get(t)
        if base is None:
            base = max(1, min(230, schema.original_sizes.get(t, 30)))
        lo = max(0, int(base * 0.5))
        hi = min(230, max(lo + 1, int(base * 1.5) + 1))
        sizes[t] = rng.randint(lo, hi)
    return sizes


def _apply_null_rule(cols: dict, table: str, schema, spec, rng) -> dict:
    """NULL share per nullable column (compact share), at least one NULL row per nullable column."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        cs = column_spec(spec, table, cm.name)
        share = cs.get('null_share')
        is_fk = (table, cm.name) in schema.fks
        if share is None and not is_fk:
            continue
        if share is None:
            ov = schema.original_values.get((table, cm.name), [])
            share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.05
        share = max(0.0, min(0.9, float(share)))
        k = max(1, int(round(share * n)))
        idx = list(range(n))
        rng.shuffle(idx)
        for i in idx[:k]:
            cols[cm.name][i] = None
    return cols


def _apply_duplicate_rule(cols: dict, table: str, schema, spec, rng) -> dict:
    """Repeat 20-50% of values on flagged non-PK columns so COUNT(DISTINCT) < COUNT(*)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 3:
        return cols
    pk = set(schema.tables[table].primary_key)
    for (t, c), share in spec.get('dups', {}).items():
        if t != table or c not in cols or c in pk:
            continue
        k = max(1, int(round(share * n)))
        idx = list(range(n))
        rng.shuffle(idx)
        src = idx[:k]
        dst = idx[k:2 * k]
        for a, b in zip(src, dst):
            cols[c][b] = cols[c][a]
    return cols


def _apply_tie_rule(cols: dict, table: str, spec, rng) -> dict:
    """Plant at least two rows sharing a value on flagged columns (rank-1 ties)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return cols
    for (t, c) in spec.get('ties', set()):
        if t != table or c not in cols:
            continue
        a, b = rng.sample(range(n), 2)
        cols[c][b] = cols[c][a]
        if n >= 6 and (t, c) in {('Ward', 'ward_no')}:
            rest = [i for i in range(n) if i not in (a, b)]
            x, y = rng.sample(rest, 2)
            cols[c][y] = cols[c][x]
    return cols


def _extra_enum_values(schema, table, column, listed):
    """Compact values not in the listed enum (open domains, e.g. the 9th Community_Area.side)."""
    ov = schema.original_values.get((table, column), [])
    listed_set = {str(v) for v in listed}
    return [v for v in ov if v is not None and str(v) not in listed_set]


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as generated rows to append to the compact DB."""
    spec = spec or {'enums': {}, 'ranges': {}, 'nulls': {}, 'dups': {}, 'joins': set(), 'ties': set(),
                    'boundaries': {}, 'likes': {}, 'sizes': {}, 'fk_null': 0.05, 'fk_orphan': 0.0}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                cs = column_spec(spec, t, cm.name)
                extra = _extra_enum_values(schema, t, cm.name, cs.get('enum') or []) if cs.get('enum') else None
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), cspec=cs, extra_enum=extra)
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
        taken = set()
        if tm.primary_key:
            ov = schema.original_values
            if len(tm.primary_key) == 1:
                taken = {(v,) for v in ov.get((t, tm.primary_key[0]), []) if v is not None}
            else:
                lists = [ov.get((t, c), []) for c in tm.primary_key]
                taken = set(zip(*lists)) if lists and all(lists) else set()
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(cols, t, schema, spec, rng)
        cols = _apply_duplicate_rule(cols, t, schema, spec, rng)
        cols = _apply_tie_rule(cols, t, spec, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
