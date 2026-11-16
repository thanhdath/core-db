"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from .values import (ColumnSampler, DateSampler, DuplicateShareSampler, EnumSampler, PoolSampler,
                     _init_sampler, make_column_sampler)

_DATE_FMT = '%Y-%m-%d %H:%M:%S'


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


def _parse_dt(v):
    if isinstance(v, dt.datetime):
        return v
    if v is None:
        return None
    try:
        return dt.datetime.strptime(str(v)[:19], _DATE_FMT)
    except ValueError:
        return None


def _fmt_dt(d):
    return d.strftime(_DATE_FMT)


def _is_date_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _is_num_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'decimal', 'numeric', 'real', 'float', 'double'))


def _is_str_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'varchar', 'blob')) or t == ''


def _next_pk(schema, table, rng) -> int:
    """Smallest integer strictly greater than every compact/generated PK value."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 1
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _parent_values(schema, inst, pt, pc) -> list:
    """Compact + generated values of a parent column (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(inst.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _choose_table_sizes(schema, spec, rng) -> dict:
    """Specification table sizes, jittered per instance (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = int(spec.get('table_sizes', {}).get(t, 15))
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _make_sampler(schema, spec, table, cm, literal_pool, rng, n_pk):
    """Build the sampler for one non-FK column, honouring the specification pools."""
    key = (table, cm.name)
    if key in spec.get('enums', {}):
        return EnumSampler(spec['enums'][key], rng)
    if key in spec.get('boundary', {}):
        return PoolSampler(spec['boundary'][key], rng)
    if key in spec.get('agg_boundary', {}):
        return PoolSampler(spec['agg_boundary'][key], rng)
    p = 0.0 if rng.random() < 0.3 else 0.2
    inner = _init_sampler(cm, literal_pool.get(key, []), schema.original_values.get(key, []), p, rng, n_pk)
    if key in spec.get('duplicate_share', {}):
        return DuplicateShareSampler(inner, float(spec['duplicate_share'][key]), rng)
    return inner


def _apply_date_order(spec, table, cols, rng):
    """end >= start for every (table, end, start) rule; NULL end stays NULL."""
    for (t, end, start) in spec.get('date_order', []):
        if t != table or end not in cols or start not in cols:
            continue
        for i in range(len(cols[end])):
            s = _parse_dt(cols[start][i])
            e = _parse_dt(cols[end][i])
            if s is None:
                continue
            if e is None:
                if cols[end][i] is not None:
                    cols[end][i] = None
                continue
            if e < s:
                delta = dt.timedelta(seconds=rng.randint(0, 86400 * 30))
                cols[end][i] = _fmt_dt(s + delta)


def _apply_nonneg(spec, table, cols):
    """Numeric non-negative rules (product_price >= 0, total_value_purchased >= 0)."""
    for (t, c) in spec.get('nonneg', []):
        if t != table or c not in cols:
            continue
        cols[c] = [None if v is None else (abs(v) if isinstance(v, (int, float)) and v < 0 else v)
                   for v in cols[c]]


def _apply_ties(spec, table, cols, rng):
    """ties_for_order_limit: force `k` rows to share the extreme value of a column."""
    for (t, c), k in spec.get('tie_targets', {}).items():
        if t != table or c not in cols or len(cols[c]) < k:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        extreme = max(vals) if rng.random() < 0.5 else min(vals)
        idx = [i for i, v in enumerate(cols[c]) if v is not None]
        rng.shuffle(idx)
        for i in idx[:k]:
            cols[c][i] = extreme


def _apply_agg_counts(spec, table, cols, rng):
    """aggregate_boundary: make the distinct count of a column straddle a threshold."""
    for (t, c), thresholds in spec.get('agg_count_targets', {}).items():
        if t != table or c not in cols or not thresholds:
            continue
        target = rng.choice(thresholds)
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        distinct = sorted(set(vals))
        if len(distinct) > target:
            keep = set(distinct[:target])
            cols[c] = [v if (v is None or v in keep) else rng.choice(sorted(keep)) for v in cols[c]]


def _fill_fk(schema, inst, table, cm, n, rng, spec, null_share):
    """FK column: draw from parent values (compact + generated) or NULL by the NULL rule."""
    pt, pc = schema.fks[(table, cm.name)]
    pv = _parent_values(schema, inst, pt, pc)
    key = (table, cm.name)
    is_null_target = key in spec.get('null_targets', [])
    out = []
    for _ in range(n):
        if not pv:
            out.append(None)
        elif is_null_target and rng.random() < null_share:
            out.append(None)
        else:
            out.append(rng.choice(pv))
    return out


def _plant_nulls(spec, table, cols, rng, null_share):
    """At least one NULL per nullable target column; ~null_share of rows NULL."""
    for (t, c) in spec.get('null_targets', []):
        if t != table or c not in cols or not cols[c]:
            continue
        n = len(cols[c])
        for i in range(n):
            if rng.random() < null_share:
                cols[c][i] = None
        if all(v is not None for v in cols[c]):
            cols[c][rng.randrange(n)] = None


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance: compact rows + appended generated rows (fuzz.py:111-196)."""
    if spec is None:
        spec = {'enums': {}, 'boundary': {}, 'agg_boundary': {}, 'duplicate_share': {},
                'null_targets': [], 'date_order': [], 'nonneg': [], 'table_sizes': {},
                'tie_targets': {}, 'agg_count_targets': {}}
    if size is None:
        size = _choose_table_sizes(schema, spec, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        n_pk = len(tm.primary_key)
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                start = _next_pk(schema, t, rng)
                cols[cm.name] = [start + i for i in range(n)]
                continue
            s = _make_sampler(schema, spec, t, cm, literal_pool, rng, n_pk)
            cols[cm.name] = [s.sample() for _ in range(n)]
        null_share = 0.08
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                cols[cm.name] = _fill_fk(schema, inst, t, cm, n, rng, spec, null_share)
        _apply_date_order(spec, t, cols, rng)
        _apply_nonneg(spec, t, cols)
        _apply_ties(spec, t, cols, rng)
        _apply_agg_counts(spec, t, cols, rng)
        _plant_nulls(spec, t, cols, rng, null_share)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
