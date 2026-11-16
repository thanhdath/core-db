"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
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


def _parent_id_pool(instance: dict, schema, table: str, column: str) -> list:
    """Parent id pool: compact rows plus generated rows (in memory)."""
    vals = list(schema.original_values.get((table, column), []))
    vals += list(instance.get(table, {}).get(column, []))
    return [v for v in vals if v is not None]


def _assign_group_sizes(n: int, n_parents: int, rng) -> list:
    """Assign child counts to parents so that sizes 1, 2 and >= 3 all occur and at least one parent has >= 4 children
    (aggregate boundary)."""
    if n <= 0:
        return []
    if n_parents <= 0:
        raise ValueError('no parent rows for FK assignment')
    required = list(spec.GROUP_SIZE_TARGETS['sizes'])
    min_large = spec.GROUP_SIZE_TARGETS['min_large']
    sizes = list(required) + [min_large]
    if sum(sizes) > n:
        raise ValueError('cannot satisfy group-size targets with n=%d (need >= %d)'
                         % (n, sum(sizes)))
    remainder = n - sum(sizes)
    if remainder:
        sizes[sizes.index(max(sizes))] += remainder
    if sum(sizes) != n:
        raise ValueError('group-size assignment does not cover n=%d' % n)
    if len(sizes) < 3 or max(sizes) < min_large:
        raise ValueError('group-size targets not met: %r' % (sizes,))
    rng.shuffle(sizes)
    pairs = []
    for k, s in enumerate(sizes):
        pairs.append((k % n_parents, s))
    return pairs


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's id pool (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_id_pool(instance, schema, pt, pc)
        if not pv:
            out[cm.name] = [None] * n
            continue
        if table == 'cars' and cm.name == 'train_id':
            pairs = _assign_group_sizes(n, len(pv), rng)
            vals = []
            for k, s in pairs:
                vals.extend([pv[k]] * s)
            if len(vals) != n:
                raise ValueError('FK assignment produced %d values for %d rows' % (len(vals), n))
            rng.shuffle(vals)
            out[cm.name] = vals
        else:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Table sizes per instance (specification: table_sizes_per_instance)."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = int(spec.TABLE_SIZES.get(t, 0))
    return sizes


def _next_pk_start(schema, table: str, column: str) -> int:
    """First fresh integer primary key (sequential, fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _balance_direction(schema, table: str, cols: dict, rng) -> None:
    """Force an equal east/west split across generated trains (rank-1 tie)."""
    if not spec.DIRECTION_TIE or table != 'trains' or 'direction' not in cols:
        return
    pool = spec.enum_pool('trains', 'direction')
    if len(pool) < 2:
        return
    n = len(cols['direction'])
    if n < 2:
        return
    half = n // 2
    vals = [pool[0]] * half + [pool[1]] * (n - half)
    rng.shuffle(vals)
    cols['direction'] = vals


def _plant_nulls(schema, table: str, cols: dict, rng) -> None:
    """Plant exactly one NULL per nullable column (interface NULL rule)."""
    n = _n_rows(cols)
    if n < 2:
        return
    for cm in schema.tables[table].columns:
        if cm.name not in cols or cm.notnull or cm.pk_pos > 0:
            continue
        if any(v is None for v in cols[cm.name]):
            continue
        cols[cm.name][rng.randrange(n)] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz/fuzz.py:111-196), appended to the compact rows."""
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
        for cm in tm.columns:
            if cm.pk_pos > 0 and 'int' in (cm.type_str or '').lower():
                start = _next_pk_start(schema, t, cm.name)
                cols[cm.name] = list(range(start, start + n))
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = {cm.name: cols[cm.name] for cm in tm.columns}
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _balance_direction(schema, t, cols, rng)
        _plant_nulls(schema, t, cols, rng)
        lengths = {len(v) for v in cols.values()}
        if len(lengths) > 1:
            raise ValueError('inconsistent column lengths for %s: %r' % (t, lengths))
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
