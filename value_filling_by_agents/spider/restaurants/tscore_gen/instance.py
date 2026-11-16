"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification rules."""
from . import spec
from .values import _init_sampler, spec_elements, spec_numeric_range, near_variants


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row); first occurrence kept."""
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


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (also against compact rows)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(existing.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_keys: dict) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_keys.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        nullable = not cm.notnull and cm.pk_pos == 0
        vals = []
        for _ in range(n):
            u = rng.random()
            if nullable and u < 0.10:
                vals.append(None)
            elif nullable and u < 0.20:
                vals.append(_orphan_value(pv, cm, rng))
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None if nullable else _orphan_value(pv, cm, rng))
        out[cm.name] = vals
    return out


def _orphan_value(parent_values: list, cm, rng):
    """A value that is not in the parent pool (typed by the column)."""
    if 'int' in (cm.type_str or '').lower():
        used = {v for v in parent_values if isinstance(v, int)}
        v = rng.randint(100000, 999999)
        while v in used:
            v += 1
        return v
    base = 'orphan city'
    v = base
    used = {str(x) for x in parent_values}
    while v in used:
        v = base + str(rng.randint(1, 9999))
    return v


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes, with a small per-instance jitter (0-230 rows)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t.upper())
        if base is None:
            base = 30
        jitter = rng.randint(-5, 5)
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _compact_keys(schema) -> dict:
    """Parent key pools from the compact database (held in memory)."""
    out = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        out.setdefault((pt, pc), [])
    for (pt, pc) in list(out):
        out[(pt, pc)] = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    return out


def _compact_existing(schema) -> dict:
    """Existing PK tuples and unique values per table (for dedup against compact rows)."""
    pk, uniq = {}, {}
    for t, tm in schema.tables.items():
        if tm.primary_key:
            cols = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            n = min((len(c) for c in cols), default=0)
            pk[t] = {tuple(c[i] for c in cols) for i in range(n)}
        for cm in tm.columns:
            if cm.unique:
                uniq.setdefault(t, {})[cm.name] = set(schema.original_values.get((t, cm.name), []))
    return pk, uniq


def _apply_null_rule(table: str, column: str, values: list, nullable: bool, rng) -> list:
    """NULL rule: at least one NULL row per nullable column; share ~ DEFAULT_NULL_SHARE."""
    if not nullable or not values:
        return values
    share = spec.DEFAULT_NULL_SHARE
    n = len(values)
    n_null = max(1, int(round(n * share)))
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:n_null]:
        values[i] = None
    return values


def _apply_duplicate_rule(table: str, column: str, values: list, rng) -> list:
    """DISTINCT duplicate rule: 20-50% of values are duplicates of other rows."""
    share = spec.DISTINCT_DUPLICATE_SHARE.get((table.upper(), column.upper()))
    if share is None or len(values) < 2:
        return values
    n_dup = int(round(len(values) * share))
    idx = list(range(len(values)))
    rng.shuffle(idx)
    for i in idx[:n_dup]:
        j = rng.choice([k for k in range(len(values)) if k != i])
        values[i] = values[j]
    return values


def _apply_formula(table: str, column: str, values: list, rng) -> list:
    """Semantic formula by construction: resample non-NULL values until the rule holds."""
    fn = spec.FORMULAS.get((table.upper(), column.upper()))
    if fn is None:
        return values
    rng_spec = spec_numeric_range(table, column)
    for i, v in enumerate(values):
        if v is None:
            continue
        if fn(v):
            continue
        if rng_spec is not None:
            lo, hi, is_int, prec = rng_spec
            if is_int:
                values[i] = rng.randint(int(lo), int(hi))
            else:
                values[i] = round(rng.uniform(lo, hi), prec)
        else:
            values[i] = None
    return values


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification rules."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact_keys = _compact_keys(schema)
    compact_pk, compact_uniq = _compact_existing(schema)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                els = spec_elements(t, cm.name, literal_pool.get((t, cm.name), []))
                samplers[(t, cm.name)] = _init_sampler(cm, els,
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_keys))
        for cm in tm.columns:
            if cm.name in cols:
                nullable = (not cm.notnull) and cm.pk_pos == 0
                cols[cm.name] = _apply_null_rule(t, cm.name, cols[cm.name], nullable, rng)
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_duplicate_rule(t, cm.name, cols[cm.name], rng)
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_formula(t, cm.name, cols[cm.name], rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         compact_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols, compact_uniq.get(t, {}))
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
