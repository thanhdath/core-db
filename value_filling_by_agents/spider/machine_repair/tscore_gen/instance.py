"""Random instance construction (fuzz/fuzz.py:83-196), spec-driven."""
import random

from .schema import max_single_int_pk
from .values import make_column_sampler


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


def choose_table_sizes(schema, rng, spec) -> dict:
    """Spec sizes win; otherwise the library choice (fuzz.py:83-110)."""
    fixed = (spec or {}).get('table_sizes') or {}
    if fixed:
        return {t: int(fixed.get(t, fixed.get(t.lower(), 0))) for t in schema.tables}
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


def _spec_lookup(spec: dict, group: str, key: str):
    """Case/qualifier-tolerant lookup in ONE spec dict keyed by 'table.col'."""
    if not spec:
        return None
    blk = spec.get(group) or {}
    if not isinstance(blk, dict):
        return None
    if key in blk:
        return blk[key]
    low = key.lower()
    for k, v in blk.items():
        if k.lower() == low:
            return v
        kt, kc = (k.split('.', 1) + [''])[:2]
        tt, tc = (key.split('.', 1) + [''])[:2]
        if kc.lower() == tc.lower() and kt.lower() == tt.lower():
            return v
    return None


def _is_target(spec: dict, group: str, key: str) -> bool:
    for k in (spec or {}).get(group) or []:
        kt, kc = (k.split('.', 1) + [''])[:2]
        tt, tc = (key.split('.', 1) + [''])[:2]
        if kc.lower() == tc.lower() and (not kt or kt.lower() == tt.lower()):
            return True
    return False


def _range_for(spec, table, cm):
    rng_spec = (spec or {}).get('ranges') or {}
    for k, v in rng_spec.items():
        kt, kc = (k.split('.', 1) + [''])[:2]
        if kc.lower() == cm.name.lower() and (not kt or kt.lower() == table.lower()):
            if isinstance(v, list) and len(v) >= 2 and v[0] is not None and v[1] is not None:
                return v[0], v[1]
            break
    return None, None


def _make_sampler(schema, pool, spec, table, cm, rng, p):
    key = table + '.' + cm.name
    lo, hi = _range_for(spec, table, cm)
    forced = []
    bv = _spec_lookup(spec, 'boundary_values', key)
    if isinstance(bv, list) and _is_target(spec, 'boundary_values', key):
        forced.extend(bv)
    lp = _spec_lookup(spec, 'literal_pool', key)
    if isinstance(lp, list):
        forced.extend(lp)
    ov = schema.original_values.get((table, cm.name), [])
    pool_vals = [str(v) for v in (pool.get((table, cm.name)) or [])]
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted(set(pool_vals))
    return make_column_sampler(cm, els, p, float('inf'), rng, lo=lo, hi=hi, forced=forced)


def _inject_nulls(values, share, rng, n_at_least=1):
    """Set a share of positions to None (at least one) - NULL is a generated value."""
    n = len(values)
    if n == 0:
        return values
    k = max(n_at_least, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def _force_duplicates(values, rng):
    """Ensure ~20-50% of the values repeat another row's value (best effort)."""
    n = len(values)
    if n < 2:
        return values
    nonnull = [i for i, v in enumerate(values) if v is not None]
    if len(nonnull) < 2:
        return values
    k = max(1, int(round(n * rng.uniform(0.2, 0.5))))
    k = min(k, len(nonnull) - 1)
    targets = rng.sample(nonnull[1:], k)
    for i in targets:
        src = rng.choice([j for j in nonnull if j != i])
        values[i] = values[src]
    return values


def _shape_group_sizes(values, rng, n):
    """Make group sizes 1, 2 and >=3 concrete when n >= 6 (best effort)."""
    if n < 6:
        return values
    seen = {}
    for v in values:
        seen[v] = seen.get(v, 0) + 1
    have = sorted(set(seen.values()))
    if 1 in have and 2 in have and any(x >= 3 for x in have):
        return values
    base = [v for v in values if v is not None]
    if len(base) < 6:
        return values
    a, b = base[0], base[1]
    c = base[2] if base[2] != a else base[3]
    for i in range(len(values)):
        if i < 3:
            values[i] = a
        elif i < 5:
            values[i] = b
        elif i < 6:
            values[i] = c
    return values


def _scatter(forced, values, rng):
    """Place the forced values into the first positions that are not NULL."""
    if not forced:
        return values
    slots = [i for i, v in enumerate(values) if v is not None]
    for k, f in enumerate(forced):
        if k < len(slots):
            values[slots[k]] = f
    return values


def _cast_fk(value, child_type: str):
    """Cast a parent PK value to the child FK column's declared type."""
    if value is None:
        return None
    t = (child_type or '').lower()
    if 'int' in t and 'real' not in t and 'float' not in t:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return value
    if 'real' in t or 'float' in t or 'double' in t:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def build_random_instance(schema, literal_pool: dict, spec, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) that is appended to a compact copy."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    null_targets = {k.lower(): v for k, v in (spec.get('null_targets') or {}).items()}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            s = _make_sampler(schema, literal_pool, spec, t, cm, rng, p)
            vals = [s.sample() for _ in range(n)]
            if not cm.notnull and cm.pk_pos == 0:
                lkey = (t + '.' + cm.name).lower()
                band = null_targets.get(lkey)
                if isinstance(band, list) and len(band) >= 2:
                    share = rng.uniform(band[0], band[1])
                else:
                    share = rng.uniform(0.05, 0.10)
                vals = _inject_nulls(vals, share, rng, 1)
            cols[cm.name] = vals
        for i, pkcol in enumerate(tm.primary_key):
            cm = next(c for c in tm.columns if c.name == pkcol)
            if len(tm.primary_key) == 1 and cm.pk_pos == 1:
                start = max_single_int_pk(schema, t) + 1
                if cm.name in cols and ('int' in (cm.type_str or '').lower() or 'real' in (cm.type_str or '').lower()):
                    is_real = 'real' in (cm.type_str or '').lower() and 'int' not in (cm.type_str or '').lower()
                    cols[cm.name] = [(float(start + i) if is_real else start + i) for i in range(n)]
        for cm in tm.columns:
            key = t + '.' + cm.name
            forced = []
            bv = _spec_lookup(spec, 'boundary_values', key)
            if isinstance(bv, list) and _is_target(spec, 'boundary_values', key):
                forced.extend(bv)
            lp = _spec_lookup(spec, 'literal_pool', key)
            if isinstance(lp, list):
                forced.extend(lp)
            if forced and cm.name in cols and cm.name not in tm.primary_key:
                cols[cm.name] = _scatter(forced, cols[cm.name], rng)
        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = list(schema.original_values.get((pt, pc), [])) + list(inst.get(pt, {}).get(pc) or [])
            pv = [_cast_fk(v, cm.type_str) for v in pv if v is not None]
            cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            key = t + '.' + cm.name
            if cm.name not in cols or cm.name in tm.primary_key:
                continue
            if _is_target(spec, 'duplicate_targets', key):
                cols[cm.name] = _force_duplicates(cols[cm.name], rng)
            if _is_target(spec, 'group_sizes_targets', key):
                cols[cm.name] = _shape_group_sizes(cols[cm.name], rng, len(cols[cm.name]))
            if _is_target(spec, 'tie_targets', key) and len(cols[cm.name]) >= 2:
                nn = [i for i, v in enumerate(cols[cm.name]) if v is not None]
                if len(nn) >= 2:
                    cols[cm.name][nn[1]] = cols[cm.name][nn[0]]
        inst[t] = cols
    return {t: inst.get(t, {}) for t in schema.tables}
