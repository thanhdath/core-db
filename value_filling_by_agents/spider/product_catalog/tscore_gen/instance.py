"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt
import re

from .values import _init_sampler

ENUM_DOMAINS = {
    ('Attribute_Definitions', 'attribute_data_type'): ['Bool'],
    ('Catalog_Structure', 'catalog_level_name'): ['Category', 'Sub-Category', 'Product'],
    ('Catalog_Contents_Additional_Attributes', 'attribute_value'): ['0', '1'],
}
BOUNDARY_LITERALS = {
    ('Attribute_Definitions', 'attribute_data_type'): ['', 'x'],
    ('Catalog_Contents', 'length'): ['-5', '-4', '-3', '2', '3', '4'],
    ('Catalog_Contents', 'width'): ['4', '5', '6'],
    ('Catalog_Structure', 'catalog_level_number'): ['5', '6', '10', '11'],
}
LITERAL_POOL = {
    ('Attribute_Definitions', 'attribute_name'): ['Green'],
    ('Catalog_Contents', 'product_stock_number'): ['2%'],
}
DISTINCT_COLUMNS = [
    ('Attribute_Definitions', 'attribute_data_type'),
    ('Catalog_Contents', 'catalog_entry_name'),
    ('Catalogs', 'catalog_publisher'),
]
TIE_COLUMNS = [
    ('Catalog_Contents', 'price_in_dollars'),
    ('Catalog_Contents', 'price_in_euros'),
    ('Catalog_Contents', 'capacity'),
    ('Catalog_Contents', 'next_entry_id'),
    ('Catalogs', 'catalog_publisher'),
]
GROUP_COLUMNS = [
    ('Attribute_Definitions', 'attribute_data_type'),
    ('Catalog_Contents_Additional_Attributes', 'attribute_id'),
]
LIKE_NEAR = ('Catalogs', 'catalog_publisher', 'Murray', 'Mur')
NONNEG_COLUMNS = [
    ('Catalog_Contents', 'price_in_dollars'),
    ('Catalog_Contents', 'price_in_euros'),
    ('Catalog_Contents', 'price_in_pounds'),
]
DATE_ORDER = ('Catalogs', 'date_of_publication', 'date_of_latest_revision')
SELF_REFS = ['parent_entry_id', 'previous_entry_id', 'next_entry_id']


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows); first kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    taken = taken or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v is None or v not in seen:
                    if v is not None:
                        seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: dict = None) -> dict:
    """FK child columns draw from the parent's compact+generated values; NULL per the NULL rule."""
    null_share = null_share or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        share = null_share.get(key, 0.0)
        vals = []
        for _ in range(n):
            if pv and rng.random() >= share:
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


def _spec_sizes(schema, rng) -> dict:
    """Table sizes per instance: the specification's table_sizes_per_instance, jittered 0-230."""
    base = {'Attribute_Definitions': 4, 'Catalogs': 8, 'Catalog_Structure': 3,
            'Catalog_Contents': 15, 'Catalog_Contents_Additional_Attributes': 15}
    out = {}
    for t in schema.tables:
        b = base.get(t)
        if b is None:
            out[t] = rng.randint(0, 30)
        else:
            out[t] = max(0, b + rng.randint(-2, 6))
    return out


def _enum_domain(schema, key) -> list:
    """Closed domain for a column: declared enum, else a small observed distinct set."""
    if key in ENUM_DOMAINS:
        return list(ENUM_DOMAINS[key])
    dv = schema.distinct_values.get(key) or set()
    if 0 < len(dv) <= 4 and all(len(v) <= 10 for v in dv):
        return sorted(dv)
    return None


def _plant_boundaries(schema, key, pool: list) -> list:
    """Add L, L-1, L+1 (numeric) or the literal itself to the value pool."""
    out = list(pool)
    for lit in BOUNDARY_LITERALS.get(key, []):
        out.append(lit)
        try:
            x = float(lit)
        except ValueError:
            continue
        for d in (-1, 1):
            y = x + d
            out.append(str(int(y)) if y == int(y) else str(y))
    for lit in LITERAL_POOL.get(key, []):
        out.append(lit)
    return out


def _null_share(schema, key, rng) -> float:
    """NULL share for a nullable column: compact share, at least one NULL row enforced later."""
    s = schema.null_share.get(key, 0.0)
    if s <= 0.0:
        s = rng.uniform(0.05, 0.10)
    return min(max(s, 0.0), 0.5)


def _plant_nulls(cols: dict, key, n: int, share: float, rng) -> None:
    """NULL rule: at least one NULL row per nullable column, share ~ compact share."""
    name = key[1]
    vals = cols.get(name)
    if vals is None or n == 0:
        return
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        vals[i] = None


def _plant_ties(cols: dict, key, rng) -> None:
    """Tie rule: at least two rows share the rank-1 value of an ORDER column."""
    name = key[1]
    vals = cols.get(name)
    if not vals or len(vals) < 2:
        return
    nn = [v for v in vals if v is not None]
    if not nn:
        return
    top = max(nn, key=lambda v: (str(type(v)), v))
    idx = [i for i, v in enumerate(vals) if v is not None]
    if len(idx) < 2:
        return
    a, b = rng.sample(idx, 2)
    vals[a] = top
    vals[b] = top


def _plant_duplicates(cols: dict, key, rng) -> None:
    """DISTINCT rule: 20-50 % of non-NULL values repeat an earlier value."""
    name = key[1]
    vals = cols.get(name)
    if not vals:
        return
    idx = [i for i, v in enumerate(vals) if v is not None]
    if len(idx) < 2:
        return
    k = max(1, int(round(rng.uniform(0.2, 0.5) * len(idx))))
    for i in rng.sample(idx, min(k, len(idx) - 1)):
        j = rng.choice([x for x in idx if x != i])
        vals[i] = vals[j]


def _plant_group_sizes(cols: dict, key, rng) -> None:
    """Group-size rule: groups of size 1, 2 and >= 3 exist."""
    name = key[1]
    vals = cols.get(name)
    if not vals or len(vals) < 6:
        return
    nn = [v for v in vals if v is not None]
    if not nn:
        return
    a, b, c = rng.sample(nn, 3) if len(set(map(str, nn))) >= 3 else (nn[0], nn[0], nn[0])
    idx = list(range(len(vals)))
    rng.shuffle(idx)
    vals[idx[0]] = a
    vals[idx[1]] = b
    vals[idx[2]] = b
    for i in idx[3:6]:
        vals[i] = c


def _plant_like_near(cols: dict, rng) -> None:
    """LIKE near-variant: a publisher containing 'Murray' (matches both %Mur% and %Murray%)."""
    t, name, full, near = LIKE_NEAR
    vals = cols.get(name)
    if not vals:
        return
    idx = [i for i, v in enumerate(vals) if v is not None]
    if not idx:
        return
    i = rng.choice(idx)
    vals[i] = 'Murray Coffee shop' if rng.random() < 0.5 else ('%s %s' % (near, 'Coffee shop'))


def _apply_formulas(inst: dict, schema, rng) -> None:
    """Semantic formulas computed in Python (never SQL)."""
    for t, c in NONNEG_COLUMNS:
        vals = inst.get(t, {}).get(c)
        if vals:
            for i, v in enumerate(vals):
                if v is not None and v < 0:
                    vals[i] = abs(v)
    t, pub, rev = DATE_ORDER
    pv = inst.get(t, {}).get(pub)
    rv = inst.get(t, {}).get(rev)
    if pv and rv:
        for i in range(min(len(pv), len(rv))):
            if pv[i] is None or rv[i] is None:
                continue
            p = _as_dt(pv[i])
            r = _as_dt(rv[i])
            if p is not None and r is not None and r < p:
                rv[i] = (p + dt.timedelta(days=rng.randint(1, 365))).strftime('%Y-%m-%d %H:%M:%S')


def _as_dt(v):
    if isinstance(v, dt.datetime):
        return v
    try:
        return dt.datetime.strptime(str(v), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def _fix_self_refs(inst: dict, schema, table: str, rng) -> None:
    """Self-references point at existing entry ids (compact + generated); NULL allowed."""
    cols = inst.get(table, {})
    ids = cols.get('catalog_entry_id') or []
    if not ids:
        return
    for name in SELF_REFS:
        vals = cols.get(name)
        if vals is None:
            continue
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in ids:
                vals[i] = rng.choice(ids)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of *appended* rows (fuzz.py:111-196 + specification)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            pool = list(literal_pool.get(key, []))
            pool = _plant_boundaries(schema, key, pool)
            samplers[key] = _init_sampler(cm, pool, schema.original_values.get(key, []), p, rng,
                                          len(tm.primary_key), enum_domain=_enum_domain(schema, key))
    if size is None:
        size = _spec_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, schema.null_share))
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks or cm.pk_pos > 0 or cm.notnull:
                continue
            _plant_nulls(cols, key, n, _null_share(schema, key, rng), rng)
        taken = set()
        for c in tm.primary_key:
            taken |= {(v,) for v in schema.original_values.get((t, c), []) if v is not None}
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for key in DISTINCT_COLUMNS:
        if key[0] in inst:
            _plant_duplicates(inst[key[0]], key, rng)
    for key in TIE_COLUMNS:
        if key[0] in inst:
            _plant_ties(inst[key[0]], key, rng)
    for key in GROUP_COLUMNS:
        if key[0] in inst:
            _plant_group_sizes(inst[key[0]], key, rng)
    if LIKE_NEAR[0] in inst:
        _plant_like_near(inst[LIKE_NEAR[0]], rng)
    _apply_formulas(inst, schema, rng)
    if 'Catalog_Contents' in inst:
        _fix_self_refs(inst, schema, 'Catalog_Contents', rng)
    return {t: inst[t] for t in schema.tables}
