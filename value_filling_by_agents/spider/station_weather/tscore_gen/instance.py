"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import re

from .values import _init_sampler, parse_domain, DAYS

SPEC_SIZES = {'train': 8, 'station': 8, 'route': 12, 'weekly_weather': 12}
SPEC_RULES = {
    ('train', 'id'): ['id > 0'],
    ('train', 'train_number'): ['train_number > 0'],
    ('train', 'time'): ["time GLOB '[0-2][0-9]:[0-5][0-9]'"],
    ('train', 'interval'): ["interval IN ('Daily')"],
    ('station', 'id'): ['id > 0'],
    ('route', 'train_id'): ['train_id > 0'],
    ('route', 'station_id'): ['station_id > 0'],
    ('weekly_weather', 'station_id'): ['station_id > 0'],
    ('weekly_weather', 'day_of_week'): ["day_of_week IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')"],
    ('weekly_weather', 'high_temperature'): ['high_temperature BETWEEN -50 AND 130'],
    ('weekly_weather', 'low_temperature'): ['low_temperature BETWEEN -50 AND 130', 'low_temperature <= high_temperature'],
    ('weekly_weather', 'precipitation'): ['precipitation >= 0'],
    ('weekly_weather', 'wind_speed_mph'): ['wind_speed_mph >= 0'],
}
SPEC_BOUNDARIES = {
    ('weekly_weather', 'precipitation'): [-38, -37, -36, 49, 50, 51],
}
SPEC_EQUALITY = {
    ('station', 'network_name'): ['Amersham', 'amersham'],
    ('station', 'services'): ['Metropolitan line and Chiltern Railways',
                              'metropolitan line and chiltern railways'],
}


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
    """Specification sizes with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = SPEC_SIZES.get(t, 8)
        jitter = rng.randint(-2, 2)
        sizes[t] = max(1, min(230, base + jitter))
    return sizes


def _group_size_plan(n: int, rng) -> list:
    """Return a list of group sizes covering n rows with sizes 1, 2 and >= 3."""
    plan = [1, 2, max(3, n - 3)]
    while sum(plan) < n:
        plan.append(rng.choice([1, 2, 3, 4]))
    while sum(plan) > n and len(plan) > 3:
        plan.pop()
    if sum(plan) > n:
        plan[-1] -= sum(plan) - n
    return [p for p in plan if p > 0]


def _assign_groups(parent_ids: list, n: int, rng) -> list:
    """Assign n child rows to parent ids so that group sizes are 1, 2 and >= 3."""
    if not parent_ids:
        return [None] * n
    plan = _group_size_plan(n, rng)
    parents = list(parent_ids)
    rng.shuffle(parents)
    out = []
    for k, g in enumerate(plan):
        p = parents[k % len(parents)]
        out.extend([p] * g)
    rng.shuffle(out)
    return out[:n]


def _plant_nulls(cols: dict, cm, n: int, share: float, rng) -> None:
    """NULL rule: at least one NULL, share following the compact database's share."""
    if cm.notnull or cm.pk_pos > 0:
        return
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        cols[cm.name][i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    domains = {}
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                dom = parse_domain(cm, SPEC_RULES.get((t, cm.name), []))
                for b in SPEC_BOUNDARIES.get((t, cm.name), []):
                    if b not in dom.boundaries:
                        dom.boundaries.append(b)
                if (t, cm.name) in SPEC_EQUALITY:
                    dom.enum = list(SPEC_EQUALITY[(t, cm.name)])
                domains[(t, cm.name)] = dom
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), domain=dom)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        if t == 'route':
            train_ids = inst.get('train', {}).get('id') or []
            station_ids = inst.get('station', {}).get('id') or []
            cols['train_id'] = _assign_groups(train_ids, n, rng)
            cols['station_id'] = _assign_groups(station_ids, n, rng)
        elif t == 'weekly_weather':
            station_ids = inst.get('station', {}).get('id') or []
            cols['station_id'] = _assign_groups(station_ids, n, rng)
            days = list(DAYS)
            rng.shuffle(days)
            cols['day_of_week'] = [days[i % 7] for i in range(n)]
        else:
            cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        if t == 'weekly_weather' and 'low_temperature' in cols and 'high_temperature' in cols:
            hi = cols['high_temperature']
            lo = cols['low_temperature']
            for i in range(n):
                if hi[i] is not None and lo[i] is not None and lo[i] > hi[i]:
                    lo[i] = hi[i] - rng.randint(0, 5)
        for cm in tm.columns:
            if cm.name in cols:
                _plant_nulls(cols, cm, n, schema.null_share.get((t, cm.name), 0.0), rng)
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                existing = [r[0] for r in schema.pk_values.get(t, []) if r and r[0] is not None]
                start = (max(existing) + 1) if existing else 1
                for i in range(n):
                    if cols[pk][i] is not None:
                        cols[pk][i] = start + i
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
    return {t: inst[t] for t in schema.tables}
