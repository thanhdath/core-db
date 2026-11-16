"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, spec_sampler


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   fk_null_share: float = 0.10) -> dict:
    """FK child columns draw from the parent's values with replacement; NULL by the NULL rule."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        vals = []
        for _ in range(n):
            if not pv or rng.random() < fk_null_share:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict = None) -> dict:
    """Specification table sizes (per instance) with a small random jitter."""
    sizes = {}
    spec_sizes = (spec or {}).get('table_sizes', {})
    for lvl in schema.table_order:
        for t in lvl:
            base = int(spec_sizes.get(t, 0))
            if base <= 0:
                base = int(30 * rng.random() + int(rng.random() * 200))
            jitter = int(base * 0.1)
            sizes[t] = max(0, base + rng.randint(-jitter, jitter))
    return sizes


def _apply_null_rule(table: str, columns: dict, spec: dict, rng) -> dict:
    """Each nullable column: NULL share from the specification, at least one NULL row."""
    shares = spec.get('null_share', {})
    for col, vals in columns.items():
        key = '%s.%s' % (table, col)
        share = shares.get(key)
        if share is None:
            continue
        n = len(vals)
        if n == 0:
            continue
        k = max(1, int(round(share * n)))
        idx = list(range(n))
        rng.shuffle(idx)
        for i in idx[:k]:
            vals[i] = None
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification-driven samplers."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + \
                  sorted({str(v) for v in literal_pool.get((t, cm.name), [])})
            max_l0 = float('inf')
            if rng.random() < 0.5:
                max_l0 = rng.random() * 30
                if cm.pk_pos > 0:
                    max_l0 = float('inf') if len(tm.primary_key) == 1 else 30
            s = spec_sampler(t, cm.name, spec, rng, els, p, max_l0)
            if s is None:
                s = _init_sampler(cm, literal_pool.get((t, cm.name), []), ov, p, rng, len(tm.primary_key))
            samplers[(t, cm.name)] = s
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                   spec.get('fk_null_share', 0.10)))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(t, cols, spec, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
