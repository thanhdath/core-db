"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec construction."""
import datetime as dt
import re

from . import spec
from .values import spec_sampler

_NUM = re.compile(r'^-?\d+$')


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pk: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(compact_pk), []
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


def _null_share(table: str, col: str) -> float:
    return spec.NULL_SHARE.get((table, col), spec.DEFAULT_NULL_SHARE)


def _plant_nulls(table: str, col: str, values: list, rng) -> list:
    """NULL rule: at least one NULL row per nullable column, share from spec.NULL_SHARE."""
    if not values:
        return values
    share = _null_share(table, col)
    n = len(values)
    n_null = max(1, int(round(share * n)))
    n_null = min(n_null, n)
    idx = set(rng.sample(range(n), n_null))
    return [None if i in idx else v for i, v in enumerate(values)]


def _fk_pool(instance: dict, schema, pt: str, pc: str, reserved: dict) -> list:
    """Parent values available to a child FK: compact parents + generated parents."""
    pool = list(schema.compact_fk.get((pt, pc), []))
    gen = instance.get(pt, {}).get(pc) or []
    pool.extend([v for v in gen if v is not None])
    rv = reserved.get(pt)
    if rv is not None:
        pool = [v for v in pool if v != rv]
    return pool


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, reserved: dict) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _fk_pool(instance, schema, pt, pc, reserved)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes (spec.TABLE_SIZES); fall back to the generic rand_lin / level sizes."""
    sizes = {}
    for t in schema.tables:
        if t in spec.TABLE_SIZES:
            sizes[t] = spec.TABLE_SIZES[t]
    if len(sizes) == len(schema.tables):
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                if t not in sizes:
                    min_c = 30 * rng.random()
                    sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                if t not in sizes:
                    sizes[t] = int(min(s, 2500))
                s *= 4
    return sizes


def _derive_results(cols: dict, rng) -> None:
    """positionText = position OR in ('R','D','E','F','W'); laps/milliseconds consistent."""
    pos = cols.get('position', [])
    pt = []
    for p in pos:
        if p is None:
            pt.append(None)
        else:
            pt.append(str(p))
    cols['positionText'] = pt
    laps = cols.get('laps', [])
    out_laps = []
    for v in laps:
        if v is None:
            out_laps.append(None)
        elif _NUM.match(str(v)):
            out_laps.append(str(int(v)))
        else:
            out_laps.append(str(v))
    cols['laps'] = out_laps
    t = cols.get('time', [])
    ms = cols.get('milliseconds', [])
    out = []
    for i, v in enumerate(ms):
        if i < len(t) and (t[i] is None or t[i] == ''):
            out.append('')
        elif v is None:
            out.append('')
        elif _NUM.match(str(v)):
            out.append(str(int(v)))
        else:
            out.append(str(v))
    cols['milliseconds'] = out


def _derive_races(cols: dict) -> None:
    """date must lie within the year (spec formula); robust to any year value."""
    years = cols.get('year', [])
    dates = cols.get('date', [])
    out = []
    for i, d in enumerate(dates):
        if d is None:
            out.append(None)
            continue
        y = years[i] if i < len(years) else None
        if y is None:
            out.append(d)
            continue
        try:
            dd = dt.datetime.strptime(str(d), '%Y-%m-%d')
        except ValueError:
            out.append(d)
            continue
        try:
            y = int(y)
        except (TypeError, ValueError):
            out.append(d)
            continue
        if dd.year != y:
            try:
                dd = dd.replace(year=y)
            except ValueError:
                dd = dt.datetime(y, 1, 1)
            out.append(dd.strftime('%Y-%m-%d'))
        else:
            out.append(d)
    cols['date'] = out


def _derive_constructor_results(cols: dict) -> None:
    """status IS NULL OR status IN ('D')."""
    st = cols.get('status', [])
    cols['status'] = [None if v is None else 'D' for v in st]


def _plant_group_sizes(table: str, col: str, values: list, rng) -> list:
    """Force group sizes 1, 2 and >= 3 for the given (non-PK) column."""
    targets = spec.GROUP_SIZE_TARGETS.get((table, col))
    if not targets or not values:
        return values
    n = len(values)
    sizes = [1, 2, 3]
    remaining = n - sum(sizes)
    while remaining > 0:
        s = min(remaining, rng.choice([1, 2, 3, 4]))
        sizes.append(s)
        remaining -= s
    out = []
    for gi, s in enumerate(sizes):
        v = values[gi % len(values)]
        out.extend([v] * s)
    return out[:n]


def _plant_ties(table: str, col: str, values: list, rng) -> list:
    """Ensure at least two rows share the top value of the ORDER column (non-PK only)."""
    direction = spec.TIE_COLUMNS.get((table, col)) or spec.TIE_CHILD_COLUMNS.get((table, col))
    if direction is None or len(values) < 2:
        return values
    try:
        top = max(values) if direction == 'DESC' else min(values)
    except TypeError:
        return values
    out = list(values)
    out[0] = top
    out[1] = top
    return out


def _plant_aggregate_boundary(table: str, col: str, values: list, rng) -> list:
    """Plant a group count in the aggregate-boundary set for the given grouping column."""
    targets = spec.AGGREGATE_BOUNDARY.get((table, col))
    if not targets or not values:
        return values
    n = len(values)
    if n < 4:
        return values
    pool = sorted({v for v in values if v is not None})
    if not pool:
        return values
    k = min(rng.choice(targets), n)
    anchor = rng.choice(pool)
    out = [anchor] * k
    rest = [rng.choice(pool) for _ in range(n - k)]
    out.extend(rest)
    rng.shuffle(out)
    return out


def _plant_distinct_duplicates(table: str, col: str, values: list, rng) -> list:
    """Control the number of distinct values to hit a 20-50 % duplicate share."""
    share = spec.DISTINCT_DUP_SHARE.get((table, col))
    if share is None or not values:
        return values
    n = len(values)
    pool = sorted({v for v in values if v is not None})
    if not pool:
        return values
    n_distinct = max(1, int(round(n * (1.0 - share))))
    n_distinct = min(n_distinct, len(pool), n)
    chosen = rng.sample(pool, n_distinct)
    return [rng.choice(chosen) for _ in range(n)]


def _plant_unmatched(instance: dict, schema, rng) -> None:
    """Plant NULL FKs in child tables (non-PK, nullable columns only)."""
    for (pt, pc), children in spec.UNMATCHED.items():
        for (ct, cc) in children:
            child_cols = instance.get(ct)
            if not child_cols or cc not in child_cols or not child_cols[cc]:
                continue
            cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
            if cm is None or cm.notnull or cm.pk_pos > 0:
                continue
            child_cols[cc][0] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with round-1 spec construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = spec_sampler(
                    t, cm.name, cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), rng, p,
                    len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    reserved: dict = {}
    for pt, pc in spec.RESERVED_PARENTS.items():
        if pt in schema.tables and pc in [c.name for c in schema.tables[pt].columns]:
            reserved[pt] = None
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, reserved))
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.name not in cols:
                continue
            if cm.pk_pos == 0:
                cols[cm.name] = _plant_group_sizes(t, cm.name, cols[cm.name], rng)
                cols[cm.name] = _plant_aggregate_boundary(t, cm.name, cols[cm.name], rng)
                cols[cm.name] = _plant_distinct_duplicates(t, cm.name, cols[cm.name], rng)
                cols[cm.name] = _plant_ties(t, cm.name, cols[cm.name], rng)
                if not cm.notnull:
                    cols[cm.name] = _plant_nulls(t, cm.name, cols[cm.name], rng)
        if t == 'results':
            _derive_results(cols, rng)
        elif t == 'races':
            _derive_races(cols)
        elif t == 'constructorResults':
            _derive_constructor_results(cols)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         schema.compact_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        if t in reserved and reserved[t] is None:
            pk_col = spec.RESERVED_PARENTS[t]
            vals = [v for v in cols.get(pk_col, []) if v is not None]
            if vals:
                reserved[t] = rng.choice(vals)
    _plant_unmatched(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
