"""Random instance construction that appends rows to compact data."""
import random

from .values import _init_sampler

SPEC_SIZES = {'genre': 12, 'platform': 31, 'publisher': 40, 'region': 4,
              'game': 60, 'game_publisher': 80, 'game_platform': 100, 'region_sales': 120}

NULLABLE = {
    ('game', 'genre_id'): True,
    ('game', 'game_name'): True,
    ('game_publisher', 'game_id'): True,
    ('game_publisher', 'publisher_id'): True,
    ('game_platform', 'game_publisher_id'): True,
    ('game_platform', 'platform_id'): True,
    ('game_platform', 'release_year'): True,
    ('region_sales', 'region_id'): True,
    ('region_sales', 'game_platform_id'): True,
    ('region_sales', 'num_sales'): True,
}

BOUNDARIES = {
    ('game', 'id'): [74, 75, 76, 10030, 10031, 10032],
    ('game', 'genre_id'): [1, 2, 3],
    ('game', 'game_name'): ['ModNation Racers', 'modnation racers', 'Panzer Tactics', 'panzer tactics',
                            'FIFA 07', 'fifa 08', 'Marvel Ultimate Alliance'],
    ('game_publisher', 'id'): [6656, 6657, 6658, 10030, 10031, 10032],
    ('game_publisher', 'game_id'): [74, 75, 76, 10030, 10031, 10032],
    ('game_publisher', 'publisher_id'): [463, 464, 465],
    ('game_platform', 'id'): [25, 26, 27, 9657, 9658, 9659],
    ('game_platform', 'game_publisher_id'): [6656, 6657, 6658],
    ('game_platform', 'release_year'): [1999, 2000, 2001, 2002, 2003, 2006, 2007, 2008],
    ('publisher', 'id'): [463, 464, 465],
    ('publisher', 'publisher_name'): ['Culture Brain', 'culture brain', 'Atari', 'atari', 'Athena', 'athena',
                                       '10TACLE Studios', '10tacle studios', 'Brash Entertainment',
                                       'Electronic Arts'],
    ('genre', 'id'): [1, 2, 3],
    ('genre', 'genre_name'): ['Sports', 'sports', 'Strategy', 'strategy', 'Adventure', 'adventure',
                               'Simulation', 'simulation', 'Shooter', 'Role-Playing', 'Puzzle'],
    ('platform', 'platform_name'): ['PS3', 'ps3', 'X360', 'x360', 'PS4', 'ps4', 'PSP', 'psp', 'Wii', 'DS'],
    ('region', 'id'): [1, 2, 3],
    ('region', 'region_name'): ['Europe', 'europe', 'North America', 'north america', 'Japan', 'japan', 'Other'],
    ('region_sales', 'region_id'): [1, 2, 3, 4, 5],
    ('region_sales', 'game_platform_id'): [25, 26, 27, 9657, 9658, 9659],
    ('region_sales', 'num_sales'): [2.99, 3, 3.01, 3.49, 3.5, 3.51],
}

DUP_COLUMNS = {
    ('game', 'id'), ('game', 'game_name'), ('game_publisher', 'game_id'),
    ('game_publisher', 'publisher_id'), ('game_platform', 'id'), ('game_platform', 'game_publisher_id'),
    ('publisher', 'id'), ('publisher', 'publisher_name'), ('genre', 'genre_name'),
    ('platform', 'platform_name'), ('region', 'region_name'),
}

TIE_COLUMNS = {
    ('game', 'id'), ('game', 'game_name'), ('game_publisher', 'game_id'),
    ('game_publisher', 'publisher_id'), ('game_platform', 'id'), ('game_platform', 'release_year'),
    ('publisher', 'id'), ('publisher', 'publisher_name'), ('genre', 'genre_name'),
    ('platform', 'platform_name'), ('region', 'region_name'), ('region_sales', 'num_sales'),
    ('region_sales', 'game_platform_id'),
}

SINGLE_COL = {'genre': 'genre_name', 'platform': 'platform_name', 'publisher': 'publisher_name',
              'region': 'region_name'}


def compact_state(schema) -> dict:
    """Per table: existing PK tuples and copies of compact rows."""
    st = {}
    for t, tm in schema.tables.items():
        rows = schema.compact_rows.get(t, [])
        pks = [tuple(r[c] for c in tm.primary_key) for r in rows]
        st[t] = {'pks': set(pks), 'rows': [dict(r) for r in rows]}
    return st


def _max_pk(schema, state, t):
    tm = schema.tables[t]
    cols = tm.primary_key
    if len(cols) != 1 or not state[t]['rows']:
        return 0
    c = cols[0]
    vals = [r[c] for r in state[t]['rows'] if isinstance(r[c], (int, float))]
    return int(max(vals)) if vals else 0


def choose_table_sizes(schema, rng) -> dict:
    """Use the spec per-table append counts directly (no size roll)."""
    return dict(SPEC_SIZES)


def _value_sampler(schema, t, cm, pool, rng, n_pk, state):
    key = (t, cm.name)
    lit_pool = list(pool.get(key, [])) if pool else []
    ov = list(schema.original_values.get(key, []))
    if key in BOUNDARIES:
        ov = list(BOUNDARIES[key]) + ov
    p = 0.0 if cm.checked else (0.0 if rng.random() < 0.3 else 0.2)
    max_l0 = float('inf')
    if rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if cm.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return _init_sampler(cm, lit_pool, ov, p, rng, n_pk, max_l0)


def _fill_null(cols_vals, n, rng, share=0.2, fallback=None):
    """Force at least one NULL and one non-NULL for a nullable column."""
    out = list(cols_vals)
    nnull = max(1, int(n * share))
    idx = rng.sample(range(n), min(n, nnull + 1))
    null_idx = idx[:min(len(idx), nnull)]
    nn_idx = idx[nnull:]
    for i in null_idx:
        out[i] = None
    if nn_idx and out[nn_idx[0]] is None:
        out[nn_idx[0]] = fallback if fallback is not None else 'x'
    return out


def _fk_values(schema, t, cm, n, rng, state, parents, reserved):
    key = (t, cm.name)
    pt, pc = schema.fks[key]
    pv_all = [r[pc] for r in state[pt]['rows'] if r[pc] is not None]
    pv_gen = parents.get(pt, [])
    pv = (pv_gen or []) + pv_all
    if len(pv) > 1:
        pv = pv[:-1]
    share = 0.15
    res = []
    for _ in range(n):
        if rng.random() < share or not pv:
            res.append(None)
        else:
            res.append(rng.choice(pv))
    if pv:
        res = _fill_null(res, n, rng, share=share, fallback=rng.choice(pv))
    return res


def _boundary_values(key, n, rng, base_sampler):
    vals = BOUNDARIES.get(key)
    if not vals:
        return None
    out = []
    while len(out) < n:
        b = rng.choice(vals)
        out.append(b)
        out.append(base_sampler.sample())
    return out[:n]


def _ensure_ties(cols, column, rng):
    """Force >=2 equal top values for tie columns."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2 or column not in cols:
        return
    col = cols[column]
    if not col:
        return
    top = col[0]
    col[1] = top


def _ensure_duplicates(cols, column, rng, share=0.3):
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 3 or column not in cols:
        return
    col = cols[column]
    k = max(1, int(n * share))
    if k >= n:
        k = n - 1
    for i in range(1, k):
        col[i] = col[0]


def build_random_instance(schema, literal_pool: dict, size, rng, state=None) -> dict:
    if size is None:
        size = SPEC_SIZES
    if state is None:
        state = compact_state(schema)
    order = [t for lvl in schema.table_order for t in lvl]
    parents: dict = {}
    inst: dict = {}
    reserved: dict = {}
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        n_pk = len(tm.primary_key)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            samplers[(t, cm.name)] = _value_sampler(schema, t, cm, literal_pool, rng, n_pk, state)

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        pk_cols = tm.primary_key
        cols: dict = {}
        pk_offset = _max_pk(schema, state, t)
        pk_seq = list(range(pk_offset + 1, pk_offset + 1 + n))
        for cm in tm.columns:
            if cm.name in pk_cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            bs = samplers[(t, cm.name)]
            vals = [bs.sample() for _ in range(n)]
            key = (t, cm.name)
            if key in BOUNDARIES:
                bv = _boundary_values(key, n, rng, bs)
                if bv is not None:
                    for i, v in enumerate(bv):
                        vals[i] = v
            cols[cm.name] = vals
        for cm in tm.columns:
            if cm.name in pk_cols:
                if len(pk_cols) == 1:
                    cols[cm.name] = pk_seq
                else:
                    cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            key = (t, cm.name)
            vals = _fk_values(schema, t, cm, n, rng, state, parents, reserved)
            if key in BOUNDARIES:
                pt, pc = schema.fks[key]
                parent_vals = {r[pc] for r in state[pt]['rows'] if r[pc] is not None}
                parent_vals |= set(parents.get(pt, []))
                bv = [v for v in BOUNDARIES[key] if v in parent_vals]
                for i in range(min(n, len(bv))):
                    vals[i] = bv[i]
            cols[cm.name] = vals
        if len(pk_cols) == 1 and pk_cols[0] in cols:
            c = pk_cols[0]
            existing = state[t]['pks']
            seen = set()
            new_vals = []
            seq = pk_offset + 1
            for i in range(n):
                v = cols[c][i]
                tu = (v,)
                if tu in existing or v in seen:
                    while (seq,) in existing or seq in seen:
                        seq += 1
                    v = seq
                    seq += 1
                new_vals.append(v)
                seen.add(v)
            cols[c] = new_vals
        for cm in tm.columns:
            key = (t, cm.name)
            if not NULLABLE.get(key, False):
                continue
            if cm.name in cols:
                fallback = None
                if (t, cm.name) in schema.fks:
                    pt, pc = schema.fks[(t, cm.name)]
                    pv = [r[pc] for r in state[pt]['rows'] if r[pc] is not None]
                    pv += parents.get(pt, [])
                    if pv:
                        fallback = rng.choice(pv)
                cols[cm.name] = _fill_null(cols[cm.name], n, rng, share=0.15, fallback=fallback)
        for key in DUP_COLUMNS:
            if key[0] == t and key[1] in cols:
                _ensure_duplicates(cols, key[1], rng, share=0.3)
        for key in TIE_COLUMNS:
            if key[0] == t and key[1] in cols:
                _ensure_ties(cols, key[1], rng)
        if t == 'region_sales' and 'num_sales' in cols:
            col = cols['num_sales']
            if len(col) >= 3:
                col[0] = 3.5
                col[1] = 3.5
                col[2] = 3.49
        if t == 'game_platform' and 'release_year' in cols:
            col = cols['release_year']
            if n >= 3:
                col[0] = 1981
                col[1] = 1981
        inst[t] = cols
        parents[t] = [v for v in (cols.get(c) or []) for c in pk_cols] if len(pk_cols) == 1 else []
    return inst
