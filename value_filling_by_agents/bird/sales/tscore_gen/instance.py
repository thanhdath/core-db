"""Random instance construction (fuzz/fuzz.py:83-196)."""
import random

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


def _reserved_parent_keys(instance: dict, schema, spec, rng) -> dict:
    """Reserve a subset of parent PKs that are never drawn as FK values."""
    reserved: dict = {}
    if not spec:
        return reserved
    unmatched = spec.get('unmatched_parents', {}) or {}
    for pt, cols in unmatched.items():
        if pt not in instance:
            continue
        tm = schema.tables.get(pt)
        if tm is None or not tm.primary_key:
            continue
        pk_col = tm.primary_key[0]
        vals = [v for v in instance[pt].get(pk_col, []) if v is not None]
        if not vals:
            continue
        k = max(1, int(round(0.03 * len(vals))))
        k = min(k, max(1, len(vals) - 1))
        reserved[pt] = set(rng.sample(vals, k))
    return reserved


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   reserved: dict = None) -> dict:
    """FK child columns draw from the parent's generated values with replacement."""
    reserved = reserved or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        skip = reserved.get(pt, set())
        pool = [v for v in pv if v is not None and v not in skip]
        if not pool:
            pool = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pool) for _ in range(n)] if pool else [None] * n
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Pick table sizes from the spec (``table_sizes``) or the upstream random sizes."""
    sizes = {}
    if spec:
        for t in schema.tables:
            v = (spec.get('table_sizes', {}) or {}).get(t)
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                lo, hi = int(v[0]), int(v[1])
            elif isinstance(v, (int, float)):
                lo = hi = int(v)
            else:
                lo = hi = 0
            sizes[t] = rng.randint(lo, hi) if hi >= lo else 0
        return sizes
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


def _apply_boundary(values, spec, rng):
    """Plant boundary values in place at the first positions (never prepend+truncate)."""
    if not spec or not values:
        return values
    out = list(values)
    for i, v in enumerate(spec):
        if i >= len(out):
            break
        out[i] = v
    return out


def _apply_duplicates(values, share, rng):
    """Make the last ``share`` share of the values duplicates of the earlier ones."""
    if not values or share <= 0:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    for i in range(n - k, n):
        values[i] = rng.choice(values[:i])
    return values


def _apply_null(values, rate, rng):
    """Plant NULL at the given rate (NULL is a value, never replaced by a rule)."""
    if not values:
        return values
    for i in range(len(values)):
        if rng.random() < rate:
            values[i] = None
    return values


def _apply_rule(values, rule, rng):
    """Apply a semantic rule to the values: values violating the rule are replaced."""
    if not rule or not values:
        return values
    kind, val = rule.get('type'), rule.get('value')
    for i, v in enumerate(values):
        if v is None:
            continue
        ok = True
        if kind == 'gt':
            ok = v > val
        elif kind == 'ge':
            ok = v >= val
        elif kind == 'lt':
            ok = v < val
        elif kind == 'le':
            ok = v <= val
        elif kind == 'eq':
            ok = v == val
        if not ok:
            if kind == 'gt':
                values[i] = val + 1
            elif kind == 'ge':
                values[i] = val
            elif kind == 'lt':
                values[i] = val - 1
            elif kind == 'le':
                values[i] = val
            else:
                values[i] = val
    return values


def _ensure_one_null(values, rng):
    """At least one NULL row per nullable column (interface rule)."""
    if values and all(v is not None for v in values):
        values[rng.randrange(len(values))] = None
    return values


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                spec_pool = None
                spec_range = None
                if spec:
                    spec_pool = (spec.get('value_pools', {}).get(t, {}) or {}).get(cm.name)
                    spec_range = (spec.get('numeric_ranges', {}).get(t, {}) or {}).get(cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                    p, rng, len(tm.primary_key), spec_pool=spec_pool, spec_range=spec_range)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    reserved: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, reserved))
        if spec:
            bv = (spec.get('boundary_values', {}).get(t, {}) or {})
            dup = (spec.get('duplicate_share', {}).get(t, {}) or {})
            nulls = (spec.get('null_targets', {}).get(t, {}) or {})
            rules = (spec.get('semantic_rules', {}).get(t, {}) or {})
            for cm in tm.columns:
                if cm.name not in cols:
                    continue
                if cm.name in dup:
                    cols[cm.name] = _apply_duplicates(cols[cm.name], dup[cm.name], rng)
                if cm.name in nulls and not cm.notnull and cm.pk_pos == 0:
                    cols[cm.name] = _apply_null(cols[cm.name], nulls[cm.name], rng)
                if cm.name in rules:
                    cols[cm.name] = _apply_rule(cols[cm.name], rules[cm.name], rng)
                if cm.name in bv:
                    cols[cm.name] = _apply_boundary(cols[cm.name], bv[cm.name], rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        if spec:
            nulls = (spec.get('null_targets', {}).get(t, {}) or {})
            for cm in tm.columns:
                if cm.name in nulls and not cm.notnull and cm.pk_pos == 0 and cm.name in cols:
                    cols[cm.name] = _ensure_one_null(cols[cm.name], rng)
        inst[t] = cols
        if spec and t in (spec.get('unmatched_parents', {}) or {}):
            reserved.update(_reserved_parent_keys({t: cols}, schema, spec, rng))
    return {t: inst[t] for t in schema.tables}
