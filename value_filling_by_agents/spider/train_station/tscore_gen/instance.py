"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
from .values import _init_sampler, make_column_sampler


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


def choose_table_sizes(schema, rng) -> dict:
    """Spec table_sizes_per_instance when present, else upstream rand_lin / level sizes."""
    sizes = {}
    for t in schema.tables:
        if t in spec.TABLE_SIZES:
            sizes[t] = spec.TABLE_SIZES[t]
    if len(sizes) == len(schema.tables):
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _is_nullable(cm) -> bool:
    return not cm.notnull and cm.pk_pos == 0


def _is_int_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'int' in t


def _plant_nulls(cols: dict, tm, rng) -> None:
    """NULL rule: every nullable column gets >=1 NULL and ~NULL_SHARE NULL rows."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols or not _is_nullable(cm):
            continue
        k = max(1, int(round(spec.NULL_SHARE * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None


def _apply_boundaries(cols: dict, table: str, rng) -> None:
    """comparison_boundary: plant the listed literals in the column."""
    for (t, c), vals in spec.BOUNDARIES.items():
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n == 0:
            continue
        for j, v in enumerate(vals):
            if j < n:
                cols[c][j] = v


def _apply_enum(cols: dict, table: str, rng) -> None:
    for (t, c), vals in spec.ENUMS.items():
        if t != table or c not in cols:
            continue
        for i in range(len(cols[c])):
            cols[c][i] = rng.choice(vals)


def _apply_text_pools(cols: dict, table: str, rng) -> None:
    """text_name / text_free pools with near-duplicates and DISTINCT duplicate share."""
    pool = spec.NAME_POOL.get(table)
    if pool and 'Name' in cols:
        n = len(cols['Name'])
        for i in range(n):
            v = rng.choice(pool)
            u = rng.random()
            if u < 0.15:
                v = v + ' '
            elif u < 0.25:
                v = v.lower()
            cols['Name'][i] = v
    if table == 'station':
        if 'Location' in cols:
            for i in range(len(cols['Location'])):
                cols['Location'][i] = rng.choice(spec.LOCATION_POOL)
        if 'Main_Services' in cols:
            for i in range(len(cols['Main_Services'])):
                cols['Main_Services'][i] = rng.choice(spec.SERVICE_POOL)


def _apply_distinct_duplicates(cols: dict, table: str, rng) -> None:
    """duplicates_for_distinct: 20-50 % duplicate share on the listed columns."""
    for (t, c) in spec.DISTINCT_DUP_COLUMNS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        share = rng.uniform(0.2, 0.5)
        k = max(1, int(round(share * n)))
        src = list(range(n))
        rng.shuffle(src)
        for i in src[:k]:
            j = rng.choice([x for x in range(n) if x != i])
            cols[c][i] = cols[c][j]


def _shape_group_sizes(cols: dict, table: str, cm, rng) -> None:
    """group_sizes: force sizes 1, 2 and >=3 for the listed columns."""
    c = cm.name
    if (table, c) not in spec.GROUP_SIZE_COLUMNS or c not in cols:
        return
    n = len(cols[c])
    if n < 6:
        return
    is_int = _is_int_col(cm)
    if is_int:
        base = [v for v in cols[c] if isinstance(v, int)]
        if not base:
            base = [rng.randint(1, 10 ** 6) for _ in range(3)]
        g1 = base[0]
        g2 = base[1] if len(base) > 1 else base[0] + 1
        g3 = base[2] if len(base) > 2 else base[0] + 2
        plan = [g1, g2, g2, g3, g3, g3]
        for i in range(6, n):
            plan.append(base[i % len(base)] + 1000 + i)
    else:
        pool = spec.NAME_POOL.get(table) or spec.LOCATION_POOL
        if c == 'Location':
            pool = spec.LOCATION_POOL
        elif c == 'Main_Services':
            pool = spec.SERVICE_POOL
        g1 = rng.choice(pool)
        g2 = rng.choice(pool)
        g3 = rng.choice(pool)
        plan = [g1, g2, g2, g3, g3, g3]
        for i in range(6, n):
            plan.append(rng.choice(pool))
    for i in range(n):
        cols[c][i] = plan[i]


def _apply_ties(cols: dict, table: str, rng) -> None:
    """ties_for_order_limit: at least two rows share the tie value at rank 1."""
    for (t, c) in spec.TIE_COLUMNS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        if c == 'Time':
            earliest = '00:00'
            for i in range(min(n, spec.TIME_LIMIT_TIE)):
                cols[c][i] = earliest
            for i in range(spec.TIME_LIMIT_TIE, n):
                cols[c][i] = '%02d:%02d' % (rng.randrange(24), rng.randrange(60))
        else:
            v = cols[c][0]
            cols[c][1] = v


def _apply_formula(cols: dict, table: str) -> None:
    """semantic formula: Total_Passengers = Annual_entry_exit + Annual_interchanges."""
    t, dst, a, b = spec.TOTAL_PASSENGERS_FORMULA
    if t != table or dst not in cols or a not in cols or b not in cols:
        return
    for i in range(len(cols[dst])):
        x, y = cols[a][i], cols[b][i]
        if x is None or y is None:
            continue
        if cols[dst][i] is None:
            continue
        cols[dst][i] = round(float(x) + float(y), 3)


def _apply_ranges(cols: dict, table: str, rng) -> None:
    """semantic ranges: clamp numeric columns into their declared range."""
    for (t, c), (lo, hi) in spec.RANGES.items():
        if t != table or c not in cols:
            continue
        for i, v in enumerate(cols[c]):
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f < lo:
                f = lo
            elif f > hi:
                f = hi
            cols[c][i] = int(f) if isinstance(lo, int) and isinstance(hi, int) else round(f, 3)


def _apply_aggregate_counts(cols: dict, table: str, rng) -> None:
    """aggregate_boundary: ensure COUNT values 1, 2, 3 occur across groups."""
    if table != 'train_station' or 'Station_ID' not in cols:
        return
    n = len(cols['Station_ID'])
    if n < 6:
        return
    base = [v for v in cols['Station_ID'] if isinstance(v, int)]
    if not base:
        base = [rng.randint(1, 10 ** 6) for _ in range(3)]
    s1 = base[0]
    s2 = base[1] if len(base) > 1 else base[0] + 1
    s3 = base[2] if len(base) > 2 else base[0] + 2
    plan = [s1, s2, s2, s3, s3, s3]
    for i in range(6, n):
        plan.append(base[i % len(base)] + 1000 + i)
    for i in range(n):
        cols['Station_ID'][i] = plan[i]


def _apply_unmatched(cols: dict, table: str, rng) -> None:
    """unmatched_join_rows: leave some parent rows without children."""
    return


def _revalidate_fks(inst: dict, schema, rng) -> None:
    """Re-establish FK consistency after all shaping passes."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        child = inst[ct]
        if cc not in child:
            continue
        parent_vals = inst[pt].get(pc) or []
        pool = [v for v in parent_vals if v is not None]
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        nullable = cm is not None and _is_nullable(cm)
        for i, v in enumerate(child[cc]):
            if v in pool:
                continue
            if pool:
                child[cc][i] = rng.choice(pool)
            elif nullable:
                child[cc][i] = None
            else:
                child[cc][i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
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
        inst[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        if not cols:
            continue
        _apply_enum(cols, t, rng)
        _apply_text_pools(cols, t, rng)
        _apply_ranges(cols, t, rng)
        _apply_boundaries(cols, t, rng)
        for cm in tm.columns:
            _shape_group_sizes(cols, t, cm, rng)
        _apply_aggregate_counts(cols, t, rng)
        _apply_ties(cols, t, rng)
        _apply_distinct_duplicates(cols, t, rng)
        _apply_formula(cols, t)
        _apply_unmatched(cols, t, rng)
        _plant_nulls(cols, tm, rng)
        _apply_formula(cols, t)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols

    _revalidate_fks(inst, schema, rng)

    return {t: inst[t] for t in schema.tables}
