"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append rows to a compact database."""
from .values import _init_sampler

SPEC_SIZES = {'item': 8, 'useracct': 7, 'review': 7, 'trust': 9}

BOUNDARY = {('review', 'rank'): [2, 3, 4], ('review', 'rating'): [4, 5, 6]}

RATING_RANGE = (0, 10)

GROUP_SIZE_COLUMNS = {('review', 'u_id'), ('review', 'i_id'), ('trust', 'source_u_id'),
                      ('trust', 'target_u_id')}

ITEM_COMPARE_COL = ('item', 'i_id')


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
    """Compact parent key values plus generated parent key values (in memory, final set)."""
    compact = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    gen = [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    seen, out = set(), []
    for v in compact + gen:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with small per-instance variation (0-230 rows per table)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = SPEC_SIZES.get(t, 8)
            jitter = rng.randint(-2, 2)
            sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _fresh_pk_values(table_meta, schema, n: int, rng) -> dict:
    """Sequential fresh integer PKs starting after the compact max (never collide with compact rows)."""
    out = {}
    for cm in table_meta.columns:
        if cm.pk_pos <= 0:
            continue
        compact = [v for v in schema.original_values.get((table_meta.name, cm.name), []) if isinstance(v, int)]
        start = (max(compact) + 1) if compact else 1
        out[cm.name] = [start + i for i in range(n)]
    return out


def _assign_group_sizes(values: list, parent_pool: list, rng) -> list:
    """Reassign FK values so that groups of size 1, 2 and >= 3 appear (best-effort)."""
    if not parent_pool or not values:
        return [rng.choice(parent_pool) for _ in values] if parent_pool else values
    n = len(values)
    plan = []
    plan += [1]
    if n >= 3:
        plan += [2]
    if n >= 6:
        plan += [3]
    rest = n - sum(plan)
    while rest > 0:
        plan.append(1)
        rest -= 1
    pool = list(parent_pool)
    rng.shuffle(pool)
    out = []
    pi = 0
    for g in plan:
        v = pool[pi % len(pool)]
        pi += 1
        out.extend([v] * g)
    out = out[:n]
    rng.shuffle(out)
    return out


def _plant_nulls(table: str, columns: dict, schema, rng) -> None:
    """Plant NULLs following the compact null share; ensure >=1 NULL when the share is 0.0 and the column is
    nullable."""
    for cm in schema.tables[table].columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        vals = columns.get(cm.name)
        if not vals:
            continue
        share = schema.null_share.get((table, cm.name), 0.0)
        has_null = False
        for i in range(len(vals)):
            if rng.random() < share:
                vals[i] = None
                has_null = True
        if not has_null:
            vals[rng.randrange(len(vals))] = None


def _plant_boundaries(table: str, columns: dict, rng) -> None:
    """Ensure comparison-boundary literals appear in the column (rank 2,3,4; rating 4,5,6)."""
    for (t, c), lits in BOUNDARY.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        if not vals:
            continue
        for lit in lits:
            if lit not in vals:
                vals[rng.randrange(len(vals))] = lit


def _plant_item_comparison_boundary(instance: dict, rng) -> None:
    """Ensure a generated item.i_id equals a review.i_id and one step from it (equal_and_one_step_from)."""
    if 'item' not in instance or 'i_id' not in instance['item']:
        return
    items = instance['item']['i_id']
    reviews = instance.get('review', {}).get('i_id', [])
    ref = [v for v in reviews if v is not None]
    if not items or not ref:
        return
    target = ref[rng.randrange(len(ref))]
    compact = []
    if target is not None:
        compact = [target, target - 1, target + 1]
    if items:
        items[rng.randrange(len(items))] = compact[0]


def _clamp_rating(columns: dict) -> None:
    """Keep review.rating within [0, 10] (semantic rule) for non-NULL values."""
    vals = columns.get('rating')
    if not vals:
        return
    lo, hi = RATING_RANGE
    for i, v in enumerate(vals):
        if v is None:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        vals[i] = max(lo, min(hi, iv))


def _clamp_rank(columns: dict) -> None:
    """Keep review.rank > 0 (semantic rule) for non-NULL values."""
    vals = columns.get('rank')
    if not vals:
        return
    for i, v in enumerate(vals):
        if v is None:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        vals[i] = max(1, iv)


def _clamp_trust(columns: dict) -> None:
    """Keep trust.trust >= 0 (semantic rule)."""
    vals = columns.get('trust')
    if not vals:
        return
    for i, v in enumerate(vals):
        if v is None:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        vals[i] = max(0, iv)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of appended rows (fuzz.py:111-196, adapted)."""
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
        cols.update(_fresh_pk_values(tm, schema, n, rng))
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pool = _parent_pool(inst, schema, pt, pc)
            if key in GROUP_SIZE_COLUMNS:
                cols[cm.name] = _assign_group_sizes([None] * n, pool, rng) if n else []
            else:
                cols[cm.name] = [rng.choice(pool) for _ in range(n)] if pool else [None] * n
        if t == 'review':
            _clamp_rating(cols)
            _clamp_rank(cols)
        if t == 'trust':
            _clamp_trust(cols)
        _plant_boundaries(t, cols, rng)
        _plant_nulls(t, cols, schema, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    _plant_item_comparison_boundary(inst, rng)
    return {t: inst[t] for t in schema.tables}
