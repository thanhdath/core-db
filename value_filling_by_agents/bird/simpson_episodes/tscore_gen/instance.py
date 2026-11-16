"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .specification import (column_spec, is_hard_formula, load_specification, null_share,
                            table_size)
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


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(existing.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _plant_nulls(values: list, share: float, rng) -> list:
    """NULL rule: each instance has NULL and non-NULL rows; share follows the compact share, at least one NULL row
    per nullable column."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n - 1) if n > 1 else n
    idx = set(rng.sample(range(n), k))
    return [None if i in idx else v for i, v in enumerate(values)]


def _inject_boundaries(values: list, boundaries: list, rng, protected: set = None) -> list:
    """Cycle boundary values across rows, skipping protected (already-boundary) rows so every boundary is present."""
    if not values or not boundaries:
        return values
    out = list(values)
    protected = set(protected or ())
    slots = [i for i in range(len(out)) if i not in protected]
    if not slots:
        return out
    for k, b in enumerate(boundaries):
        i = slots[k % len(slots)]
        out[i] = b
        protected.add(i)
    return out


def _inject_duplicates(values: list, share: float, rng, protected: set = None) -> list:
    """Force a non-unique column to share a duplicate value (20-50% of rows), never overwriting protected (boundary)
    rows."""
    n = len(values)
    if n < 3:
        return values
    protected = set(protected or ())
    k = max(2, int(round(share * n)))
    k = min(k, n - 1)
    if k < 2:
        return values
    candidates = [i for i in range(n) if i not in protected]
    if len(candidates) < 2:
        return values
    src = rng.choice(candidates)
    target = values[src]
    if target is None:
        return values
    others = [i for i in candidates if i != src]
    kk = min(k - 1, len(others))
    idx = rng.sample(others, kk)
    out = list(values)
    for i in idx:
        out[i] = target
    return out


def _plant_ties(values: list, rng, protected: set = None) -> list:
    """Deterministic rank-1 tie: two rows share the min and two share the max (ASC and DESC tie_at_rank 1)."""
    n = len(values)
    if n < 2:
        return values
    protected = set(protected or ())
    out = list(values)
    free = [i for i in range(n) if i not in protected]
    if len(free) < 2:
        return out
    nonnull = [v for v in out if v is not None]
    if not nonnull:
        return out
    lo, hi = min(nonnull), max(nonnull)
    a, b = free[0], free[1]
    out[a] = lo
    out[b] = hi
    if len(free) >= 4:
        out[free[2]] = lo
        out[free[3]] = hi
    return out


def _enforce_formula(table: str, column: str, values: list, spec: dict) -> list:
    """Clamp / enumerate sampled values so a HARD semantic formula holds for non-NULL operands."""
    if not is_hard_formula(spec, table, column):
        return values
    cs = column_spec(spec, table, column)
    dom = cs.get('domain')
    enum = cs.get('enum')
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if enum:
            out.append(v if v in enum else enum[0])
        elif dom is not None:
            lo, hi = dom
            try:
                out.append(max(lo, min(hi, v)))
            except TypeError:
                out.append(v)
        else:
            out.append(v)
    return out


def _max_boundaries(spec: dict, table: str, tm) -> int:
    """Largest boundary list length over the table's columns (min rows per table)."""
    m = 0
    for cm in tm.columns:
        b = column_spec(spec, table, cm.name).get('boundaries') or []
        m = max(m, len(b))
    return m


def choose_table_sizes(schema, rng, spec) -> dict:
    """Specification sizes, varied per instance (0-230 rows, or level x4 capped at 2500), but never fewer rows than
    the largest boundary list for the table's columns."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = table_size(spec, t, 20)
                sizes[t] = max(0, int(base * rng.uniform(0.5, 1.5)))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    for lvl in schema.table_order:
        for t in lvl:
            need = _max_boundaries(spec, t, schema.tables[t])
            if sizes.get(t, 0) < need:
                sizes[t] = need
    return sizes


def _final_parent_keys(schema, inst: dict, compact: dict, pt: str, pc: str) -> list:
    """Final surviving parent key values: compact + generated (deduped, non-NULL)."""
    vals = list(compact.get((pt, pc), [])) + list(inst.get(pt, {}).get(pc) or [])
    seen, out = set(), []
    for v in vals:
        if v is None:
            continue
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _remap_fk(values: list, parent_vals: list, nullable: bool, rng) -> list:
    """Remap any FK value not in the final parent set to a valid parent value (or NULL)."""
    pset = set(parent_vals)
    out = []
    for v in values:
        if v is None:
            out.append(None)
        elif v in pset:
            out.append(v)
        elif parent_vals:
            out.append(rng.choice(parent_vals))
        elif nullable:
            out.append(None)
        else:
            out.append(v)
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, compact: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    spec = load_specification()
    compact = compact or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), spec=column_spec(spec, t, cm.name))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = _final_parent_keys(schema, inst, compact, pt, pc)
            vals = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
            if not cm.notnull and cm.pk_pos == 0:
                share = null_share(spec, t, cm.name)
                vals = _plant_nulls(vals, share, rng)
            cols[cm.name] = vals
        for cm in tm.columns:
            if (t, cm.name) in schema.fks or cm.notnull or cm.pk_pos > 0:
                continue
            if cm.name not in cols:
                continue
            share = null_share(spec, t, cm.name)
            cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
        for cm in tm.columns:
            if cm.name in cols and not cm.unique and cm.pk_pos == 0 and (t, cm.name) not in schema.fks:
                share = 0.2 + 0.3 * rng.random()
                cols[cm.name] = _inject_duplicates(cols[cm.name], share, rng)
        protected: dict = {}
        for cm in tm.columns:
            if cm.name in cols:
                cs = column_spec(spec, t, cm.name)
                bnd = cs.get('boundaries') or []
                if bnd:
                    prot = set()
                    cols[cm.name] = _inject_boundaries(cols[cm.name], bnd, rng, prot)
                    protected[cm.name] = prot
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _enforce_formula(t, cm.name, cols[cm.name], spec)
        for col in ('votes', 'rating'):
            if t == 'Episode' and col in cols:
                cols[col] = _plant_ties(cols[col], rng, protected.get(col))
        existing_pk = set()
        if tm.primary_key:
            pkvals = [compact.get((t, c), []) for c in tm.primary_key]
            if all(pkvals):
                existing_pk = set(zip(*pkvals))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing_pk)
        existing_uniq = {cm.name: set(v for v in compact.get((t, cm.name), []) if v is not None)
                         for cm in tm.columns if cm.unique}
        cols = drop_unique_duplicates(tm, cols, existing_uniq)
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks or cm.name not in inst.get(t, {}):
                continue
            pt, pc = schema.fks[key]
            pv = _final_parent_keys(schema, inst, compact, pt, pc)
            inst[t][cm.name] = _remap_fk(inst[t][cm.name], pv, not cm.notnull, rng)
    return {t: inst[t] for t in schema.tables}
