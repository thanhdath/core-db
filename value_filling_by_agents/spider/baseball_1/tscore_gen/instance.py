"""Random instance construction (fuzz/fuzz.py:83-196) with specification rules by construction."""
import random

from . import rules
from .values import _init_sampler

GROUP_SIZE_COLUMNS = {
    ('team', 'team_id'), ('home_game', 'team_id'), ('player', 'name_first'), ('player', 'name_last'),
    ('park', 'city'), ('salary', 'player_id'), ('team', 'h'),
}

DUPLICATE_COLUMNS = {
    ('park', 'park_id'), ('salary', 'salary'), ('all_star', 'game_id'),
}

TIE_COLUMNS = {
    ('team', 'attendance'), ('home_game', 'attendance'),
}

ORPHAN_FK_COLUMNS = {
    ('home_game', 'team_id'), ('salary', 'team_id'), ('all_star', 'team_id'), ('all_star', 'player_id'),
    ('manager', 'team_id'), ('team', 'team_id_br'),
}

ORPHAN_SHARE = 0.05


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
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
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
    """Uniform rand_lin sizes w.p."""
    sizes = {}
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
    return sizes


def _plant_boundary_values(table, col, n, rng):
    bv = rules.BOUNDARY_VALUES.get((table, col))
    if not bv:
        return None
    out = list(bv)
    while len(out) < n:
        out.append(rng.choice(bv))
    rng.shuffle(out)
    return out[:n]


def _plant_literal_pool(table, col, n, rng):
    lp = rules.LITERAL_POOLS.get((table, col))
    if not lp:
        return None
    out = list(lp)
    while len(out) < n:
        out.append(rng.choice(lp))
    rng.shuffle(out)
    return out[:n]


def _plant_enum(table, col, n, rng):
    ep = rules.ENUMS.get((table, col))
    if not ep:
        return None
    return [rng.choice(ep) for _ in range(n)]


def _plant_duplicates(table, col, n, rng, share=0.35):
    """Return a list of n values with a duplicate share in [20%, 50%]."""
    k = max(2, int(n * share))
    pool = [rng.randint(0, 1000) for _ in range(k)]
    return [rng.choice(pool) for _ in range(n)]


def _plant_tie(table, col, n, rng):
    """Return a list of n values where at least two share the top value."""
    if n < 2:
        return None
    top = rng.randint(100, 1000)
    out = [rng.randint(0, top - 1) for _ in range(n)]
    out[0] = top
    out[1] = top
    rng.shuffle(out)
    return out


def _plant_group_sizes(table, col, n, rng):
    """Return a list of n values with group sizes 1, 2 and >= 3."""
    out = []
    out.append(rng.randint(0, 1000))
    v2 = rng.randint(0, 1000)
    out.extend([v2, v2])
    v3 = rng.randint(0, 1000)
    out.extend([v3, v3, v3])
    while len(out) < n:
        out.append(rng.randint(0, 1000))
    rng.shuffle(out)
    return out[:n]


def _apply_null_rule(table, col, values, schema, rng, fallback=None):
    """Replace some values with NULL following the compact database's share (at least one NULL)."""
    if not rules.is_nullable(schema, table, col):
        return values
    n = len(values)
    if n == 0:
        return values
    share = rules.null_share(schema, table, col)
    n_null = max(1, int(round(n * share)))
    n_null = min(n_null, n)
    idx = list(range(n))
    rng.shuffle(idx)
    null_set = set(idx[:n_null])
    for i in range(n):
        if i in null_set:
            values[i] = None
        elif values[i] is None:
            if fallback:
                values[i] = rng.choice(fallback)
            else:
                values[i] = 0
    return values


def _apply_near_variants(table, col, values, rng, share=0.05):
    """~5% share near-variants (case changes, one-char edits)."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:k]:
        if values[i] is not None:
            values[i] = rules.near_variant(values[i], rng)
    return values


def _apply_value_rules(table, col, values, rng):
    """Repair values that violate single-column rules (by construction, in Python)."""
    for i, v in enumerate(values):
        if v is None:
            continue
        if not rules.value_ok(table, col, v):
            rng_ = rules.INT_RANGES.get((table, col))
            if rng_ is not None:
                try:
                    values[i] = max(rng_[0], min(rng_[1], int(v)))
                    continue
                except (TypeError, ValueError):
                    pass
            ep = rules.ENUMS.get((table, col))
            if ep:
                values[i] = rng.choice(ep)
                continue
            if (table, col) in rules.NONNEG:
                try:
                    values[i] = max(0, v)
                    continue
                except TypeError:
                    pass
            if (table, col) in rules.POSITIVE:
                try:
                    values[i] = max(1, v)
                    continue
                except TypeError:
                    pass
            if (table, col) in rules.RATE:
                try:
                    values[i] = max(0.0, min(1.0, float(v)))
                    continue
                except (TypeError, ValueError):
                    pass
    return values


def _apply_cross_rules(table, columns, rng):
    """Repair rows that violate cross-column rules (by construction, in Python)."""
    n = len(next(iter(columns.values()))) if columns else 0
    for i in range(n):
        row = {c: columns[c][i] for c in columns}
        if rules.row_ok(table, row):
            continue
        if table == 'player' and 'debut' in row and 'final_game' in row:
            if row['debut'] is not None and row['final_game'] is not None and row['debut'] > row['final_game']:
                columns['final_game'][i] = row['debut']
        elif table in ('team', 'manager', 'team_half', 'manager_half') and 'w' in row and 'l' in row and 'g' in row:
            w, l, g = row.get('w'), row.get('l'), row.get('g')
            if w is not None and l is not None and g is not None and w + l > g:
                columns['g'][i] = w + l
        elif table in ('batting', 'batting_postseason') and 'h' in row and 'ab' in row:
            h, ab = row.get('h'), row.get('ab')
            if h is not None and ab is not None and h > ab:
                columns['ab'][i] = h
        elif table in ('pitching', 'pitching_postseason') and 'gs' in row and 'g' in row:
            gs, g = row.get('gs'), row.get('g')
            if gs is not None and g is not None and gs > g:
                columns['g'][i] = gs
        elif table == 'home_game' and 'span_first' in row and 'span_last' in row:
            sf, sl = row.get('span_first'), row.get('span_last')
            if sf is not None and sl is not None and sf > sl:
                columns['span_last'][i] = sf
    return columns


def _plant_column(table, col, values, n, rng):
    """Plant boundary / literal / enum / duplicate / tie / group-size values LAST."""
    planted = None
    if (table, col) in rules.BOUNDARY_VALUES:
        planted = _plant_boundary_values(table, col, n, rng)
    elif (table, col) in rules.LITERAL_POOLS:
        planted = _plant_literal_pool(table, col, n, rng)
    elif (table, col) in rules.ENUMS:
        planted = _plant_enum(table, col, n, rng)
    elif (table, col) in DUPLICATE_COLUMNS:
        planted = _plant_duplicates(table, col, n, rng)
    elif (table, col) in TIE_COLUMNS:
        planted = _plant_tie(table, col, n, rng)
    elif (table, col) in GROUP_SIZE_COLUMNS:
        planted = _plant_group_sizes(table, col, n, rng)
    if planted is not None:
        return planted
    return values


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification rules by construction."""
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
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        for cm in tm.columns:
            col = cm.name
            if col not in cols:
                continue
            cols[col] = _apply_value_rules(t, col, cols[col], rng)
            cols[col] = _apply_near_variants(t, col, cols[col], rng)
            cols[col] = _plant_column(t, col, cols[col], n, rng)
            fallback = None
            if (t, col) in schema.fks:
                pt, pc = schema.fks[(t, col)]
                fallback = inst.get(pt, {}).get(pc) or None
            cols[col] = _apply_null_rule(t, col, cols[col], schema, rng, fallback)
        cols = _apply_cross_rules(t, cols, rng)
        inst[t] = cols
    for (t, col) in ORPHAN_FK_COLUMNS:
        if t not in inst or col not in inst[t]:
            continue
        pt, pc = schema.fks.get((t, col), (None, None))
        if pt is None:
            continue
        parent_vals = inst.get(pt, {}).get(pc) or []
        if not parent_vals:
            continue
        vals = inst[t][col]
        n = len(vals)
        k = max(1, int(round(n * ORPHAN_SHARE)))
        idx = list(range(n))
        rng.shuffle(idx)
        for i in idx[:k]:
            if vals[i] is not None:
                vals[i] = 'ORPHAN' + str(rng.randint(0, 999))
    return {t: inst[t] for t in schema.tables}
