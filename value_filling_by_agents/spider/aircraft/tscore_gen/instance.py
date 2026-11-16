"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification rules."""
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


def choose_table_sizes(schema, rng) -> dict:
    """Base sizes from the specification, jittered per instance (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES_PER_INSTANCE.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        j = rng.uniform(0.5, 1.5)
        sizes[t] = max(0, int(round(base * j)))
    return sizes


def _compact_values(schema, table, column):
    return [v for v in schema.original_values.get((table, column), []) if v is not None]


def _compact_pk_set(schema, table):
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [_compact_values(schema, table, c) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _null_share(schema, table, column, rng):
    """NULL share following the compact database's share, at least one NULL row per nullable column."""
    key = (table, column)
    if key in spec.NULL_SHARE_OVERRIDE:
        lo, hi = spec.NULL_SHARE_OVERRIDE[key]
        return rng.uniform(lo, hi)
    vals = schema.original_values.get(key, [])
    if not vals:
        return 0.1
    share = sum(1 for v in vals if v is None) / float(len(vals))
    return max(share, 0.05)


def _plant_groups(values: list, rng, n: int) -> list:
    """Plant group sizes 1, 2 and >= 3 into a list of values (in place, returns list)."""
    if n < 6:
        return values
    reps = []
    for v in values:
        if v not in reps:
            reps.append(v)
        if len(reps) >= 3:
            break
    if len(reps) < 3:
        return values
    plan = [(reps[0], 1), (reps[1], 2), (reps[2], 3)]
    out = []
    for v, k in plan:
        out.extend([v] * k)
    i = 0
    while len(out) < n:
        out.append(values[i % len(values)])
        i += 1
    rng.shuffle(out)
    return out


def _apply_duplicate_share(values: list, rng, share_lo=0.2, share_hi=0.5) -> list:
    """duplicates_for_distinct: 20-50 % of rows reuse an already-generated value."""
    n = len(values)
    if n < 2:
        return values
    share = rng.uniform(share_lo, share_hi)
    k = int(round(n * share))
    if k <= 0:
        return values
    idx = list(range(n))
    rng.shuffle(idx)
    for j in idx[:k]:
        src = rng.randrange(n)
        if src != j:
            values[j] = values[src]
    return values


def _apply_null_rule(schema, table, cols: dict, n: int, rng) -> dict:
    """NULL rule: every nullable column gets at least one NULL row and a share of NULLs."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if not cm.notnull and cm.pk_pos == 0:
            share = _null_share(schema, table, cm.name, rng)
            k = max(1, int(round(n * share)))
            k = min(k, n)
            idx = list(range(n))
            rng.shuffle(idx)
            for j in idx[:k]:
                cols[cm.name][j] = None
    return cols


def _apply_sum_rule(schema, table, cols: dict, rng) -> dict:
    """Total_Passengers = International + Domestic + Transit (non-NULL operands only)."""
    if table != 'airport':
        return cols
    need = ['Total_Passengers', 'International_Passengers', 'Domestic_Passengers', 'Transit_Passengers']
    if not all(c in cols for c in need):
        return cols
    boundaries = set(spec.NUMERIC_BOUNDARIES.get(('airport', 'Total_Passengers'), []))
    n = len(cols['Total_Passengers'])
    for i in range(n):
        a = cols['International_Passengers'][i]
        b = cols['Domestic_Passengers'][i]
        c = cols['Transit_Passengers'][i]
        if a is not None and b is not None and c is not None:
            total = float(a) + float(b) + float(c)
            t = cols['Total_Passengers'][i]
            if t is not None and float(t) in boundaries:
                target = float(t)
                new_c = target - float(a) - float(b)
                if new_c >= 0:
                    cols['Transit_Passengers'][i] = new_c
                    continue
                new_a = target - float(b) - float(c)
                if new_a >= 0:
                    cols['International_Passengers'][i] = new_a
                    continue
            cols['Total_Passengers'][i] = total
    return cols


def _apply_comparison_boundary(schema, table, cols: dict, rng) -> dict:
    """comparison_boundary: pilot.Pilot_Id / match.Winning_Pilot equal and one step apart."""
    if table == 'pilot' and 'Pilot_Id' in cols:
        n = len(cols['Pilot_Id'])
        if n >= 3:
            base = rng.randint(1, 50)
            cols['Pilot_Id'][0] = base
            cols['Pilot_Id'][1] = base + 1
            cols['Pilot_Id'][2] = base + 2
    return cols


def _apply_match_comparison_boundary(schema, table, cols: dict, rng) -> dict:
    """Plant match.Winning_Pilot equal to a pilot PK and one step from another."""
    if table != 'match' or 'Winning_Pilot' not in cols:
        return cols
    pilot_pks = [v for v in schema.original_values.get(('pilot', 'Pilot_Id'), []) if v is not None]
    if not pilot_pks:
        return cols
    n = len(cols['Winning_Pilot'])
    if n >= 2:
        base = rng.choice(pilot_pks)
        cols['Winning_Pilot'][0] = str(base)
        cols['Winning_Pilot'][1] = str(int(base) + 1)
    return cols


def _apply_unmatched_join(schema, table, cols: dict, rng) -> dict:
    """unmatched_join_rows: child rows with NULL FK (handled by NULL rule) and parent rows without children."""
    return cols


def _apply_group_sizes(schema, table, cols: dict, rng) -> dict:
    """group_sizes "1, 2 and >= 3" for the listed columns (PK columns excluded)."""
    for (t, c) in spec.GROUP_SIZE_COLUMNS:
        if t == table and c in cols:
            cols[c] = _plant_groups(list(cols[c]), rng, len(cols[c]))
    return cols


def _apply_distinct_duplicates(schema, table, cols: dict, rng) -> dict:
    """duplicates_for_distinct: 20-50 % duplicate share."""
    for (t, c) in spec.DISTINCT_COLUMNS:
        if t == table and c in cols:
            cols[c] = _apply_duplicate_share(list(cols[c]), rng)
    return cols


def _apply_semantic_ranges(schema, table, cols: dict, rng) -> dict:
    """Semantic ranges: non-negative quantities, positive ids, Age in [18, 70]."""
    if table == 'pilot' and 'Age' in cols:
        lo, hi = spec.AGE_RANGE
        cols['Age'] = [max(lo, min(hi, int(v))) if v is not None else None for v in cols['Age']]
    if table == 'airport':
        for c in ('Total_Passengers', 'International_Passengers', 'Domestic_Passengers',
                  'Transit_Passengers', 'Aircraft_Movements', 'Freight_Metric_Tonnes'):
            if c in cols:
                cols[c] = [max(0.0, float(v)) if v is not None else None for v in cols[c]]
    return cols


def _fresh_pk_values(schema, table, cols: dict, rng) -> dict:
    """Make generated PK values fresh against the compact rows (and unique among themselves)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return cols
    if len(tm.primary_key) != 1:
        return cols
    pk = tm.primary_key[0]
    if pk not in cols:
        return cols
    compact = _compact_pk_set(schema, table)
    used = set()
    for i, v in enumerate(cols[pk]):
        if v is None:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        while (iv,) in compact or iv in used:
            iv += 1
        used.add(iv)
        cols[pk][i] = iv
    return cols


def _fill_fks_from_final(schema, inst: dict, table: str, n: int, rng) -> dict:
    """Fill FK child columns from the parent's FINAL generated PK values (after post-processing)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = inst.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _ensure_childless_parent(schema, inst: dict, table: str, rng) -> None:
    """Guarantee at least one parent row with no child for each UNMATCHED_JOIN_FKS entry."""
    for (ct, cc) in spec.UNMATCHED_JOIN_FKS:
        if ct != table:
            continue
        pt, pc = schema.fks.get((ct, cc), (None, None))
        if pt is None:
            continue
        parent_pks = inst.get(pt, {}).get(pc) or []
        child_vals = inst.get(ct, {}).get(cc) or []
        child_set = {str(v) for v in child_vals if v is not None}
        childless = [p for p in parent_pks if str(p) not in child_set]
        if childless:
            continue
        tm = schema.tables[ct]
        cm = next((c for c in tm.columns if c.name == cc), None)
        if cm is not None and not cm.notnull and child_vals:
            for i, v in enumerate(child_vals):
                if v is not None:
                    child_vals[i] = None
                    break


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random *delta* instance (fuzz.py:111-196) with round-1 specification rules."""
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
    for t in order:
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        cols = _apply_semantic_ranges(schema, t, cols, rng)
        cols = _apply_comparison_boundary(schema, t, cols, rng)
        cols = _apply_group_sizes(schema, t, cols, rng)
        cols = _apply_distinct_duplicates(schema, t, cols, rng)
        inst[t] = cols
    for t in order:
        cols = inst[t]
        if not cols:
            continue
        cols = _fresh_pk_values(schema, t, cols, rng)
        inst[t] = cols
    for t in order:
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        fk_cols = _fill_fks_from_final(schema, inst, t, n, rng)
        cols.update(fk_cols)
        inst[t] = cols
    for t in order:
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        cols = _apply_null_rule(schema, t, cols, n, rng)
        inst[t] = cols
    for t in order:
        cols = inst[t]
        if not cols:
            continue
        cols = _apply_sum_rule(schema, t, cols, rng)
        inst[t] = cols
    for t in order:
        cols = inst[t]
        if not cols:
            continue
        cols = _apply_match_comparison_boundary(schema, t, cols, rng)
        cols = _apply_unmatched_join(schema, t, cols, rng)
        inst[t] = cols
    for t in order:
        _ensure_childless_parent(schema, inst, t, rng)
    return {t: inst[t] for t in schema.tables}
