"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

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
        if cm.unique and cm.name in columns and not (cm.pk_pos > 0):
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
    """Specification table sizes (people=10, gymnast=7) with small per-instance variation."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
            sizes[t] = max(0, base + rng.randint(-1, 2))
        else:
            sizes[t] = base
    np_ = sizes.get('people')
    if np_ is not None and 'gymnast' in sizes:
        max_gym = max(0, np_ - spec.MIN_UNMATCHED_PEOPLE)
        sizes['gymnast'] = min(sizes['gymnast'], max_gym)
    return sizes


def _round(v: float, step: float) -> float:
    return round(round(v / step) * step, 6)


def _score(rng) -> float:
    lo, hi = spec.SCORE_RANGE
    return _round(rng.uniform(lo, hi), spec.SCORE_STEP)


def _measure(rng, lo: float, hi: float) -> float:
    return _round(rng.uniform(lo, hi), spec.MEASURE_STEP)


def _name(rng) -> str:
    """text_name: pool of realistic names, ~15% near-duplicate variants."""
    if rng.random() < 0.15:
        bases = [k for k in spec.NAME_VARIANTS if spec.NAME_VARIANTS[k]]
        return rng.choice(spec.NAME_VARIANTS[rng.choice(bases)])
    return rng.choice(spec.NAME_POOL)


def _place(rng) -> str:
    """text_place: small city pool, ~10% case variants."""
    u = rng.random()
    if u < 0.10:
        return rng.choice(spec.PLACE_VARIANTS['Santo Domingo'])
    return rng.choice(spec.PLACE_POOL)


def _age(rng) -> float:
    """comparison_boundary: include 19,20,21,22; otherwise weighted toward 19-24."""
    if rng.random() < 0.40:
        return rng.choice(spec.AGE_BOUNDARY)
    if rng.random() < 0.70:
        return float(rng.randint(19, 24))
    lo, hi = spec.AGE_RANGE
    return float(rng.randint(int(lo), int(hi)))


def _height(rng) -> float:
    lo, hi = spec.HEIGHT_RANGE
    return _round(rng.uniform(lo, hi), spec.MEASURE_STEP)


def _total_points(rng) -> float:
    """literal_pool: values around 57.5 (57.4, 57.5, 57.6) plus range [50,60]."""
    if rng.random() < 0.50:
        return rng.choice(spec.TOTAL_POINTS_LITERALS)
    lo, hi = spec.TOTAL_RANGE
    return _round(rng.uniform(lo, hi), spec.SCORE_STEP)


def _apply_null_rule(columns: dict, table_meta, table: str, rng) -> dict:
    """NULL rule: only spec.NULL_TARGETS (empty for this DB) get NULLs."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in table_meta.columns:
        if cm.name not in columns:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        share = spec.NULL_TARGETS.get((table, cm.name), 0.0)
        if share <= 0.0:
            continue
        k = max(1, int(round(n * share)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        col = list(columns[cm.name])
        for i in idx:
            col[i] = None
        columns[cm.name] = col
    return columns


def _hometown_assignment(rng, n: int) -> list:
    """Aggregate + comparison boundary for Hometown, deterministic per instance."""
    pool = list(spec.PLACE_POOL)
    pool.append('santo domingo')
    rng.shuffle(pool)
    if 'Santo Domingo' in pool:
        pool.remove('Santo Domingo')
    pool.insert(0, 'Santo Domingo')
    n_groups = max(4, min(len(pool), n))
    pool = pool[:n_groups]
    if 'santo domingo' not in pool and len(pool) > 1:
        pool[-1] = 'santo domingo'
    sizes = list(spec.HOMETOWN_GROUP_SIZES)
    for _ in range(n_groups - len(sizes)):
        sizes.append(1)
    total = sum(sizes)
    if total < n:
        extra = n - total
        bumped = False
        for i, v in enumerate(pool):
            if sizes[i] == 1 and v not in ('Santo Domingo', 'santo domingo'):
                sizes[i] += extra
                bumped = True
                break
        if not bumped and n_groups >= 1:
            sizes[-1] += extra
    elif total > n:
        need = total - n
        for i in range(len(sizes) - 1, 3, -1):
            take = min(need, sizes[i] - 1)
            sizes[i] -= take
            need -= take
            if need <= 0:
                break
        if need > 0:
            i3 = sizes.index(3)
            take = min(need, sizes[i3] - 2)
            sizes[i3] -= take
            need -= take
        if need > 0:
            i2 = sizes.index(2)
            take = min(need, sizes[i2] - 1)
            sizes[i2] -= take
            need -= take
    values = []
    for v, k in zip(pool, sizes):
        values.extend([v] * k)
    while len(values) < n:
        v = rng.choice([p for p in spec.PLACE_POOL])
        values.append(v)
    values = values[:n]
    rng.shuffle(values)
    return values


def _name_assignment(rng, n: int) -> list:
    """Name duplicate share: >= 3 names repeated twice (20-50% duplicate share)."""
    distinct = []
    target_dupes = min(spec.NAME_DUPLICATE_GROUPS, n // 2)
    chosen = rng.sample(spec.NAME_POOL, min(len(spec.NAME_POOL), target_dupes + (n - 2 * target_dupes)))
    dupes = chosen[:target_dupes]
    rest = chosen[target_dupes:]
    vals = list(dupes) + list(dupes)
    for v in rest:
        vals.append(v)
    while len(vals) < n:
        if rng.random() < 0.5 and dupes:
            vals.append(rng.choice(dupes))
        else:
            vals.append(rng.choice(spec.NAME_POOL))
    vals = vals[:n]
    rng.shuffle(vals)
    return vals


def _people_rows(schema, n: int, rng, start_id: int) -> dict:
    """Generate `n` people rows with fresh People_IDs starting at start_id."""
    tm = schema.tables['people']
    ids = list(range(start_id, start_id + n))
    names = _name_assignment(rng, n)
    ages = [_age(rng) for _ in range(n)]
    if n >= len(spec.AGE_BOUNDARY):
        for k, v in enumerate(spec.AGE_BOUNDARY):
            ages[k] = v
    heights = [_height(rng) for _ in range(n)]
    places = _hometown_assignment(rng, n)
    cols = {'People_ID': ids, 'Name': names, 'Age': ages, 'Height': heights, 'Hometown': places}
    cols = _apply_null_rule(cols, tm, 'people', rng)
    if n >= 3:
        hs = [h for h in cols['Height'] if h is not None]
        if hs:
            mx = max(hs)
            idx = [i for i, h in enumerate(cols['Height']) if h is not None][:2]
            for i in idx:
                cols['Height'][i] = mx
    return cols


def _choose_gymnast_fk_subset(rng, people: dict, n_gym: int) -> list:
    """Pick people ids for gymnast rows so that:"""
    ids = people.get('People_ID', [])
    ht = people.get('Hometown', [])
    by_h: dict = {}
    for pid, h in zip(ids, ht):
        by_h.setdefault(h, []).append(pid)
    groups = sorted(by_h.items(), key=lambda kv: kv[0])
    if not groups:
        return []
    rng.shuffle(groups)
    used_ids: list = []
    plan = [3, 2, 1]
    g_idx = 0
    for want in plan:
        while g_idx < len(groups) and len(groups[g_idx][1]) < want:
            g_idx += 1
        if g_idx >= len(groups):
            break
        _, pids = groups[g_idx]
        take = rng.sample(pids, want)
        used_ids.extend(take)
        g_idx += 1
    remaining = [p for p in ids if p not in used_ids]
    rng.shuffle(remaining)
    need = n_gym - len(used_ids)
    if need > 0 and remaining:
        used_ids.extend(remaining[:need])
    used_ids = used_ids[:n_gym]
    max_used = max(0, len(ids) - spec.MIN_UNMATCHED_PEOPLE)
    if len(used_ids) > max_used:
        used_ids = used_ids[:max_used]
    return used_ids


def _gymnast_rows(schema, n: int, rng, people: dict) -> dict:
    """Generate `n` gymnast rows referencing existing people ids (FK)."""
    tm = schema.tables['gymnast']
    if not people or not people.get('People_ID'):
        return {}
    ids = _choose_gymnast_fk_subset(rng, people, n)
    if not ids:
        return {}
    cols = {'Gymnast_ID': ids}
    for c in spec.SCORE_COLUMNS:
        cols[c] = [_score(rng) for _ in range(len(ids))]
    cols['Total_Points'] = [_total_points(rng) for _ in range(len(ids))]
    cols = _apply_null_rule(cols, tm, 'gymnast', rng)
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as *appended* rows over the compact DB."""
    if size is None:
        size = choose_table_sizes(schema, rng)

    inst: dict = {}

    if 'people' in schema.tables:
        n_people = int(size.get('people', 0))
        existing = [v for v in schema.original_values.get(('people', 'People_ID'), []) if v is not None]
        start = (max(existing) + 1) if existing else 1
        inst['people'] = _people_rows(schema, n_people, rng, start)

    if 'gymnast' in schema.tables:
        n_people_gen = len(inst.get('people', {}).get('People_ID', []))
        n_gym = min(int(size.get('gymnast', 0)),
                    max(0, n_people_gen - spec.MIN_UNMATCHED_PEOPLE))
        if n_people_gen > 0 and n_gym > 0:
            inst['gymnast'] = _gymnast_rows(schema, n_gym, rng, inst['people'])

    for t, tm in schema.tables.items():
        if t in inst:
            continue
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                              schema.original_values.get((t, cm.name), []), 0.2, rng,
                              len(tm.primary_key))
            cols[cm.name] = [s.sample() for _ in range(n)]
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = _apply_null_rule(cols, tm, t, rng)
        inst[t] = cols

    for t, tm in schema.tables.items():
        if t not in inst:
            continue
        cols = inst[t]
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols

    return inst
