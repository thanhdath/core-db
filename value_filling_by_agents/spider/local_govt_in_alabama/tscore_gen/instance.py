"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append-only instances."""
import random

from .values import _init_sampler, near_variants

SPEC_SIZES = {'Services': 15, 'Participants': 15, 'Events': 15, 'Participants_in_Events': 18}

SPEC_ENUMS = {
    ('Services', 'Service_Type_Code'): ['Marriage', 'Death Proof', 'Birth Proof', 'Property Change'],
    ('Participants', 'Participant_Type_Code'): ['Organizer', 'Participant'],
    ('Events', 'Event_Details'): ['Success', 'Fail'],
}

SPEC_NULL_TARGETS = [('Events', 'Event_Details'), ('Participants', 'Participant_Details')]

SPEC_EXACT_LITERALS = {('Participants', 'Participant_Details'): ['Kenyatta Kuhn', 'kenyatta kuhn']}

GROUP_COLUMNS = {
    ('Events', 'Event_Details'),
    ('Participants', 'Participant_Type_Code'),
    ('Services', 'Service_Type_Code'),
    ('Events', 'Event_ID'),
    ('Participants_in_Events', 'Event_ID'),
    ('Participants_in_Events', 'Participant_ID'),
    ('Participants', 'Participant_ID'),
    ('Services', 'Service_ID'),
}

DISTINCT_COLUMNS = {
    ('Events', 'Event_Details'),
    ('Participants', 'Participant_Type_Code'),
    ('Services', 'Service_Type_Code'),
    ('Participants', 'Participant_Details'),
    ('Events', 'Event_ID'),
    ('Participants_in_Events', 'Event_ID'),
}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, compact_keys: set = None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact key), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen = set(compact_keys or ())
    keep = []
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
                                   compact_fk: dict = None) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        if compact_fk and key in compact_fk:
            pv = list(compact_fk[key]) + pv
        if not pv:
            out[cm.name] = [None] * n
            continue
        pool = _small_set(pv, rng) if n > 1 else pv
        out[cm.name] = [rng.choice(pool) for _ in range(n)]
    return out


def _small_set(vals: list, rng) -> list:
    """A small set of parent ids (1..3 distinct) for multi-join reuse."""
    uniq = sorted({v for v in vals if v is not None}, key=lambda x: str(x))
    if not uniq:
        return vals
    k = min(len(uniq), rng.randint(1, 3))
    return rng.sample(uniq, k)


def _min_sizes(schema) -> dict:
    """Specification sizes, raised so the join / group-size targets are reachable."""
    sizes = dict(SPEC_SIZES)
    if 'Events' in schema.tables:
        sizes['Events'] = max(sizes.get('Events', 0), 18)
    if 'Participants_in_Events' in schema.tables:
        sizes['Participants_in_Events'] = max(sizes.get('Participants_in_Events', 0), 18)
    if 'Services' in schema.tables:
        sizes['Services'] = max(sizes.get('Services', 0), 8)
    if 'Participants' in schema.tables:
        sizes['Participants'] = max(sizes.get('Participants', 0), 6)
    return sizes


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes (as minima) when present, else upstream rand_lin / level x4."""
    sizes = {}
    if all(t in SPEC_SIZES for t in schema.tables):
        base = _min_sizes(schema)
        for t in schema.tables:
            b = base[t]
            if rng.random() < 0.5:
                sizes[t] = b
            else:
                sizes[t] = max(b, min(230, b + rng.randint(0, 3)))
        return sizes
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


def _group_size_plan(n: int, rng) -> list:
    """Group sizes 1, 2 and >= 3 by construction: return a list of group sizes summing to n."""
    if n <= 0:
        return []
    plan = [1, 2, 3]
    rest = n - sum(plan)
    while rest > 0:
        k = min(rest, rng.randint(1, 4))
        plan.append(k)
        rest -= k
    rng.shuffle(plan)
    return plan


def _apply_group_sizes(values: list, rng) -> list:
    """Re-arrange values so that group sizes 1, 2 and >= 3 occur (for group columns)."""
    if len(values) < 6:
        return values
    plan = _group_size_plan(len(values), rng)
    out = []
    for g in plan:
        v = rng.choice(values)
        out.extend([v] * g)
    return out[:len(values)]


def _distinct_cap(values: list, rng, share_lo=0.2, share_hi=0.5) -> list:
    """Duplicate share 20-50 %: cap the number of distinct values."""
    if not values:
        return values
    n = len(values)
    share = rng.uniform(share_lo, share_hi)
    cap = max(1, int(round(n * (1.0 - share))))
    uniq = []
    for v in values:
        if v not in uniq:
            uniq.append(v)
    if len(uniq) <= cap:
        return values
    keep = uniq[:cap]
    return [rng.choice(keep) for _ in values]


def _plant_nulls(values: list, share: float, rng) -> list:
    """NULL rule: at least one NULL, share following the compact share (min 1 row)."""
    if not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _fresh_pk_sequence(n: int, compact_keys: set, rng) -> list:
    """Fresh sequential integers starting at 1, unique per table, never colliding with compact keys."""
    used = set()
    for k in compact_keys or ():
        if isinstance(k, tuple) and len(k) == 1:
            used.add(k[0])
        else:
            used.add(k)
    out = []
    v = 1
    while len(out) < n:
        if v not in used:
            out.append(v)
            used.add(v)
        v += 1
    return out


def _apply_group_sizes_to_fk(values: list, rng) -> list:
    """Group sizes 1, 2, >= 3 for a foreign-key column while keeping every value a valid parent key."""
    if len(values) < 6:
        return values
    uniq = []
    for v in values:
        if v not in uniq:
            uniq.append(v)
    if len(uniq) < 3:
        return values
    plan = _group_size_plan(len(values), rng)
    out = []
    for g in plan:
        v = rng.choice(uniq)
        out.extend([v] * g)
    return out[:len(values)]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            enum = SPEC_ENUMS.get((t, cm.name))
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []), p, rng,
                len(tm.primary_key), enum=enum)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                   compact_fk=schema.compact_fk))
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            cols[pk] = _fresh_pk_sequence(n, schema.compact_keys.get(t, set()), rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         schema.compact_keys.get(t, set()))
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
            if (t, cm.name) in schema.fks or cm.pk_pos > 0:
                continue
            if (t, cm.name) in GROUP_COLUMNS:
                cols[cm.name] = _apply_group_sizes(cols[cm.name], rng)
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            if (t, cm.name) in GROUP_COLUMNS:
                cols[cm.name] = _apply_group_sizes_to_fk(cols[cm.name], rng)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks or cm.pk_pos > 0:
                continue
            if (t, cm.name) in DISTINCT_COLUMNS:
                cols[cm.name] = _distinct_cap(cols[cm.name], rng)
        for (tt, cc), lits in SPEC_EXACT_LITERALS.items():
            if tt == t and cc in cols and cols[cc]:
                idx = rng.randrange(len(cols[cc]))
                cols[cc][idx] = lits[0]
                if len(cols[cc]) > 1:
                    j = (idx + 1) % len(cols[cc])
                    cols[cc][j] = lits[1]
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            share = schema.null_share.get((t, cm.name), 0.0)
            if (t, cm.name) in SPEC_NULL_TARGETS:
                share = max(share, 1.0 / max(1, n))
            if share > 0 or (t, cm.name) in SPEC_NULL_TARGETS:
                cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
    return {t: inst[t] for t in schema.tables}
