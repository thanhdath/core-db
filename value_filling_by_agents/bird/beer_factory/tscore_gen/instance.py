"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
from . import spec
from .values import _init_sampler, apply_null_rule


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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent key pool = compact values + generated values (in memory)."""
    pool = list(schema.original_values.get((pt, pc), []))
    pool += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return pool


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _fresh_keys(schema, table: str, column: str, n: int, rng) -> list:
    """Fresh integer keys above the compact maximum (never reuse compact keys)."""
    used = {v for v in schema.original_values.get((table, column), []) if isinstance(v, int)}
    if used:
        start = max(used) + 1
    else:
        start = 1
    return [start + i for i in range(n)]


def _group_size_plan(n: int, rng) -> list:
    """Group sizes 1, 2 and >= 3 (spec group_sizes) summing to n."""
    plan, left = [], n
    while left > 0:
        g = rng.choice([1, 2, 3, 4, 5])
        g = min(g, left)
        plan.append(g)
        left -= g
    return plan


def _assign_groups(keys: list, n: int, rng) -> list:
    """Assign n child rows to parent keys with group sizes 1, 2 and >= 3 where possible."""
    if not keys:
        return [None] * n
    plan = _group_size_plan(n, rng)
    out = []
    for g in plan:
        k = rng.choice(keys)
        out.extend([k] * g)
    rng.shuffle(out)
    return out[:n]


def _null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return spec.DEFAULT_NULL_SHARE
    nulls = sum(1 for v in vals if v is None)
    return nulls / len(vals)


def _is_nullable(schema, table: str, column: str) -> bool:
    for cm in schema.tables[table].columns:
        if cm.name == column:
            return not cm.notnull and cm.pk_pos == 0
    return False


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes, with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        jitter = rng.randint(-2, 2) if base > 5 else 0
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _brand_price_map(schema, inst: dict) -> dict:
    """BrandID -> CurrentRetailPrice from compact + generated rootbeerbrand rows (in memory)."""
    out = {}
    for b, pr in zip(schema.original_values.get(('rootbeerbrand', 'BrandID'), []),
                     schema.original_values.get(('rootbeerbrand', 'CurrentRetailPrice'), [])):
        if b is not None and pr is not None:
            out[b] = pr
    gb = inst.get('rootbeerbrand', {})
    for b, pr in zip(gb.get('BrandID', []), gb.get('CurrentRetailPrice', [])):
        if b is not None and pr is not None:
            out[b] = pr
    return out


def _rootbeer_brand_map(schema, inst: dict) -> dict:
    """RootBeerID -> BrandID from compact + generated rootbeer rows (in memory)."""
    out = {}
    for rb, b in zip(schema.original_values.get(('rootbeer', 'RootBeerID'), []),
                     schema.original_values.get(('rootbeer', 'BrandID'), [])):
        if rb is not None and b is not None:
            out[rb] = b
    gr = inst.get('rootbeer', {})
    for rb, b in zip(gr.get('RootBeerID', []), gr.get('BrandID', [])):
        if rb is not None and b is not None:
            out[rb] = b
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
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
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                cols[cm.name] = _fresh_keys(schema, t, cm.name, n, rng)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks and key in spec.GROUP_SIZE_COLUMNS:
                pt, pc = schema.fks[key]
                pv = _parent_pool(inst, schema, pt, pc)
                fk_cols[cm.name] = _assign_groups(pv, n, rng)
        cols.update(fk_cols)
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                cols[cm.name] = apply_null_rule(cols[cm.name], True,
                                                _null_share(schema, t, cm.name), rng)
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
    if 'transaction' in inst:
        rb2brand = _rootbeer_brand_map(schema, inst)
        brand2price = _brand_price_map(schema, inst)
        tr = inst['transaction']
        rb = tr.get('RootBeerID', [])
        pp = []
        for v in rb:
            b = rb2brand.get(v) if v is not None else None
            pp.append(brand2price.get(b) if b is not None else None)
        tr['PurchasePrice'] = pp
        tr['PurchasePrice'] = apply_null_rule(tr['PurchasePrice'], True,
                                              _null_share(schema, 'transaction', 'PurchasePrice'), rng)
    return {t: inst[t] for t in schema.tables}
