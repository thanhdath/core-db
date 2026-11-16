"""Random instance construction (fuzz/fuzz.py:83-196) + specification samplers."""
import math

from . import spec as S
from .values import (_init_sampler, EnumSampler, YearSampler, PositiveRealSampler,
                     near_variant, like_variants)


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    base = (spec.get('_sizes') or {}) if isinstance(spec, dict) else {}
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
    for t, b in base.items():
        if t in sizes:
            sizes[t] = max(0, int(b) + rng.randint(-1, 2))
    return sizes


def _pk_start(schema, table: str) -> int:
    """Next integer primary key after the compact rows (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _group_size_plan(n: int, rng) -> list:
    """Group sizes covering 1, 2 and >= 3 (specification group_sizes target)."""
    plan = [1, 2, 3]
    while sum(plan) < n:
        plan.append(rng.choice([1, 2, 3, 3, 4]))
    return plan


def _assign_groups(n: int, rng) -> list:
    """Assign each of n rows a group index whose sizes cover 1, 2 and >= 3."""
    plan = _group_size_plan(n, rng)
    out = []
    for g, k in enumerate(plan):
        out.extend([g] * k)
    out = out[:n]
    rng.shuffle(out)
    return out


def _grouped_values(pool: list, n: int, rng) -> list:
    """Values drawn from pool so that group sizes cover 1, 2 and >= 3 (non-FK group target)."""
    if not pool or n <= 0:
        return [None] * n
    groups = _assign_groups(n, rng)
    gvals = {}
    for g in set(groups):
        gvals[g] = rng.choice(pool)
    return [gvals[g] for g in groups]


def _plant_nulls(values: list, nullable: bool, share: float, rng) -> list:
    """NULL rule: at least one NULL per nullable column, share following the compact share."""
    if not nullable or not values:
        return values
    k = max(1, int(round(len(values) * share)))
    k = min(k, len(values))
    idx = rng.sample(range(len(values)), k)
    for i in idx:
        values[i] = None
    return values


def _spec_sampler(schema, table: str, column: str, plan: dict, pool: list, rng):
    """Build a specification-aware sampler for one column, or None to use the generic one."""
    enum = S.enum_values(table, column)
    if enum:
        return EnumSampler(enum, rng)
    if (table, column) == ('mill', 'built_year'):
        return YearSampler(S.YEAR_RANGE[0], S.YEAR_RANGE[1], S.YEAR_BOUNDARY, rng)
    if (table, column) == ('bridge', 'length_meters'):
        ov = [v for v in schema.original_values.get((table, column), []) if isinstance(v, (int, float))]
        ties = sorted(ov, reverse=True)[:1] if ov else []
        return PositiveRealSampler(ov + [float(x) for x in pool if _isnum(x)], rng, ties)
    return None


def _isnum(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _nationality_values(schema, pool: list, rng, n: int) -> list:
    """Nationality pool with the specification's boundary values and LIKE near-variants."""
    base = [v for v in schema.original_values.get(('architect', 'nationality'), []) if v is not None]
    base = base or list(S.NATIONALITY_POOL)
    extra = ['Canadian', 'canadian', 'American', 'american', 'Aan', 'aan', 'Cn', 'cn', 'ic', 'IC']
    extra += ['Americao', 'American x', 'american']
    extra += like_variants('American%')
    vals = []
    for _ in range(n):
        u = rng.random()
        if u < 0.5:
            vals.append(rng.choice(base))
        elif u < 0.8:
            vals.append(rng.choice(extra))
        else:
            vals.append(near_variant(rng.choice(base), rng))
    return vals


def _name_values(schema, table: str, column: str, pool: list, rng, n: int) -> list:
    """Name pool with 5% near-duplicates (case/whitespace variants) to exercise DISTINCT."""
    base = [v for v in schema.original_values.get((table, column), []) if v is not None]
    base = base or list(S.NAME_POOL)
    vals = []
    for _ in range(n):
        v = rng.choice(base)
        if rng.random() < 0.05:
            v = near_variant(v, rng)
        vals.append(v)
    return vals


def _location_values(schema, table: str, column: str, rng, n: int) -> list:
    base = [v for v in schema.original_values.get((table, column), []) if v is not None]
    base = base or list(S.LOCATION_POOL)
    vals = []
    for _ in range(n):
        v = rng.choice(base)
        if rng.random() < 0.05:
            v = near_variant(v, rng)
        vals.append(v)
    return vals


def _notes_values(schema, table: str, column: str, rng, n: int) -> list:
    base = [v for v in schema.original_values.get((table, column), []) if v is not None]
    base = base or list(S.NOTE_POOL)
    vals = []
    for _ in range(n):
        if rng.random() < 0.1:
            vals.append('note %d' % rng.randint(1, 99))
        else:
            vals.append(rng.choice(base))
    return vals


def _apply_formulas(schema, table: str, cols: dict, rng) -> None:
    """Derived columns computed in Python from sampled values (never with SQL)."""
    for cm in schema.tables[table].columns:
        f = S.formula(table, cm.name)
        if not f:
            continue
        kind, (src, factor) = f
        if src not in cols:
            continue
        if kind == 'round_half_up':
            cols[cm.name] = [S.length_feet_value(v) for v in cols[src]]
        else:
            cols[cm.name] = [None] * len(cols[src])


def _null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.1
    nulls = sum(1 for v in vals if v is None)
    return max(0.05, min(0.5, nulls / len(vals) if nulls else 0.1))


def _reserve_childless_parent(inst: dict, schema, table: str, rng) -> None:
    """Ensure at least one parent row has no children in any child table (parent_rows_without_children)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return
    pk = tm.primary_key[0]
    pvals = inst.get(table, {}).get(pk) or []
    if not pvals:
        return
    children = [(ct, cc) for (ct, cc), (pt, pc) in schema.fks.items() if pt == table and pc == pk]
    if not children:
        return
    used = set()
    for ct, cc in children:
        for v in inst.get(ct, {}).get(cc, []) or []:
            if v is not None:
                used.add(v)
    free = [v for v in pvals if v not in used]
    if free:
        return
    ct, cc = children[0]
    col_meta = next((c for c in schema.tables[ct].columns if c.name == cc), None)
    vals = inst.get(ct, {}).get(cc)
    if vals is None:
        return
    if col_meta is not None and not col_meta.notnull:
        vals[0] = None
    else:
        n = len(vals)
        keep = list(range(1, n))
        inst[ct] = _filter(inst[ct], keep)


def _bridge_lengths_by_group(schema, n: int, rng, base_pool: list) -> list:
    """bridge.length_meters: >= 2 distinct values per architect group and a tie at rank 1."""
    if n <= 0:
        return []
    pool = [float(v) for v in base_pool if _isnum(v) and float(v) > 0]
    if not pool:
        pool = [121.0, 88.0, 87.0, 76.0, 74.0, 71.0, 70.0, 69.0]
    top = max(pool)
    vals = []
    for i in range(n):
        if i < 2:
            vals.append(top)
        else:
            v = rng.choice(pool)
            if rng.random() < 0.2:
                v = max(0.1, v + rng.choice([-1.0, 1.0, -2.0, 2.0]))
            vals.append(round(v, 1))
    rng.shuffle(vals)
    return vals


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            plan = S.column_plan(spec, t, cm.name)
            sp = _spec_sampler(schema, t, cm.name, plan, literal_pool.get((t, cm.name), []), rng)
            if sp is not None:
                samplers[(t, cm.name)] = sp
            else:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            plan = S.column_plan(spec, t, cm.name)
            if (t, cm.name) == ('architect', 'nationality'):
                cols[cm.name] = _nationality_values(schema, literal_pool.get((t, cm.name), []), rng, n)
            elif cm.name.lower() == 'name':
                cols[cm.name] = _name_values(schema, t, cm.name, literal_pool.get((t, cm.name), []), rng, n)
            elif cm.name.lower() == 'location':
                cols[cm.name] = _location_values(schema, t, cm.name, rng, n)
            elif cm.name.lower() == 'notes':
                cols[cm.name] = _notes_values(schema, t, cm.name, rng, n)
            elif (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
            else:
                cols[cm.name] = [None] * n
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            start = _pk_start(schema, t)
            cols[pk] = list(range(start, start + n))
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            plan = S.column_plan(spec, t, cm.name)
            if 'group_sizes' in plan and cm.name in cols and cm.name.lower() not in ('id',):
                pool = [v for v in cols[cm.name] if v is not None]
                if pool:
                    cols[cm.name] = _grouped_values(pool, n, rng)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            plan = S.column_plan(spec, t, cm.name)
            pt, pc = schema.fks[(t, cm.name)]
            pv = inst.get(pt, {}).get(pc) or []
            if 'group_sizes' in plan and pv:
                groups = _assign_groups(n, rng)
                fk_cols[cm.name] = [pv[g % len(pv)] for g in groups]
        cols.update(fk_cols)
        if (t, 'length_meters') in [(t, c.name) for c in tm.columns]:
            plan = S.column_plan(spec, t, 'length_meters')
            if plan.get('rows_with_different_values'):
                base = [v for v in schema.original_values.get((t, 'length_meters'), []) if _isnum(v)]
                cols['length_meters'] = _bridge_lengths_by_group(schema, n, rng, base)
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            if cm.name not in cols:
                continue
            share = _null_share(schema, t, cm.name)
            cols[cm.name] = _plant_nulls(cols[cm.name], True, share, rng)
        _apply_formulas(schema, t, cols, rng)
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
    for t in order:
        _reserve_childless_parent(inst, schema, t, rng)
    return {t: inst[t] for t in schema.tables}
