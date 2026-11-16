"""Random instance construction (fuzz/fuzz.py:83-196)."""
from collections import Counter

from .spec import column_domain, DEFAULT_DUP_SHARE, NULL_FLOOR
from .values import _init_sampler

PARENT_SHARE = 0.5
BOUNDARY_SHARE = 0.35


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


def _fill_soft_join_column(table: str, column: str, n: int, parent_vals: list, dom: dict,
                           sampler, rng) -> list:
    """Mix parent values, boundary/range values, and sampler values for a soft-join child column."""
    boundary = [v for v in (dom.get('pool') or []) if v is not None]
    rng_range = dom.get('range')
    out = []
    parent_vals = [v for v in (parent_vals or []) if v is not None]
    for _ in range(n):
        u = rng.random()
        if parent_vals and u < PARENT_SHARE:
            out.append(rng.choice(parent_vals))
        elif boundary and u < PARENT_SHARE + BOUNDARY_SHARE and rng.random() < 0.7:
            out.append(rng.choice(boundary))
        elif boundary and u < PARENT_SHARE + BOUNDARY_SHARE and rng_range is not None:
            out.append(rng.randint(int(rng_range[0]), int(rng_range[1])))
        else:
            v = sampler.sample() if sampler is not None else None
            out.append(v)
    if out and all(v is None for v in out):
        cand = parent_vals or boundary
        if cand:
            out[rng.randrange(n)] = rng.choice(cand)
        elif rng_range is not None:
            out[rng.randrange(n)] = rng.randint(int(rng_range[0]), int(rng_range[1]))
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   soft_joins: dict = None, samplers: dict = None,
                                   spec: dict = None) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    joins = dict(schema.fks)
    if soft_joins:
        for (ct, cc), (pt, pc) in soft_joins.items():
            joins.setdefault((ct, cc), (pt, pc))
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in joins:
            continue
        pt, pc = joins[key]
        pv = instance.get(pt, {}).get(pc) or []
        pv = [v for v in pv if v is not None]
        is_soft = soft_joins and key in soft_joins
        if is_soft:
            dom = column_domain(schema, spec or {}, table, cm.name)
            sampler = (samplers or {}).get((table, cm.name))
            out[cm.name] = _fill_soft_join_column(table, cm.name, n, pv, dom, sampler, rng)
        else:
            out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec_sizes: dict = None) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if spec_sizes:
        for t in schema.tables:
            base = int(spec_sizes.get(t, 0))
            jitter = rng.randint(-max(1, base // 6), max(1, base // 6)) if base else 0
            sizes[t] = max(0, base + jitter)
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


def _apply_null_rule(cols: dict, table: str, schema, spec: dict, rng) -> dict:
    """NULL rule: nullable columns get a NULL share (compact share, floor) and at least one NULL row."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        dom = column_domain(schema, spec, table, cm.name)
        base_share = dom.get('null_share')
        share = float(base_share) if base_share is not None else float(dom.get('null_floor', NULL_FLOOR))
        k = max(1, int(round(share * n)))
        k = min(k, n)
        if k >= n:
            k = n - 1
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None
        if all(v is None for v in cols[cm.name]):
            cand = [v for v in (dom.get('pool') or []) if v is not None]
            if cand:
                cols[cm.name][rng.randrange(n)] = rng.choice(cand)
            elif dom.get('range') is not None:
                lo, hi = dom['range']
                cols[cm.name][rng.randrange(n)] = rng.randint(int(lo), int(hi))
    return cols


def _apply_duplicate_share(cols: dict, table: str, schema, spec: dict, rng) -> dict:
    """Duplicate share for DISTINCT columns: 20-50% of rows reuse an earlier value."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0:
            continue
        dom = column_domain(schema, spec, table, cm.name)
        share = dom.get('dup_share')
        if share is None:
            continue
        share = max(0.2, min(0.5, float(share)))
        k = int(round(share * n))
        if k <= 0:
            continue
        idx = rng.sample(range(1, n), min(k, n - 1))
        for i in idx:
            j = rng.randrange(0, i)
            cols[cm.name][i] = cols[cm.name][j]
    return cols


def _apply_group_sizes(cols: dict, table: str, schema, spec: dict, rng) -> dict:
    """Group-size targets: for GROUP BY columns, ensure groups of size 1, 2 and >= 3 exist."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 6:
        return cols
    want = {(str(t).lower(), str(c).lower()) for (t, c) in spec.get('group_cols', set())}
    if not any(tt == str(table).lower() for tt, _ in want):
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if (str(table).lower(), str(cm.name).lower()) not in want:
            continue
        vals = cols[cm.name]
        distinct = []
        for v in vals:
            if v is not None and v not in distinct:
                distinct.append(v)
            if len(distinct) >= 6:
                break
        if len(distinct) < 3:
            continue
        positions = list(range(n))
        rng.shuffle(positions)
        a, b, c = distinct[0], distinct[1], distinct[2]
        vals[positions[0]] = a
        vals[positions[1]] = b
        vals[positions[2]] = b
        vals[positions[3]] = c
        vals[positions[4]] = c
        vals[positions[5]] = c
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks and (t, cm.name) not in spec.get('soft_joins', {}):
                dom = column_domain(schema, spec, t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), domain=dom)
            elif (t, cm.name) in spec.get('soft_joins', {}) and (t, cm.name) not in schema.fks:
                dom = column_domain(schema, spec, t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), domain=dom)
    if size is None:
        size = choose_table_sizes(schema, rng, spec.get('table_sizes'))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers
                and (t, cm.name) not in schema.fks
                and (t, cm.name) not in spec.get('soft_joins', {})}
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                   spec.get('soft_joins', {}),
                                                   samplers, spec))
        cols = _apply_null_rule(cols, t, schema, spec, rng)
        cols = _apply_duplicate_share(cols, t, schema, spec, rng)
        cols = _apply_group_sizes(cols, t, schema, spec, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        cols = _apply_group_sizes(cols, t, schema, spec, rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = {v for v in final if v is not None}
                if fs:
                    cols[cm.name] = [v if v is None or v in fs else rng.choice(sorted(fs))
                                     for v in cols[cm.name]]
                else:
                    cols[cm.name] = [None for _ in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
