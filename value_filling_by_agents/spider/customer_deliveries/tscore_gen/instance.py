"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt
from collections import Counter

from .spec import (formula_for, has_pattern, is_null_target, parse_ts, fmt_ts)


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


def _merged_fks(schema, spec) -> dict:
    """schema.fks plus spec['dependencies'] (spec wins on conflict)."""
    fks = dict(schema.fks)
    for child, parent in (spec or {}).get('dependencies', {}).items():
        if child in schema.tables and parent[0] in schema.tables:
            fks[child] = parent
    return fks


def _reserved_parent_keys(schema, spec, fks) -> dict:
    """For each targeted parent column, reserve one parent key that is never sampled as a child FK (so the parent has
    at least one childless row)."""
    reserved = {}
    for (ct, cc), (pt, pc) in fks.items():
        if not has_pattern(spec, ct, cc, 'unmatched_join_rows'):
            continue
        compact = schema.original_values.get((pt, pc)) or []
        if compact:
            reserved.setdefault((pt, pc), set()).add(compact[0])
    return reserved


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec=None,
                                   reserved=None) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    fks = _merged_fks(schema, spec)
    reserved = reserved or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in fks:
            continue
        pt, pc = fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        compact = schema.original_values.get((pt, pc)) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        res = reserved.get((pt, pc), set())
        candidates = [v for v in pv if v not in res]
        if not candidates:
            candidates = list(pv)
        vals = []
        for _ in range(n):
            if compact and rng.random() < 0.25:
                c = [v for v in compact if v not in res]
                vals.append(rng.choice(c) if c else rng.choice(candidates))
            else:
                vals.append(rng.choice(candidates))
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specification sizes are exact per-instance row counts (spec: 'must not vary them')."""
    sizes = {}
    base = (spec or {}).get('sizes') or {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = int(base.get(t, 15))
    return sizes


def _plant_group_sizes(values: list, rng, compact_values=None) -> list:
    """Ensure at least one group of size 1, one of size 2 and one of size >= 3."""
    n = len(values)
    if n < 6:
        return values
    pool = sorted({v for v in values if v is not None}, key=lambda x: str(x))
    if len(pool) < 3:
        return values
    for _ in range(8):
        a, b, c = rng.sample(pool, 3)
        out = list(values)
        out[0] = a
        out[1] = b
        out[2] = b
        for i in range(3, min(n, 6)):
            out[i] = c
        cnt = Counter(v for v in out if v is not None)
        if compact_values:
            cnt.update(v for v in compact_values if v is not None)
        sizes = set(cnt.values())
        if 1 in sizes and 2 in sizes and any(s >= 3 for s in sizes):
            return out
    return out


def _plant_duplicate_share(values: list, rng, compact_values=None) -> list:
    """20-50% of rows share a value with another row (target count computed from n)."""
    n = len(values)
    if n < 4:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    out = list(values)
    target = max(2, int(round(n * rng.uniform(0.2, 0.5))))
    target = min(target, n)
    src = rng.choice(pool)
    idx = rng.sample(range(n), target)
    for i in idx:
        out[i] = src
    return out


def _plant_rows_with_different_values(values: list, rng) -> list:
    """At least two distinct non-NULL values per qualifying group (>= 2 rows)."""
    n = len(values)
    if n < 2:
        return values
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    out = list(values)
    if len(nums) >= 2 and len(set(nums)) >= 2:
        return out
    if nums:
        lo = min(nums)
        hi = max(nums)
        if lo == hi:
            hi = lo + 1
    else:
        lo, hi = 0.01, 9999.99
    slots = [i for i, v in enumerate(out) if v is not None][:2]
    if len(slots) == 2:
        out[slots[0]] = lo
        out[slots[1]] = hi
    return out


def _apply_null_rule(values: list, nullable: bool, compact_share: float, rng) -> list:
    """NULL is a value to generate: >= 1 NULL row and a share following the compact share."""
    if not nullable:
        return [v for v in values if v is not None]
    n = len(values)
    if n == 0:
        return values
    share = compact_share if compact_share > 0 else 0.2
    k = max(1, int(round(n * share)))
    k = min(k, n)
    out = list(values)
    idx = rng.sample(range(n), k)
    for i in idx:
        out[i] = None
    return out


def _compact_null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column)) or []
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _fix_formula(table: str, column: str, row: dict, spec, rng) -> bool:
    """Apply the column's formula to the in-memory row; returns True if it holds (or is NULL)."""
    f = formula_for(spec, table, column)
    if f is None:
        return True
    try:
        return bool(f(row, None))
    except Exception:
        return True


def _repair_row(table: str, row: dict, spec, rng) -> bool:
    """Try to satisfy formulas by re-drawing the offending column (never replaces a planted NULL)."""
    for cm_name, v in list(row.items()):
        if v is None:
            continue
        if not _fix_formula(table, cm_name, row, spec, rng):
            return False
    return True


def _resync_foreign_keys(inst: dict, schema, spec) -> None:
    """Re-resolve every FK child value against the FINAL parent key set."""
    fks = _merged_fks(schema, spec)
    for (ct, cc), (pt, pc) in fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        child = inst[ct][cc]
        parent_gen = inst.get(pt, {}).get(pc) or []
        parent_compact = schema.original_values.get((pt, pc)) or []
        final = set(parent_gen) | set(parent_compact)
        final.discard(None)
        if not final:
            continue
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        nullable = cm is not None and (not cm.notnull) and cm.pk_pos == 0
        final_list = sorted(final, key=lambda x: str(x))
        for i, v in enumerate(child):
            if v is None:
                if not nullable:
                    child[i] = final_list[0]
                continue
            if v not in final:
                child[i] = final_list[0]


def _resample_until_exact(table: str, tm, cols: dict, samplers: dict, n: int, rng, spec) -> dict:
    """Resample rows that would be dropped by PK/unique filtering so the final count is n."""
    if not tm.primary_key and not any(c.unique for c in tm.columns):
        return cols
    names = [c.name for c in tm.columns]
    pk = list(tm.primary_key)
    uniq = [c.name for c in tm.columns if c.unique]
    seen_pk = set()
    seen_uniq = {c: set() for c in uniq}
    keep = []
    for i in range(n):
        for _ in range(64):
            row = {c: cols[c][i] for c in names}
            k = tuple(row[c] for c in pk) if pk else None
            ok = True
            if k is not None and k in seen_pk:
                ok = False
            for c in uniq:
                if row[c] in seen_uniq[c]:
                    ok = False
                    break
            if ok:
                if k is not None:
                    seen_pk.add(k)
                for c in uniq:
                    seen_uniq[c].add(row[c])
                keep.append(i)
                break
            for c in pk + uniq:
                if (table, c) in samplers:
                    cols[c][i] = samplers[(table, c)].sample()
        else:
            keep.append(i)
    return _filter(cols, keep)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    from .values import _init_sampler
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    fks = _merged_fks(schema, spec)
    reserved = _reserved_parent_keys(schema, spec, fks)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec=spec, table=t)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec, reserved))
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            if is_null_target(spec, t, cm.name) and nullable:
                nullable = True
            if (t, cm.name) in fks and not nullable:
                cols[cm.name] = [v for v in cols[cm.name] if v is not None]
                continue
            cols[cm.name] = _apply_null_rule(cols[cm.name], nullable,
                                             _compact_null_share(schema, t, cm.name), rng)
        for cm in tm.columns:
            if (t, cm.name) in fks or cm.name not in cols:
                continue
            compact = schema.original_values.get((t, cm.name), [])
            if has_pattern(spec, t, cm.name, 'group_sizes'):
                cols[cm.name] = _plant_group_sizes(cols[cm.name], rng, compact)
            if has_pattern(spec, t, cm.name, 'duplicates_for_distinct'):
                cols[cm.name] = _plant_duplicate_share(cols[cm.name], rng, compact)
            if has_pattern(spec, t, cm.name, 'rows_with_different_values'):
                cols[cm.name] = _plant_rows_with_different_values(cols[cm.name], rng)
        cols = _resample_until_exact(t, tm, cols, samplers, n, rng, spec)
        inst[t] = cols
    _resync_foreign_keys(inst, schema, spec)
    for t in order:
        tm = schema.tables[t]
        cols = inst.get(t, {})
        if not cols:
            continue
        names = [c.name for c in tm.columns]
        n = len(cols.get(names[0], [])) if names else 0
        for i in range(n):
            for _ in range(8):
                row = {c: cols[c][i] for c in names}
                if _repair_row(t, row, spec, rng):
                    break
                for c in names:
                    if (t, c) in samplers and row.get(c) is not None:
                        cols[c][i] = samplers[(t, c)].sample()
    return {t: inst[t] for t in schema.tables}


def verify_instance(schema, inst: dict, spec: dict) -> dict:
    """Post-generation verification of the specification targets (reported, never silent)."""
    out = {'sizes': {}, 'group_sizes': {}, 'duplicates_for_distinct': {},
           'unmatched_join_rows': {}, 'rows_with_different_values': {}, 'comparison_boundary': {}}
    for t, tm in schema.tables.items():
        cols = inst.get(t, {})
        names = [c.name for c in tm.columns]
        n = len(cols.get(names[0], [])) if names else 0
        target = int((spec.get('sizes') or {}).get(t, n))
        out['sizes'][t] = {'target': target, 'actual': n, 'ok': n == target}
        for cm in tm.columns:
            vals = cols.get(cm.name, [])
            compact = schema.original_values.get((t, cm.name), [])
            allv = list(compact) + list(vals)
            if has_pattern(spec, t, cm.name, 'group_sizes'):
                cnt = Counter(v for v in allv if v is not None)
                sizes = set(cnt.values())
                out['group_sizes']['%s.%s' % (t, cm.name)] = {
                    'ok': 1 in sizes and 2 in sizes and any(s >= 3 for s in sizes),
                    'sizes': sorted(sizes)}
            if has_pattern(spec, t, cm.name, 'duplicates_for_distinct'):
                cnt = Counter(v for v in allv if v is not None)
                dup = sum(c for c in cnt.values() if c > 1)
                share = dup / float(len(allv)) if allv else 0.0
                out['duplicates_for_distinct']['%s.%s' % (t, cm.name)] = {
                    'ok': 0.2 <= share <= 0.5, 'share': round(share, 3)}
            if has_pattern(spec, t, cm.name, 'rows_with_different_values'):
                distinct = len({v for v in allv if v is not None})
                out['rows_with_different_values']['%s.%s' % (t, cm.name)] = {
                    'ok': distinct >= 2, 'distinct': distinct}
            if has_pattern(spec, t, cm.name, 'comparison_boundary'):
                bnd = spec.get('boundary', {}).get((t, cm.name)) or []
                present = {v for v in allv if v in bnd}
                out['comparison_boundary']['%s.%s' % (t, cm.name)] = {
                    'ok': len(present) >= 2, 'present': sorted(map(str, present))}
    fks = _merged_fks(schema, spec)
    for (ct, cc), (pt, pc) in fks.items():
        if not has_pattern(spec, ct, cc, 'unmatched_join_rows'):
            continue
        child = inst.get(ct, {}).get(cc) or []
        parent = set(inst.get(pt, {}).get(pc) or []) | set(schema.original_values.get((pt, pc)) or [])
        parent.discard(None)
        childset = {v for v in child if v is not None}
        childless = parent - childset
        out['unmatched_join_rows']['%s.%s' % (ct, cc)] = {
            'ok': bool(childless) and all(v in parent for v in childset),
            'childless_parents': len(childless)}
    return out
