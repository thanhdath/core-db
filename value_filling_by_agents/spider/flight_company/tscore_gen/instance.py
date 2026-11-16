"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact database."""
import math

from .spec import (DEFAULT_NULL_SHARE, NEAR_VARIANT_PROB, DISTINCT_DUP_SHARE, GROUP_SIZES,
                   AGG_BOUNDARY, AGG_BOUNDARY_GT2)
from .values import _init_sampler, near_variants


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


def _null_share(schema, spec, key) -> float:
    """NULL share for a nullable column: compact share, at least one NULL row, spec default."""
    if key in spec.get('null_share', {}):
        base = spec['null_share'][key]
    else:
        base = DEFAULT_NULL_SHARE
    ov = schema.original_values.get(key) or []
    if ov:
        obs = sum(1 for v in ov if v is None) / len(ov)
        base = max(base, obs)
    return min(base, 0.5)


def _plant_nulls(values: list, share: float, rng) -> list:
    """Set a share of positions to NULL, guaranteeing at least one NULL AND at least one non-NULL."""
    n = len(values)
    if n == 0:
        return values
    if n == 1:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n - 1)
    rng_ = rng
    idx = rng_.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def _plant_group_and_agg_jointly(values: list, group_sizes: tuple, boundary: tuple, rng) -> list:
    """Plant groups of size 1, 2, >=3 AND counts straddling the HAVING threshold simultaneously."""
    n = len(values)
    if n < 6:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    candidates = list({v for v in pool})
    rng.shuffle(candidates)
    base1 = candidates[0]
    base2 = candidates[1] if len(candidates) > 1 else base1
    base3 = candidates[2] if len(candidates) > 2 else base1
    pos = list(range(n))
    rng.shuffle(pos)
    cur = 0
    plan = [(base1, 1), (base2, 2), (base3, 3)]
    for base, sz in plan:
        for _ in range(sz):
            if cur < n:
                values[pos[cur]] = base
                cur += 1
    return values


def _plant_group_sizes(values: list, rng) -> list:
    """Ensure groups of size 1, 2 and >= 3 among the values (group_sizes rule)."""
    return _plant_group_and_agg_jointly(values, GROUP_SIZES, AGG_BOUNDARY, rng)


def _plant_agg_boundary(values: list, boundary: tuple, rng) -> list:
    """Ensure counts straddle the HAVING threshold (e.g. 0,1,2 for >1; 1,2,3 for >2)."""
    return _plant_group_and_agg_jointly(values, GROUP_SIZES, boundary, rng)


def _plant_distinct_dups(values: list, rng) -> list:
    """Ensure a 20-50% duplicate share for DISTINCT-target columns."""
    n = len(values)
    if n < 4:
        return values
    share = rng.uniform(*DISTINCT_DUP_SHARE)
    k = max(1, int(round(share * n)))
    pos = list(range(n))
    rng.shuffle(pos)
    for j in range(1, k):
        values[pos[j]] = values[pos[0]]
    return values


def _apply_range(values: list, lo, hi, rng) -> list:
    """Clamp non-NULL numeric values into [lo, hi] (semantic range rule)."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if lo is not None and v < lo:
            v = lo
        if hi is not None and v > hi:
            v = hi
        out.append(v)
    return out


def _apply_length(values: list, length: int, rng) -> list:
    """Force non-NULL strings to a fixed length (semantic length rule)."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        s = str(v)
        if len(s) < length:
            s = s + ''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(length - len(s)))
        out.append(s[:length])
    return out


def _apply_enum(values: list, enum: list, rng) -> list:
    """Force non-NULL values into an enumeration (semantic IN rule)."""
    return [None if v is None else (v if v in enum else rng.choice(enum)) for v in values]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec) -> dict:
    """FK child columns draw from the parent's compact + generated values; NULL per the NULL rule."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc)) or [])
        pv += [v for v in (instance.get(pt, {}).get(pc) or []) if v is not None]
        pv = [v for v in pv if v is not None]
        if pv:
            vals = [rng.choice(pv) for _ in range(n)]
        else:
            vals = [None] * n
        nullable = (not cm.notnull) and cm.pk_pos == 0
        if nullable and n >= 1:
            share = _null_share(schema, spec, key)
            vals = _plant_nulls(vals, share, rng)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec) -> dict:
    """Specification sizes with per-instance jitter; fallback to upstream rand_lin / level sizes."""
    sizes = {}
    fixed = spec.get('table_sizes') or {}
    if fixed:
        for lvl in schema.table_order:
            for t in lvl:
                base = int(fixed.get(t, 0))
                jitter = rng.randint(-max(1, base // 4), max(1, base // 4)) if base else 0
                sizes[t] = max(0, base + jitter)
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


def _next_pk_start(schema, table: str, pk_col: str) -> int:
    """First integer PK value after the compact rows (fresh against compact rows)."""
    ov = [v for v in (schema.original_values.get((table, pk_col)) or []) if isinstance(v, int)]
    return (max(ov) + 1) if ov else 1


def _reserve_unmatched_parents(schema, inst: dict, rng, spec) -> None:
    """Ensure for each parent table that at least one parent id (compact or generated) has no child."""
    parent_refs: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        parent_refs.setdefault(pt, []).append((ct, cc, pc))
    for pt, refs in parent_refs.items():
        pvals = [v for v in (schema.original_values.get((pt, refs[0][2])) or []) if v is not None]
        pvals += [v for v in (inst.get(pt, {}).get(refs[0][2]) or []) if v is not None]
        pvals = list(dict.fromkeys(pvals))
        if len(pvals) < 2:
            continue
        for ct, cc, _pc in refs:
            col = inst.get(ct, {}).get(cc)
            if col is None:
                continue
            used = set(v for v in col if v is not None)
            unused = [v for v in pvals if v not in used]
            if unused:
                continue
            target = repo_pick = None
            for v in col:
                if v is not None:
                    target = v
                    break
            if target is not None:
                replacement = rng.choice(pvals)
                if replacement == target:
                    replacement = pvals[(pvals.index(target) + 1) % len(pvals)]
                for j, v in enumerate(col):
                    if v == target:
                        col[j] = replacement
                        break


def _apply_semantic_rules(inst: dict, schema, table: str, cols: dict, spec, rng) -> None:
    """Apply ranges/lengths/enums to non-FK columns (FK columns are never clamped)."""
    for k, (lo, hi) in spec.get('ranges', {}).items():
        if k[0] == table and k[1] in cols and k not in schema.fks and (lo is not None or hi is not None):
            cols[k[1]] = _apply_range(cols[k[1]], lo, hi, rng)
    for k, ln in spec.get('lengths', {}).items():
        if k[0] == table and k[1] in cols and k not in schema.fks:
            cols[k[1]] = _apply_length(cols[k[1]], ln, rng)
    for k, en in spec.get('enums', {}).items():
        if k[0] == table and k[1] in cols:
            if k in schema.fks:
                continue
            cols[k[1]] = _apply_enum(cols[k[1]], en, rng)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) appended to the compact rows."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            k = (t, cm.name)
            samplers[k] = _init_sampler(
                cm, literal_pool.get(k, []), schema.original_values.get(k, []), p, rng,
                len(tm.primary_key),
                fixed_len=spec.get('lengths', {}).get(k),
                near_prob=NEAR_VARIANT_PROB,
                lo=(spec.get('ranges', {}).get(k) or (None, None))[0],
                hi=(spec.get('ranges', {}).get(k) or (None, None))[1],
                enum=spec.get('enums', {}).get(k))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols and all(isinstance(v, int) for v in cols[pk] if v is not None):
                start = _next_pk_start(schema, t, pk)
                cols[pk] = [start + i for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        _apply_semantic_rules(inst, schema, t, cols, spec, rng)
        for cm in tm.columns:
            k = (t, cm.name)
            if cm.notnull or cm.pk_pos > 0 or k in schema.fks:
                continue
            if cm.name in cols:
                cols[cm.name] = _plant_nulls(cols[cm.name], _null_share(schema, spec, k), rng)
        for cm in tm.columns:
            k = (t, cm.name)
            if cm.name not in cols:
                continue
            is_group = k in spec.get('group_targets', set())
            is_agg = k in spec.get('agg_targets', {})
            if is_group and is_agg:
                cols[cm.name] = _plant_group_and_agg_jointly(
                    cols[cm.name], GROUP_SIZES, spec['agg_targets'][k], rng)
            elif is_group:
                cols[cm.name] = _plant_group_sizes(cols[cm.name], rng)
            elif is_agg:
                cols[cm.name] = _plant_agg_boundary(cols[cm.name], spec['agg_targets'][k], rng)
            if k in spec.get('distinct_targets', set()):
                cols[cm.name] = _plant_distinct_dups(cols[cm.name], rng)
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
    _reserve_unmatched_parents(schema, inst, rng, spec)
    return {t: inst[t] for t in schema.tables}
