"""Random instance construction (fuzz/fuzz.py:83-196), adapted for append-to-compact."""
import datetime as dt

from .values import _init_sampler, make_column_sampler

_FIXED = {
    ('Episode', 'season'): 9,
    ('Episode', 'series'): 'Law and Order',
    ('Award', 'series'): 'Law and Order',
}
_ENUMS = {
    ('Award', 'result'): ['Winner', 'Nominee'],
    ('Award', 'organization'): ['International Monitor Awards', 'Primetime Emmy Awards',
                                 'American Bar Association Silver Gavel Awards for Media and the Arts',
                                 'Edgar Allan Poe Awards'],
    ('Award', 'award_category'): ['Monitor', 'Primetime Emmy', 'Silver Gavel Award', 'Edgar'],
    ('Credit', 'credited'): ['true', 'false'],
    ('Credit', 'category'): ['Additional Crew', 'Art Department', 'Camera and Electrical Department',
                             'Cast', 'Casting Department', 'Costume and Wardrobe Department',
                             'General', 'Directed by'],
}
_RANGES = {
    ('Episode', 'episode'): (1, 24),
    ('Episode', 'number_in_series'): (182, 205),
    ('Episode', 'rating'): (0.0, 10.0),
    ('Episode', 'votes'): (0, None),
    ('Person', 'height_meters'): (1.0, 2.5),
    ('Award', 'year'): (1990, 2010),
    ('Vote', 'stars'): (0, 10),
    ('Vote', 'votes'): (0, None),
    ('Vote', 'percent'): (0.0, 100.0),
}
_DATE_RANGES = {
    ('Episode', 'air_date'): ('1998-09-01', '1999-12-31'),
    ('Person', 'birthdate'): ('1900-01-01', '2030-12-31'),
}
_COPIED = {
    ('Award', 'series'): ('Episode', 'series'),
    ('Credit', 'series'): ('Episode', 'series'),
}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set = None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row); first kept."""
    if not table_meta.primary_key or not columns:
        return columns
    seen = set(existing or ())
    n = len(next(iter(columns.values())))
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict = None) -> dict:
    """Drop rows repeating any single unique column value (also against compact rows)."""
    existing = existing or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing.get(cm.name, ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   generated_only: bool = False) -> dict:
    """FK child columns draw from the parent's values with replacement; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if generated_only:
            pv = [v for v in pv if v is not None]
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
                sizes[t] = int(s)
            s *= 4
    return sizes


def _null_share(schema, t: str, col: str) -> float:
    """Compact NULL share for a column (0.0 if none observed)."""
    vals = schema.original_values.get((t, col), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _apply_null_rule(schema, t: str, cols: dict, n: int, rng) -> None:
    """Plant NULLs in every nullable column: share ~ compact share, at least one NULL row."""
    tm = schema.tables[t]
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        if n <= 0:
            continue
        share = _null_share(schema, t, cm.name)
        if share <= 0.0:
            share = rng.uniform(0.05, 0.10)
        k = int(round(share * n))
        k = max(1, min(n, k))
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None


def _clamp_num(v, lo, hi):
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return v
    if lo is not None and x < lo:
        x = lo
    if hi is not None and x > hi:
        x = hi
    return x


def _clamp_date(v, lo, hi):
    if v is None:
        return None
    s = str(v)[:10]
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        return v
    if s < lo:
        return lo
    if s > hi:
        return hi
    return s


def _apply_semantic_rules(schema, t: str, cols: dict, rng) -> None:
    """Enforce fixed values, enumerations, numeric and date ranges by construction."""
    tm = schema.tables[t]
    for cm in tm.columns:
        name = cm.name
        if name not in cols:
            continue
        key = (t, name)
        if key in _FIXED:
            cols[name] = [_FIXED[key] if v is not None else None for v in cols[name]]
        elif key in _ENUMS:
            pool = _ENUMS[key]
            cols[name] = [rng.choice(pool) if v is not None else None for v in cols[name]]
        elif key in _RANGES:
            lo, hi = _RANGES[key]
            is_int = 'int' in (cm.type_str or '').lower()
            out = []
            for v in cols[name]:
                x = _clamp_num(v, lo, hi)
                if x is not None and is_int:
                    x = int(round(x))
                out.append(x)
            cols[name] = out
        elif key in _DATE_RANGES:
            lo, hi = _DATE_RANGES[key]
            cols[name] = [_clamp_date(v, lo, hi) for v in cols[name]]


def _apply_copied_columns(instance: dict, schema, t: str, cols: dict, rng) -> None:
    """Copy parent columns to child rows via the FK (Award.series / Credit.series)."""
    for (ct, cc), (pt, pc) in _COPIED.items():
        if ct != t or cc not in cols:
            continue
        fk_col = None
        for cm in schema.tables[t].columns:
            if schema.fks.get((t, cm.name)) == (pt, schema.tables[pt].primary_key[0] if schema.tables[pt].primary_key else None):
                fk_col = cm.name
                break
        if fk_col is None:
            for cm in schema.tables[t].columns:
                fk = schema.fks.get((t, cm.name))
                if fk and fk[0] == pt:
                    fk_col = cm.name
                    break
        if fk_col is None or fk_col not in cols:
            continue
        parent_ids = instance.get(pt, {}).get(schema.tables[pt].primary_key[0] if schema.tables[pt].primary_key else None)
        parent_vals = instance.get(pt, {}).get(pc)
        if not parent_ids or not parent_vals:
            continue
        lookup = {}
        for pid, pv in zip(parent_ids, parent_vals):
            if pid is not None:
                lookup[pid] = pv
        new = []
        for fk_v in cols[fk_col]:
            if fk_v is None:
                new.append(None)
            else:
                new.append(lookup.get(fk_v))
        cols[cc] = new


def _apply_vote_percent(instance: dict, schema, rng) -> None:
    """Vote.percent = round(100 * votes / SUM(votes) over the same episode_id, 1)."""
    if 'Vote' not in instance:
        return
    cols = instance['Vote']
    if 'votes' not in cols or 'percent' not in cols or 'episode_id' not in cols:
        return
    totals: dict = {}
    for eid, v in zip(cols['episode_id'], cols['votes']):
        if eid is None or v is None:
            continue
        totals[eid] = totals.get(eid, 0) + v
    new = []
    for eid, v in zip(cols['episode_id'], cols['votes']):
        if eid is None or v is None:
            new.append(None)
            continue
        tot = totals.get(eid, 0)
        if tot <= 0:
            new.append(None)
        else:
            new.append(round(100.0 * v / tot, 1))
    cols['percent'] = new


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the NULL rule applied."""
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
        _apply_semantic_rules(schema, t, cols, rng)
        _apply_copied_columns(inst, schema, t, cols, rng)
        _apply_null_rule(schema, t, cols, n, rng)
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
    _apply_vote_percent(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
