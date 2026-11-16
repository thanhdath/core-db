"""Random instance construction (fuzz/fuzz.py:83-196) + specification rules by construction."""
from .values import build_spec_sampler

_NULL_SHARE = {
    ('gender_age', 'gender'): 0.597, ('gender_age', 'age'): 0.597, ('gender_age', 'group'): 0.597,
    ('events_relevant', 'device_id'): 1.0,
}
_DEFAULT_NULL_SHARE = 0.10


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pk: set = None) -> dict:
    """Drop rows whose PK tuple repeats (first occurrence kept) or collides with a compact row."""
    if not table_meta.primary_key or not columns:
        return columns
    compact_pk = compact_pk or set()
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen and k not in compact_pk:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_unique: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    compact_unique = compact_unique or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(compact_unique.get((table_meta.name, cm.name), ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v is None or v not in seen:
                    if v is not None:
                        seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_values: dict = None) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    compact_values = compact_values or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += [v for v in compact_values.get((pt, pc), []) if v is not None]
        pv = [v for v in pv if v is not None]
        nullable = not cm.notnull and cm.pk_pos == 0
        null_share = _NULL_SHARE.get(key, _DEFAULT_NULL_SHARE) if nullable else 0.0
        vals = []
        for _ in range(n):
            if nullable and rng.random() < null_share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
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


def _plant_nulls(values: list, share: float, rng) -> list:
    """NULL rule: NULL is a value to generate; at least one NULL row per nullable column."""
    if not values:
        return values
    out = list(values)
    n = len(out)
    k = int(round(share * n))
    if k < 1:
        k = 1
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        out[i] = None
    return out


def _fresh_int_keys(schema, table: str, column: str, n: int, rng) -> list:
    """Fresh sequential integers starting above the compact max (never NULL)."""
    start = int(schema.compact_max_int.get((table, column), 0)) + 1
    return [start + i for i in range(n)]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    null_shares = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t, cm.name)
            share = _NULL_SHARE.get(key, _DEFAULT_NULL_SHARE) if (not cm.notnull and cm.pk_pos == 0) else 0.0
            max_l0 = float('inf')
            if rng.random() < 0.5:
                max_l0 = rng.random() * 30
                if cm.pk_pos > 0:
                    max_l0 = float('inf') if len(tm.primary_key) == 1 else 30
            s, share = build_spec_sampler(t, cm, literal_pool.get(key, []),
                                          schema.original_values.get(key, []), p, rng, max_l0, share)
            samplers[key] = s
            null_shares[key] = share
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in samplers:
                vals = [samplers[key].sample() for _ in range(n)]
                if null_shares.get(key, 0.0) > 0.0:
                    vals = _plant_nulls(vals, null_shares[key], rng)
                cols[cm.name] = vals
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, schema.original_values))
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            pcm = next((c for c in tm.columns if c.name == pk), None)
            if pcm is not None and 'int' in (pcm.type_str or '').lower():
                cols[pk] = _fresh_int_keys(schema, t, pk, n, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         schema.compact_pk.get(t))
        cols = drop_unique_duplicates(tm, cols, schema.compact_unique)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
