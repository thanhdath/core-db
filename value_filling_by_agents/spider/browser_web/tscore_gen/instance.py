"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven sampling."""
import re

from .values import _init_sampler, make_column_sampler

_BOUNDARY = {
    ('browser', 'market_share'): [3.99, 4, 4.01, 4.99, 5, 5.01, 10.99, 11, 11.01, 14.99, 15, 15.01],
}
_STR_LITERALS = {
    ('browser', 'name'): ['Internet Explorer', 'internet explorer', 'Opera', 'opera'],
    ('Web_client_accelerator', 'name'): ['CACHEbox', 'cachebox'],
}
_RANGES = {
    ('browser', 'market_share'): (0.0, 100.0),
    ('accelerator_compatible_browser', 'compatible_since_year'): (1990, 2030),
}
_POSITIVE = {
    ('browser', 'id'), ('Web_client_accelerator', 'id'),
    ('accelerator_compatible_browser', 'accelerator_id'),
    ('accelerator_compatible_browser', 'browser_id'),
}
_NULL_SHARE = {
    ('accelerator_compatible_browser', 'compatible_since_year'): 0.15,
}
_GROUP_SIZE = {
    ('browser', 'name'),
    ('Web_client_accelerator', 'name'),
    ('Web_client_accelerator', 'Operating_system'),
    ('accelerator_compatible_browser', 'browser_id'),
}
_DUPLICATE_SHARE = set()
_TIE_RANK = {('browser', 'market_share'): 10}
_TABLE_SIZES = {'browser': 4, 'Web_client_accelerator': 8, 'accelerator_compatible_browser': 9}


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


def _compact_parent_keys(schema, pt: str, pc: str) -> list:
    """Distinct non-NULL parent key values present in the compact (copied) database."""
    vals = schema.original_values.get((pt, pc)) or []
    out, seen = [], set()
    for v in vals:
        if v is None:
            continue
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _parent_key_union(schema, instance: dict, pt: str, pc: str) -> list:
    """Union of compact and generated parent key values (both are valid FK targets)."""
    out, seen = [], set()
    for v in _compact_parent_keys(schema, pt, pc):
        if v not in seen:
            seen.add(v)
            out.append(v)
    for v in (instance.get(pt, {}).get(pc) or []):
        if v is None or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the union of compact + generated parent keys with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_key_union(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes with light per-instance variation (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = _TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        delta = rng.choice((-1, 0, 0, 1))
        sizes[t] = max(1, base + delta)
    return sizes


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t and 'point' not in t


def _is_real_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric'))


def _clamp_number(v, lo, hi, is_int):
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return v
    if x < lo:
        x = lo
    if x > hi:
        x = hi
    return int(round(x)) if is_int else round(x, 2)


def _apply_range(table, col, values, type_str):
    """Enforce a numeric range formula on sampled values (non-NULL operands only)."""
    key = (table, col)
    if key not in _RANGES:
        return values
    lo, hi = _RANGES[key]
    is_int = _is_int_type(type_str)
    return [_clamp_number(v, lo, hi, is_int) for v in values]


def _apply_positive(table, col, values):
    """Enforce a positive-integer formula (id > 0 etc.)."""
    if (table, col) not in _POSITIVE:
        return values
    out = []
    for v in values:
        if v is None:
            out.append(v)
            continue
        try:
            x = int(v)
        except (TypeError, ValueError):
            out.append(v)
            continue
        out.append(x if x > 0 else 1)
    return out


def _inject_boundaries(table, col, values, type_str, rng):
    """Plant comparison-boundary literals into the value list (replacing some slots)."""
    key = (table, col)
    if key not in _BOUNDARY or not values:
        return values
    lits = list(_BOUNDARY[key])
    is_int = _is_int_type(type_str)
    vals = list(values)
    n = len(vals)
    slots = list(range(n))
    rng.shuffle(slots)
    for i, lit in enumerate(lits):
        if i >= len(slots):
            break
        v = int(round(lit)) if is_int else round(float(lit), 2)
        vals[slots[i]] = v
    return vals


def _inject_string_literals(table, col, values, rng):
    """Plant string equality literals and case near-variants."""
    key = (table, col)
    if key not in _STR_LITERALS or not values:
        return values
    lits = list(_STR_LITERALS[key])
    vals = list(values)
    slots = list(range(len(vals)))
    rng.shuffle(slots)
    for i, lit in enumerate(lits):
        if i >= len(slots):
            break
        vals[slots[i]] = lit
    return vals


def _compact_null_share(schema, table, col):
    """NULL share of a column in the compact database (0.0 when unknown)."""
    vals = schema.original_values.get((table, col))
    if not vals:
        return 0.0
    n = len(vals)
    n_null = sum(1 for v in vals if v is None)
    return n_null / n if n else 0.0


def _apply_null_rule(table, col, values, nullable, rng, schema=None):
    """NULL rule: nullable columns get at least one NULL and a share following the compact database."""
    if not nullable or not values:
        return values
    share = _compact_null_share(schema, table, col) if schema is not None else 0.0
    if share <= 0.0:
        share = _NULL_SHARE.get((table, col), 0.0)
    n = len(values)
    n_null = max(1, int(round(share * n)))
    n_null = min(n_null, n)
    vals = list(values)
    slots = list(range(n))
    rng.shuffle(slots)
    for i in range(n_null):
        vals[slots[i]] = None
    return vals


def _apply_group_sizes(table, col, values, rng):
    """Ensure groups of size 1, 2 and >= 3 exist for the column (by repeating values)."""
    if (table, col) not in _GROUP_SIZE or len(values) < 6:
        return values
    vals = list(values)
    src = [v for v in vals if v is not None]
    if len(src) < 3:
        return vals
    a, b, c = rng.sample(src, 3)
    slots = list(range(len(vals)))
    rng.shuffle(slots)
    vals[slots[0]] = a
    vals[slots[1]] = b
    vals[slots[2]] = b
    vals[slots[3]] = c
    vals[slots[4]] = c
    vals[slots[5]] = c
    return vals


def _apply_duplicate_share(table, col, values, rng):
    """Ensure the duplicate share of the column stays in the 20-50% band (non-PK columns only)."""
    if (table, col) not in _DUPLICATE_SHARE or len(values) < 5:
        return values
    vals = list(values)
    n = len(vals)
    target = max(1, int(round(0.3 * n)))
    first = vals[0]
    slots = list(range(1, n))
    rng.shuffle(slots)
    for i in range(min(target, len(slots))):
        vals[slots[i]] = first
    return vals


def _apply_tie_rank(table, col, values, rng):
    """Plant a tie at the listed LIMIT rank (DESC) by repeating the boundary value."""
    key = (table, col)
    if key not in _TIE_RANK or len(values) < 2:
        return values
    rank = _TIE_RANK[key]
    vals = list(values)
    n = len(vals)
    order = sorted(range(n), key=lambda i: (vals[i] is None, -(vals[i] if vals[i] is not None else 0)))
    if len(order) >= rank + 1:
        hi = order[rank - 1]
        lo = order[rank]
        vals[lo] = vals[hi]
    return vals


def _shape_column(table, cm, values, rng, schema=None):
    """Apply all specification shaping rules to one column's sampled values."""
    vals = values
    vals = _apply_range(table, cm.name, vals, cm.type_str)
    vals = _apply_positive(table, cm.name, vals)
    vals = _inject_boundaries(table, cm.name, vals, cm.type_str, rng)
    vals = _inject_string_literals(table, cm.name, vals, rng)
    if cm.pk_pos == 0:
        vals = _apply_group_sizes(table, cm.name, vals, rng)
        vals = _apply_duplicate_share(table, cm.name, vals, rng)
        vals = _apply_tie_rank(table, cm.name, vals, rng)
    vals = _apply_null_rule(table, cm.name, vals, not cm.notnull and cm.pk_pos == 0, rng, schema)
    return vals


def _ensure_parent_child_coverage(schema, inst, rng):
    """At least one child row per generated parent and at least one parent row with no children."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        child = inst[ct].get(cc)
        parent = inst[pt].get(pc)
        if not child or not parent:
            continue
        present = {v for v in child if v is not None}
        missing = [p for p in parent if p is not None and p not in present]
        if not missing:
            continue
        slots = [i for i, v in enumerate(child) if v is not None]
        rng.shuffle(slots)
        for i, p in zip(slots, missing):
            child[i] = p


def _shape_browser_id_aggregate(schema, inst, rng):
    """accelerator_compatible_browser.browser_id: COUNT(DISTINCT browser_id) values 0,1,2,3 and comparison boundary
    browser_id > browser.id (equal and one step from browser.id)."""
    ct = 'accelerator_compatible_browser'
    if ct not in inst or 'browser_id' not in inst[ct]:
        return
    child = inst[ct]['browser_id']
    if not child:
        return
    parent_ids = _parent_key_union(schema, inst, 'browser', 'id')
    if not parent_ids:
        return
    n = len(child)
    slots = list(range(n))
    rng.shuffle(slots)
    if len(slots) >= 2:
        pid = rng.choice(parent_ids)
        child[slots[0]] = pid
        if (pid + 1) in set(parent_ids):
            child[slots[1]] = pid + 1
    distinct = {v for v in child if v is not None}
    if len(distinct) < 3 and len(parent_ids) >= 3:
        extra = [p for p in parent_ids if p not in distinct]
        rng.shuffle(extra)
        free = [i for i in range(n) if child[i] is None]
        rng.shuffle(free)
        for i, p in zip(free, extra):
            child[i] = p
            distinct.add(p)
            if len(distinct) >= 3:
                break


def _ensure_parent_without_children(schema, inst, rng):
    """Unmatched-join shaping: guarantee at least one parent (compact or generated) with no child."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        child = inst[ct].get(cc)
        if not child:
            continue
        parent_keys = _parent_key_union(schema, inst, pt, pc)
        if not parent_keys:
            continue
        present = {v for v in child if v is not None}
        if any(p not in present for p in parent_keys):
            continue
        if len(parent_keys) < 2:
            continue
        drop = rng.choice(parent_keys)
        keep = [p for p in parent_keys if p != drop]
        for i, v in enumerate(child):
            if v == drop:
                child[i] = rng.choice(keep)


def _revalidate_fks(schema, inst, rng):
    """Final FK re-validation after all post-shaping mutations: any child FK value not in the parent key union is
    replaced by a valid parent key (or NULL when the parent is empty)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst:
            continue
        child = inst[ct].get(cc)
        if not child:
            continue
        parent_keys = _parent_key_union(schema, inst, pt, pc)
        pset = set(parent_keys)
        for i, v in enumerate(child):
            if v is None:
                continue
            if v not in pset:
                child[i] = rng.choice(parent_keys) if parent_keys else None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification shaping by construction."""
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
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) not in samplers:
                continue
            raw = [samplers[(t, cm.name)].sample() for _ in range(n)]
            cols[cm.name] = _shape_column(t, cm, raw, rng, schema)
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
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
    _ensure_parent_child_coverage(schema, inst, rng)
    _shape_browser_id_aggregate(schema, inst, rng)
    _ensure_parent_without_children(schema, inst, rng)
    _revalidate_fks(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}
