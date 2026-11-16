"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from collections import Counter

from . import spec
from .values import (BoundaryStringSampler, EnumSampler, NumberSampler, StringSampler,
                     _init_sampler, make_column_sampler)


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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated parent values (never NULL)."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        allow_null = key in spec.NULL_TARGETS
        col = []
        for _ in range(n):
            if pv and (not allow_null or rng.random() >= spec.NULL_SHARE):
                col.append(rng.choice(pv))
            else:
                col.append(None)
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (spec.table_sizes_per_instance), with small per-instance jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 2
        jitter = rng.randint(-1, 1) if base > 2 else 0
        sizes[t] = max(0, base + jitter)
    return sizes


def _pk_start(schema, table: str, pk_col: str) -> int:
    vals = [v for v in schema.original_values.get((table, pk_col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _make_sampler(schema, table, cm, literal_pool, rng, p):
    """Specification-aware sampler factory (by construction)."""
    key = (table, cm.name)
    ov = schema.original_values.get(key, [])
    pool = literal_pool.get(key, [])
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in pool})
    t = (cm.type_str or '').lower()

    if table == 'Student' and cm.name == 'Sex':
        return EnumSampler(spec.SEX_VALUES, rng)
    if table == 'Student' and cm.name == 'Age':
        return NumberSampler(els, p, float('inf'), rng, is_int=True,
                             bounds=(spec.AGE_MIN, spec.AGE_MAX))
    if table == 'Restaurant' and cm.name == 'Rating':
        return NumberSampler(els, p, float('inf'), rng, is_int=True,
                             bounds=(spec.RATING_MIN, spec.RATING_MAX))
    if table == 'Visits_Restaurant' and cm.name == 'Spent':
        return NumberSampler(els, p, float('inf'), rng, is_int=False, precision=2,
                             bounds=(spec.SPENT_MIN, 10 ** 6))

    if table == 'Student' and cm.name == 'LName':
        return BoundaryStringSampler(els, p, float('inf'), rng, spec.LNAME_BOUNDARY, length=12)
    if table == 'Student' and cm.name == 'Fname':
        return BoundaryStringSampler(els, p, float('inf'), rng, spec.FNAME_BOUNDARY, length=12)
    if table == 'Restaurant_Type' and cm.name == 'ResTypeName':
        return BoundaryStringSampler(els, p, float('inf'), rng, spec.RESTYPE_BOUNDARY, length=40)
    if table == 'Restaurant' and cm.name == 'ResName':
        return BoundaryStringSampler(els, p, float('inf'), rng, spec.RESNAME_BOUNDARY, length=100)
    if table == 'Restaurant' and cm.name == 'Address':
        return BoundaryStringSampler(els, p, float('inf'), rng, '3233 St Paul St, Baltimore, MD 21218',
                                     length=100)
    if table == 'Student' and cm.name == 'city_code':
        return BoundaryStringSampler(els, p, float('inf'), rng, 'BAL', length=3)

    if (table, cm.name) in spec.TIE_RANK1_COLUMNS:
        return NumberSampler(els, 0.0, 3, rng, is_int=True)

    return _init_sampler(cm, pool, ov, p, rng, len(schema.tables[table].primary_key))


def _inject_nulls(cols: dict, table: str, tm, schema, n: int, rng) -> None:
    """NULL rule: plant NULLs ONLY in columns listed in spec.NULL_TARGETS."""
    if n <= 0:
        return
    for cm in tm.columns:
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if (table, cm.name) not in spec.NULL_TARGETS:
            continue
        if cm.name not in cols:
            continue
        col = cols[cm.name]
        k = max(1, int(round(n * spec.NULL_SHARE)))
        k = min(k, n)
        idxs = rng.sample(range(n), k)
        for i in idxs:
            col[i] = None


def _force_boundary_literals(cols: dict, table: str, tm, n: int, rng) -> None:
    """Guarantee the boundary literal and at least one near-variant appear in the first rows of the listed columns
    (never overwrites planted NULLs)."""
    if n < 2:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.BOUNDARY_COLUMNS or cm.name not in cols:
            continue
        boundary = spec.BOUNDARY_COLUMNS[key]
        col = cols[cm.name]
        free = [i for i, v in enumerate(col) if v is not None]
        if len(free) < 2:
            continue
        col[free[0]] = boundary
        variant = boundary.lower() if boundary != boundary.lower() else boundary.upper()
        col[free[1]] = variant


def _force_group_sizes(cols: dict, table: str, cm, n: int, rng) -> None:
    """Construct group sizes 1, 2 and >=3 for the listed columns (by construction)."""
    if n < 6 or cm.name not in cols:
        return
    if cm.pk_pos > 0:
        return
    col = cols[cm.name]
    distinct = []
    for v in col:
        if v is not None and v not in distinct:
            distinct.append(v)
        if len(distinct) >= 3:
            break
    if len(distinct) < 3:
        if table == 'Student' and cm.name == 'Sex':
            for cand in spec.SEX_VALUES:
                if cand not in distinct:
                    distinct.append(cand)
                if len(distinct) >= 3:
                    break
        else:
            base = StringSampler([v for v in col if v is not None], 0.0, float('inf'), rng, length=20)
            tries = 0
            while len(distinct) < 3 and tries < 50:
                cand = base.sample()
                if cand is not None and cand not in distinct:
                    distinct.append(cand)
                tries += 1
    if len(distinct) < 3:
        return
    a, b, c = distinct[0], distinct[1], distinct[2]
    free = [i for i, v in enumerate(col) if v is not None]
    if len(free) < 6:
        return
    col[free[0]] = a
    col[free[1]] = b
    col[free[2]] = b
    for i in free[3:]:
        col[i] = c


def _force_rank1_ties(cols: dict, table: str, cm, n: int, rng) -> None:
    """Construct ties at rank 1 for ORDER(COUNT(*), ASC/DESC) on the listed columns."""
    if n < 4 or cm.name not in cols:
        return
    col = cols[cm.name]
    distinct = []
    for v in col:
        if v is not None and v not in distinct:
            distinct.append(v)
        if len(distinct) >= 2:
            break
    if len(distinct) < 2:
        return
    free = [i for i, v in enumerate(col) if v is not None]
    if len(free) < 4:
        return
    a, b = distinct[0], distinct[1]
    col[free[0]] = a
    col[free[1]] = a
    col[free[2]] = b
    col[free[3]] = b


def _construct_unmatched_join(instance: dict, schema, table: str, cols: dict, n: int, rng) -> None:
    """For each (child_table, child_col) in spec.UNMATCHED_JOIN_TARGETS:"""
    for (ct, cc), (pt, pc) in spec.UNMATCHED_JOIN_TARGETS.items():
        if ct != table or cc not in cols:
            continue
        col = cols[cc]
        if (ct, cc) in spec.NULL_TARGETS:
            if not any(v is None for v in col) and n > 0:
                col[rng.randrange(n)] = None
        parent_vals = _parent_pool(instance, schema, pt, pc)
        if not parent_vals:
            continue
        referenced = {v for v in col if v is not None}
        unreferenced = [v for v in parent_vals if v not in referenced]
        if unreferenced:
            continue
        if len(parent_vals) < 2:
            continue
        pv = parent_vals[0]
        other = next((x for x in parent_vals if x != pv), None)
        if other is None:
            continue
        for i, v in enumerate(col):
            if v == pv:
                if (ct, cc) in spec.NULL_TARGETS and rng.random() < 0.5:
                    col[i] = None
                else:
                    col[i] = other
        if any(v == pv for v in col):
            if (ct, cc) in spec.NULL_TARGETS:
                for i, v in enumerate(col):
                    if v == pv:
                        col[i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                start = _pk_start(schema, t, cm.name)
                cols[cm.name] = list(range(start, start + n))
                continue
            s = _make_sampler(schema, t, cm, literal_pool, rng, p)
            cols[cm.name] = [s.sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        n2 = len(next(iter(cols.values()))) if cols else 0
        _inject_nulls(cols, t, tm, schema, n2, rng)
        _force_boundary_literals(cols, t, tm, n2, rng)
        for cm in tm.columns:
            if (t, cm.name) in spec.GROUP_SIZE_COLUMNS:
                _force_group_sizes(cols, t, cm, n2, rng)
            if (t, cm.name) in spec.TIE_RANK1_COLUMNS:
                _force_rank1_ties(cols, t, cm, n2, rng)
        _construct_unmatched_join(inst, schema, t, cols, n2, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def verify_instance(schema, inst: dict) -> dict:
    """Post-construction verification of the specification's structural targets."""
    checks: dict = {}
    for (t, c) in spec.TIE_RANK1_COLUMNS:
        col = inst.get(t, {}).get(c, [])
        vals = [v for v in col if v is not None]
        if len(vals) < 4:
            checks['tie_rank1_%s_%s' % (t, c)] = False
            continue
        cnt = Counter(vals)
        min_count = min(cnt.values())
        tied = [v for v, k in cnt.items() if k == min_count]
        checks['tie_rank1_%s_%s' % (t, c)] = len(tied) >= 2
        checks['tie_rank1_countcol_%s_%s' % (t, c)] = len(tied) >= 2
        share = (len(col) - len(vals)) / len(col) if col else 0.0
        checks['null_share_%s_%s' % (t, c)] = (0.05 <= share <= 0.10)
    for (t, c) in spec.GROUP_SIZE_COLUMNS:
        col = inst.get(t, {}).get(c, [])
        vals = [v for v in col if v is not None]
        cnt = Counter(vals)
        sizes = set(cnt.values())
        checks['group_sizes_%s_%s' % (t, c)] = (1 in sizes and 2 in sizes and any(s >= 3 for s in sizes))
    for (t, c) in spec.DISTINCT_COLUMNS:
        col = inst.get(t, {}).get(c, [])
        vals = [v for v in col if v is not None]
        if len(vals) < 2:
            checks['dup_share_%s_%s' % (t, c)] = False
            continue
        cnt = Counter(vals)
        dup = sum(k - 1 for k in cnt.values() if k > 1)
        share = dup / len(vals)
        checks['dup_share_%s_%s' % (t, c)] = (0.20 <= share <= 0.50)
    for (t, c), boundary in spec.BOUNDARY_COLUMNS.items():
        col = inst.get(t, {}).get(c, [])
        vals = [v for v in col if v is not None]
        checks['boundary_%s_%s' % (t, c)] = (boundary in vals)
    for (ct, cc), (pt, pc) in spec.UNMATCHED_JOIN_TARGETS.items():
        child_col = inst.get(ct, {}).get(cc, [])
        parent_col = inst.get(pt, {}).get(pc, [])
        referenced = {v for v in child_col if v is not None}
        parent_vals = [v for v in parent_col if v is not None]
        has_unreferenced = any(v not in referenced for v in parent_vals)
        checks['unmatched_parent_%s_%s' % (ct, cc)] = has_unreferenced
        if (ct, cc) in spec.NULL_TARGETS:
            checks['unmatched_null_fk_%s_%s' % (ct, cc)] = any(v is None for v in child_col)
    return checks
