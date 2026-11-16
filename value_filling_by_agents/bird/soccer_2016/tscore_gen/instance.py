"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, reserved: set) -> dict:
    """Drop rows whose PK tuple repeats or collides with a compact row (first occurrence kept)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(reserved), []
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        if not pv:
            out[cm.name] = [None] * n
            continue
        share = null_share.get(key, 0.0) if not cm.notnull else 0.0
        vals = []
        for _ in range(n):
            if share > 0 and rng.random() < share:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        if share > 0 and all(v is not None for v in vals) and n > 0:
            vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Round 1: spec.TABLE_SIZES with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.table_size(t)
        if t in spec.REFERENCE_TABLES:
            sizes[t] = base
        else:
            jitter = int(base * 0.1)
            sizes[t] = max(0, base + rng.randint(-jitter, jitter))
    return sizes


def _null_share(schema, table: str, column: str) -> float:
    """NULL share from the compact database's share, clamped to [0.05, 0.30] for NULL targets."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.1
    share = sum(1 for v in vals if v is None) / len(vals)
    if spec.is_null_target(table, column):
        return min(0.30, max(0.05, share if share > 0 else 0.1))
    return share


def _apply_null_rule(table: str, columns: dict, schema, rng) -> dict:
    """For every nullable column, plant NULLs at the compact share (>= 1 NULL row)."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in columns:
            continue
        share = _null_share(schema, table, cm.name)
        if share <= 0:
            continue
        vals = columns[cm.name]
        for i in range(n):
            if rng.random() < share:
                vals[i] = None
        if all(v is not None for v in vals):
            vals[rng.randrange(n)] = None
    return columns


def _derive_season_caps(instance: dict, schema, rng) -> None:
    """Season caps (Man_of_the_Series / Orange_Cap / Purple_Cap) are player ids held in memory."""
    players = list(schema.original_values.get(('Player', 'Player_Id'), []))
    players += list(instance.get('Player', {}).get('Player_Id') or [])
    players = [p for p in players if p is not None]
    if not players or 'Season' not in instance:
        return
    cols = instance['Season']
    n = len(cols.get('Season_Id', []))
    for c in ('Man_of_the_Series', 'Orange_Cap', 'Purple_Cap'):
        if c in cols:
            cols[c] = [rng.choice(players) for _ in range(n)]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) on top of the compact database."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), table=t)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        null_share = {k: _null_share(schema, k[0], k[1]) for k in schema.fks if k[0] == t}
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, null_share))
        cols = _apply_null_rule(t, cols, schema, rng)
        reserved = set()
        if tm.primary_key:
            ov = schema.original_values
            m = len(ov.get((t, tm.primary_key[0]), [])) if tm.primary_key else 0
            for i in range(m):
                reserved.add(tuple(ov.get((t, c), [None] * m)[i] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, reserved)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    _derive_season_caps(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
