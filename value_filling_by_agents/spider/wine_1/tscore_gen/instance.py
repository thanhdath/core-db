"""Random instance construction (fuzz/fuzz.py:83-196)."""
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
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v is not None:
                    if v in seen:
                        continue
                    seen.add(v)
                keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _unique_text_set(schema, table: str, col: str, cols: dict) -> set:
    """Compact + generated values already present in a UNIQUE text column."""
    s = {v for v in schema.original_values.get((table, col), []) if v is not None}
    s |= {v for v in cols.get(col, []) if v is not None}
    return s


def _fresh_unique_value(schema, table: str, col: str, cols: dict, base: str) -> str:
    """A fresh value not present in the compact+generated set of a UNIQUE text column."""
    used = _unique_text_set(schema, table, col, cols)
    v = base
    k = 0
    while v in used:
        k += 1
        v = '%s %d' % (base, k)
    return v


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = [v for v in (instance.get(pt, {}).get(pc) or []) if v is not None]
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        for b in spec.FK_CHILD_BOUNDARY.get(key, []):
            if b in pv and b not in vals:
                vals[rng.randrange(n)] = b
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (grapes 20, appellations 57, wine 500)."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = int(spec.TABLE_SIZES.get(t, 30 + int(rng.random() * 200)))
    return sizes


def _fk_child_names(schema, table: str) -> set:
    return {c for (t, c) in schema.fks if t == table}


def _resequence_integer_pks(schema, table: str, cols: dict, rng) -> None:
    """Integer PKs of appended rows start above the compact max (never reuse a key)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.pk_pos <= 0:
            continue
        t = (cm.type_str or '').lower()
        if 'int' not in t:
            continue
        compact = [v for v in schema.original_values.get((table, cm.name), []) if isinstance(v, int)]
        start = (max(compact) + 1) if compact else 1
        n = len(cols.get(cm.name, []))
        cols[cm.name] = list(range(start, start + n))


def _plant_null(columns: dict, table: str, rng) -> None:
    """NULL rule: every nullable column gets at least one NULL row; FK children get exactly one."""
    for cm in columns:
        key = (table, cm)
        if key not in spec.NULL_TARGETS:
            continue
        vals = columns[cm]
        n = len(vals)
        if n == 0:
            continue
        if key in spec.FK_CHILD_NULL_MIN_ONE:
            k = 1
        else:
            k = max(1, int(round(n * spec.NULL_SHARE)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            vals[i] = None


def _plant_boundary(columns: dict, table: str, rng, fk_children: set) -> None:
    """Boundary literals: ensure literal-1, literal, literal+1 (or exact + near-variant) appear."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        vals = columns[cm]
        n = len(vals)
        if n == 0:
            continue
        free = [i for i in range(n) if vals[i] is not None]
        if not free:
            continue
        b = spec.BOUNDARY.get(key)
        if b:
            for v in b:
                if v not in vals:
                    vals[rng.choice(free)] = v
        bt = spec.BOUNDARY_TEXT.get(key)
        if bt:
            for v in bt:
                if v not in vals:
                    vals[rng.choice(free)] = v


def _plant_duplicates(columns: dict, table: str, rng, fk_children: set) -> None:
    """DISTINCT columns: 20-50 % of rows repeat an existing value."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.DUPLICATE_COLUMNS:
            continue
        vals = columns[cm]
        n = len(vals)
        if n < 2:
            continue
        free = [i for i in range(n) if vals[i] is not None]
        pool = [vals[i] for i in free]
        if not pool or len(free) < 2:
            continue
        share = 0.2 + rng.random() * 0.3
        k = int(len(free) * share)
        for i in rng.sample(free, min(k, len(free))):
            vals[i] = rng.choice(pool)


def _plant_ties(columns: dict, table: str, rng, fk_children: set) -> None:
    """Tie columns: at least two distinct values each occur the same maximal count."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.TIE_COLUMNS:
            continue
        vals = columns[cm]
        n = len(vals)
        free = [i for i in range(n) if vals[i] is not None]
        if len(free) < 4:
            continue
        pool = [vals[i] for i in free]
        a, b = rng.sample(pool, 2)
        if a == b:
            continue
        cnt = max(2, len(free) // 4)
        slots = rng.sample(free, min(2 * cnt, len(free)))
        for j, i in enumerate(slots):
            vals[i] = a if j < cnt else b


def _plant_price_average_tie(columns: dict, table: str, rng, fk_children: set) -> None:
    """wine.Price tie_on SUM(price)/COUNT(*): construct two groups with equal average price at rank 1. Groups are
    keyed by wine.Winery (the aggregate-boundary column)."""
    if table != 'wine':
        return
    if 'Price' not in columns or 'Winery' not in columns:
        return
    price, winery = columns['Price'], columns['Winery']
    n = len(price)
    free = [i for i in range(n) if price[i] is not None and winery[i] is not None]
    if len(free) < 6:
        return
    wpool = sorted({winery[i] for i in free})
    if len(wpool) < 2:
        return
    w1, w2 = rng.sample(wpool, 2)
    g1 = [i for i in free if winery[i] == w1]
    g2 = [i for i in free if winery[i] == w2]
    if not g1 or not g2:
        return
    avg = rng.randint(10, 200)
    for i in g1:
        price[i] = avg
    for i in g2:
        price[i] = avg


def _plant_group_sizes(columns: dict, table: str, rng, fk_children: set) -> None:
    """Group-size columns: groups of size 1, 2 and >= 3 on disjoint slots."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.GROUP_SIZE_COLUMNS:
            continue
        vals = columns[cm]
        n = len(vals)
        free = [i for i in range(n) if vals[i] is not None]
        if len(free) < 6:
            continue
        pool = [vals[i] for i in free]
        a, b, c = rng.sample(pool, min(3, len(pool)))
        slots = rng.sample(free, min(6, len(free)))
        for i in slots[:1]:
            vals[i] = a
        for i in slots[1:3]:
            vals[i] = b
        for i in slots[3:6]:
            vals[i] = c


def _plant_aggregate(columns: dict, table: str, rng, fk_children: set) -> None:
    """Aggregate-boundary columns: COUNT(*) values around 2..5. Skips None slots and FK children."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.AGGREGATE_COLUMNS:
            continue
        vals = columns[cm]
        n = len(vals)
        free = [i for i in range(n) if vals[i] is not None]
        if len(free) < 10:
            continue
        for cnt in (2, 3, 4, 5):
            v = rng.choice([vals[i] for i in free])
            for i in rng.sample(free, min(cnt, len(free))):
                vals[i] = v


def _plant_different_values(columns: dict, table: str, rng, fk_children: set) -> None:
    """Rows-with-different-values: >= 2 non-NULL qualifying rows per group differ."""
    for cm in columns:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.DIFFERENT_VALUE_COLUMNS:
            continue
        vals = columns[cm]
        n = len(vals)
        free = [i for i in range(n) if vals[i] is not None]
        if len(free) < 4:
            continue
        for k in range(0, len(free) - 1, 2):
            i, j = free[k], free[k + 1]
            if vals[i] == vals[j]:
                if isinstance(vals[i], (int, float)):
                    vals[j] = vals[i] + 1
                else:
                    vals[j] = str(vals[i]) + 'x'


def _revalidate_fks(schema, table: str, cols: dict, parent_keys: dict, rng) -> int:
    """Re-map any child FK value not in the parent's generated-key set to a valid parent value or NULL."""
    fixed = 0
    for (t, c), (pt, pc) in schema.fks.items():
        if t != table or c not in cols:
            continue
        pset = parent_keys.get((pt, pc))
        if pset is None:
            continue
        vals = cols[c]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in pset:
                vals[i] = rng.choice(list(pset)) if pset else None
                fixed += 1
    return fixed


def _ensure_parent_without_children(schema, table: str, cols: dict, rng) -> None:
    """Ensure at least one parent row has zero matching child rows (by Appelation / Grape)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if not cm.unique:
            continue
        key = (table, cm.name)
        children = [(ct, cc) for (ct, cc), (pt, pc) in schema.fks.items() if (pt, pc) == key]
        if not children:
            continue
        vals = cols.get(cm.name)
        if not vals:
            continue
        compact_child = set()
        for (ct, cc) in children:
            compact_child |= {v for v in schema.original_values.get((ct, cc), []) if v is not None}
        free = [i for i in range(len(vals)) if vals[i] is not None and vals[i] not in compact_child]
        if not free:
            base = 'Unmatched %s' % cm.name
            v = _fresh_unique_value(schema, table, cm.name, cols, base)
            slots = [i for i in range(len(vals)) if vals[i] is not None]
            if slots:
                vals[rng.choice(slots)] = v


def _dedup_unique_text(schema, table: str, cols: dict, rng) -> None:
    """Final de-duplication on UNIQUE text columns: replace any repeated value with a fresh one."""
    for (t, c) in spec.UNIQUE_TEXT_COLUMNS:
        if t != table or c not in cols:
            continue
        vals = cols[c]
        seen = set()
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v in seen:
                vals[i] = _fresh_unique_value(schema, table, c, cols, str(v) + ' gen')
            seen.add(vals[i])


def _validate_and_replant(schema, table: str, cols: dict, rng, fk_children: set) -> None:
    """Post-planting validation: re-plant patterns destroyed by later passes."""
    for cm in cols:
        key = (table, cm)
        if key in spec.NULL_TARGETS:
            vals = cols[cm]
            if vals and all(v is not None for v in vals):
                cols[cm][rng.randrange(len(vals))] = None
    for cm in cols:
        if cm in fk_children:
            continue
        key = (table, cm)
        vals = cols[cm]
        free = [i for i in range(len(vals)) if vals[i] is not None]
        if not free:
            continue
        for v in (spec.BOUNDARY.get(key) or []) + (spec.BOUNDARY_TEXT.get(key) or []):
            if v not in vals:
                cols[cm][rng.choice(free)] = v
    for cm in cols:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.GROUP_SIZE_COLUMNS:
            continue
        vals = cols[cm]
        free = [i for i in range(len(vals)) if vals[i] is not None]
        if len(free) < 6:
            continue
        from collections import Counter
        cnt = Counter(vals[i] for i in free)
        sizes = set(cnt.values())
        if not ({1, 2} <= sizes and any(s >= 3 for s in sizes)):
            pool = [vals[i] for i in free]
            a, b, c = rng.sample(pool, min(3, len(pool)))
            slots = rng.sample(free, min(6, len(free)))
            for i in slots[:1]:
                vals[i] = a
            for i in slots[1:3]:
                vals[i] = b
            for i in slots[3:6]:
                vals[i] = c
    for cm in cols:
        if cm in fk_children:
            continue
        key = (table, cm)
        if key not in spec.TIE_COLUMNS:
            continue
        vals = cols[cm]
        free = [i for i in range(len(vals)) if vals[i] is not None]
        if len(free) < 4:
            continue
        from collections import Counter
        cnt = Counter(vals[i] for i in free)
        if not cnt:
            continue
        mx = max(cnt.values())
        if sum(1 for v in cnt.values() if v == cnt.most_common(1)[0][1]) < 2:
            pool = [vals[i] for i in free]
            a, b = rng.sample(pool, 2)
            if a != b:
                k = max(2, len(free) // 4)
                slots = rng.sample(free, min(2 * k, len(free)))
                for j, i in enumerate(slots):
                    vals[i] = a if j < k else b


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), extended with specification planting."""
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
    parent_vals: dict = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            parent_vals[(t, cm.name)] = list(schema.original_values.get((t, cm.name), []))
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        _resequence_integer_pks(schema, t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        fk_children = _fk_child_names(schema, t)
        _plant_null(cols, t, rng)
        _plant_boundary(cols, t, rng, fk_children)
        _plant_duplicates(cols, t, rng, fk_children)
        _plant_ties(cols, t, rng, fk_children)
        _plant_price_average_tie(cols, t, rng, fk_children)
        _plant_group_sizes(cols, t, rng, fk_children)
        _plant_aggregate(cols, t, rng, fk_children)
        _plant_different_values(cols, t, rng, fk_children)
        _ensure_parent_without_children(schema, t, cols, rng)
        parent_keys = {}
        for (ct, cc), (pt, pc) in schema.fks.items():
            if pt in inst or pt in schema.original_values:
                pv = parent_vals.get((pt, pc), [])
                gen = inst.get(pt, {}).get(pc) if pt in inst else []
                parent_keys[(pt, pc)] = {v for v in list(pv) + list(gen or []) if v is not None}
        _revalidate_fks(schema, t, cols, parent_keys, rng)
        _dedup_unique_text(schema, t, cols, rng)
        _validate_and_replant(schema, t, cols, rng, fk_children)
        _dedup_unique_text(schema, t, cols, rng)
        inst[t] = cols
        for cm in tm.columns:
            parent_vals[(t, cm.name)] = parent_vals[(t, cm.name)] + list(cols.get(cm.name, []))
    return {t: inst[t] for t in schema.tables}
