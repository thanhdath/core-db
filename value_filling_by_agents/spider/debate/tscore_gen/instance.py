"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
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


def _reserve_unmatched(parent_keys: list, rng, share: float = 0.3) -> set:
    """Reserve a share of parent keys that are never drawn as FK values."""
    if not parent_keys:
        return set()
    k = max(1, int(round(len(parent_keys) * share)))
    k = min(k, len(parent_keys) - 1) if len(parent_keys) > 1 else 0
    if k <= 0:
        return set()
    return set(rng.sample(list(parent_keys), k))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_max: dict, reserved: dict) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        compact_pv = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        res = reserved.get((pt, pc), set())
        gen_pool = [v for v in pv if v not in res]
        used = set()
        for (ct, cc), (ppt, ppc) in schema.fks.items():
            if (ppt, ppc) == (pt, pc) and ct != table:
                used |= {v for v in schema.original_values.get((ct, cc), []) if v is not None}
        compact_unmatched = [v for v in compact_pv if v not in used]
        pool = list(gen_pool) + list(compact_pv)
        if not pool:
            out[cm.name] = [None] * n
            continue
        vals = []
        for _ in range(n):
            if compact_unmatched and rng.random() < 0.4:
                vals.append(rng.choice(compact_unmatched))
            else:
                vals.append(rng.choice(pool))
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table_sizes_per_instance, with a small per-instance jitter (0-230 rows)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = rng.randint(0, 230)
        else:
            base = max(0, base + rng.randint(-2, 2))
        sizes[t] = base
    return sizes


def _fresh_pk_values(table_meta, n: int, rng, compact_max: dict) -> list:
    """Sequential integers starting after the compact maximum (never NULL, unique)."""
    if not table_meta.primary_key or len(table_meta.primary_key) != 1:
        return [None] * n
    pk = table_meta.primary_key[0]
    start = int(compact_max.get(pk, 0)) + 1
    return list(range(start, start + n))


def _apply_group_plan(values: list, plan: list, rng) -> list:
    """Re-shape a value list so that group sizes 1, 2 and >= 3 occur (group_sizes target)."""
    if not values:
        return values
    out = []
    for g in plan:
        v = rng.choice(values)
        out.extend([v] * g)
    return out[:len(values)] if len(out) >= len(values) else out + [rng.choice(values)] * (len(values) - len(out))


def _apply_joint_plan(values: list, share: tuple, rng) -> list:
    """Build a group-size plan first, then assign values so the duplicate share lies in `share`."""
    n = len(values)
    if n < 2:
        return values
    plan = spec.joint_plan(n, share, rng)
    out = []
    for g in plan:
        v = rng.choice(values)
        out.extend([v] * g)
    return out[:n] if len(out) >= n else out + [rng.choice(values)] * (n - len(out))


def _apply_boundary(values: list, boundary: list, rng) -> list:
    """Guarantee every boundary value appears at least once (comparison_boundary)."""
    n = len(values)
    if n <= 0 or not boundary:
        return values
    out = spec.boundary_plan(n, boundary, rng)
    return out


def _column_kwargs(table: str, column: str, rng) -> dict:
    """Per-column specification exceptions routed to the samplers."""
    kw: dict = {}
    if (table, column) == ('people', 'Age'):
        kw['lo'], kw['hi'] = spec.AGE_SEMANTIC_RANGE
        kw['boundary'] = spec.AGE_BOUNDARY_VALUES
    elif (table, column) == ('debate', 'Num_of_Audience'):
        kw['lo'], kw['hi'] = 0, spec.INT_QUANTITY_RANGE[1]
        kw['boundary'] = spec.AUDIENCE_BOUNDARY_VALUES
    elif (table, column) == ('people', 'Party'):
        kw['enum'] = spec.PARTY_ENUM
    elif (table, column) == ('people', 'Name'):
        kw['near_dup_share'] = rng.uniform(*spec.NAME_DUPLICATE_SHARE) / 2.0
    return kw


def _check_duplicate_share(values: list, share: tuple) -> dict:
    n = len(values)
    if n == 0:
        return {'n': 0, 'share': 0.0, 'ok': True}
    distinct = len(set(values))
    s = (n - distinct) / float(n)
    return {'n': n, 'share': round(s, 4), 'ok': share[0] <= s <= share[1]}


def _check_group_sizes(values: list) -> dict:
    from collections import Counter
    c = Counter(values)
    sizes = sorted(c.values())
    has1 = 1 in sizes
    has2 = 2 in sizes
    has3 = any(x >= 3 for x in sizes)
    return {'sizes': sizes, 'has_1': has1, 'has_2': has2, 'has_ge3': has3,
            'ok': has1 and has2 and has3}


def _check_boundary(values: list, boundary: list) -> dict:
    present = [b for b in boundary if b in values]
    return {'present': present, 'ok': len(present) == len(boundary)}


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                kw = _column_kwargs(t, cm.name, rng)
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), **kw)
    if size is None:
        size = choose_table_sizes(schema, rng)
    compact_max: dict = {}
    for t, tm in schema.tables.items():
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            vals = [v for v in schema.original_values.get((t, pk), []) if isinstance(v, int)]
            compact_max[pk] = max(vals) if vals else 0
    inst: dict = {}
    reserved: dict = {}
    checks: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                cols[pk] = _fresh_pk_values(tm, n, rng, compact_max)
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_max, reserved))
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                reserved[(t, pk)] = _reserve_unmatched(cols[pk], rng)
        if t == 'people' and 'Name' in cols:
            cols['Name'] = _apply_joint_plan(cols['Name'], spec.NAME_DUPLICATE_SHARE, rng)
            checks[('people', 'Name', 'duplicates')] = _check_duplicate_share(cols['Name'], spec.NAME_DUPLICATE_SHARE)
            checks[('people', 'Name', 'groups')] = _check_group_sizes(cols['Name'])
        if t == 'people' and 'Party' in cols:
            cols['Party'] = _apply_joint_plan(cols['Party'], spec.PARTY_DUPLICATE_SHARE, rng)
            checks[('people', 'Party', 'duplicates')] = _check_duplicate_share(cols['Party'], spec.PARTY_DUPLICATE_SHARE)
            checks[('people', 'Party', 'groups')] = _check_group_sizes(cols['Party'])
        if t == 'people' and 'Age' in cols:
            cols['Age'] = _apply_boundary(cols['Age'], spec.AGE_BOUNDARY_VALUES, rng)
            checks[('people', 'Age', 'boundary')] = _check_boundary(cols['Age'], spec.AGE_BOUNDARY_VALUES)
            checks[('people', 'Age', 'groups')] = _check_group_sizes(cols['Age'])
        if t == 'debate' and 'Num_of_Audience' in cols:
            cols['Num_of_Audience'] = _apply_boundary(cols['Num_of_Audience'], spec.AUDIENCE_BOUNDARY_VALUES, rng)
            checks[('debate', 'Num_of_Audience', 'boundary')] = _check_boundary(
                cols['Num_of_Audience'], spec.AUDIENCE_BOUNDARY_VALUES)
        if t == 'debate_people' and 'Negative' in cols:
            cols['Negative'] = _apply_group_plan(cols['Negative'], spec.group_size_plan(n, rng), rng)
            checks[('debate_people', 'Negative', 'groups')] = _check_group_sizes(cols['Negative'])
        if t == 'debate_people' and 'Affirmative' in cols and 'Negative' in cols:
            aff = cols['Affirmative']
            neg = cols['Negative']
            for i in range(len(aff)):
                if aff[i] is not None and aff[i] == neg[i]:
                    pt, pc = schema.fks.get((t, 'Negative'), (None, None))
                    pool = [v for v in (inst.get(pt, {}).get(pc) or []) if v is not None and v != aff[i]]
                    if pool:
                        neg[i] = rng.choice(pool)
                    else:
                        pt2, pc2 = schema.fks.get((t, 'Affirmative'), (None, None))
                        pool2 = [v for v in (inst.get(pt2, {}).get(pc2) or []) if v is not None and v != neg[i]]
                        if pool2:
                            aff[i] = rng.choice(pool2)
            checks[('debate_people', 'Affirmative<>Negative', 'rule')] = {
                'ok': all(a is None or n_ is None or a != n_ for a, n_ in zip(aff, neg))}
        if t == 'debate_people' and 'If_Affirmative_Win' in cols:
            cols['If_Affirmative_Win'] = [rng.choice([0, 1]) for _ in range(n)]
            checks[('debate_people', 'If_Affirmative_Win', 'rule')] = {
                'ok': all(v in (0, 1) for v in cols['If_Affirmative_Win'])}
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
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if not spec.null_target(t, cm.name):
                continue
            if not spec.is_nullable(t, cm.name, cm):
                continue
            col = inst.get(t, {}).get(cm.name)
            if col and all(v is not None for v in col):
                col[rng.randrange(len(col))] = None
    for (ct, cc), (pt, pc) in schema.fks.items():
        parent_keys = set(inst.get(pt, {}).get(pc) or [])
        child_vals = set(v for v in (inst.get(ct, {}).get(cc) or []) if v is not None)
        without = parent_keys - child_vals
        checks[('fk', ct, cc, 'unmatched')] = {'parent_without_children': len(without),
                                               'ok': len(without) >= 1}
    inst['_checks'] = checks
    return {t: inst[t] for t in schema.tables}
