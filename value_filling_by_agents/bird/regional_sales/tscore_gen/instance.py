"""Random instance construction + specification by construction."""
from .spec import (ENUMS, RANGES, MONEY_COLUMNS, DATE_COLUMNS, NULL_TARGETS, DISTINCT_TARGETS,
                   TIE_TARGETS, GROUP_SIZE_TARGETS, AGGREGATE_BOUNDARY, BOUNDARY_LITERALS,
                   DEPENDENCIES, UNMATCHED_JOINS, RULES, TABLE_SIZES)
from .values import (ColumnSampler, EnumSampler, RangeSampler, MoneySampler, MMDDYYDateSampler,
                     BoundaryTextSampler, BoundaryIntSampler, _init_sampler)


def _filter(columns: dict, keep: list) -> dict:
    """Keep the given row indices; guard against columns of differing length."""
    out = {}
    for c, v in columns.items():
        out[c] = [v[i] for i in keep if i < len(v)]
    return out


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = min(len(v) for v in columns.values())
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key if c in columns)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Spec table sizes when given; else upstream rand_lin / level sizes."""
    if spec and spec.get('table_sizes'):
        return {t: int(spec['table_sizes'].get(t, 0)) for t in schema.tables}
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


def _boundary_for(table: str, col: str) -> list:
    return list(BOUNDARY_LITERALS.get((table, col), []))


def _make_spec_sampler(table: str, col: str, schema, literal_pool, rng):
    """Build a sampler that implements the specification for (table, col)."""
    key = (table, col)
    col_meta = next(c for c in schema.tables[table].columns if c.name == col)
    n_pk = len(schema.tables[table].primary_key)
    boundary = _boundary_for(table, col)
    if key in ENUMS:
        return EnumSampler(ENUMS[key], 0.0, float('inf'), rng)
    if key in RANGES:
        lo, hi, is_int = RANGES[key]
        return RangeSampler(lo, hi, is_int, 0.0, float('inf'), rng, boundary=boundary)
    if key in MONEY_COLUMNS:
        return MoneySampler(0.0, float('inf'), rng, boundary=boundary)
    if key in DATE_COLUMNS:
        return MMDDYYDateSampler(0.0, float('inf'), rng)
    base = _init_sampler(col_meta, literal_pool, schema.original_values.get(key, []),
                         0.2, rng, n_pk, float('inf'))
    if boundary:
        if col_meta.pk_pos > 0 or 'int' in (col_meta.type_str or '').lower():
            return BoundaryIntSampler(boundary, base, rng)
        return BoundaryTextSampler(boundary, base, rng)
    return base


def _near_variants(values: list, rng, share: float = 0.03) -> list:
    """3% near-variants (case/whitespace) of existing string values."""
    out = []
    for v in values:
        if v is None:
            out.append(v)
            continue
        if isinstance(v, str) and rng.random() < share:
            u = rng.random()
            if u < 0.4:
                out.append(v.lower())
            elif u < 0.7:
                out.append(v.upper())
            else:
                out.append(v + ' ')
        else:
            out.append(v)
    return out


def _plant_duplicates(values: list, rng, share_lo=0.2, share_hi=0.5) -> list:
    """On DISTINCT-target columns, plant a 20-50% duplicate share."""
    if not values:
        return values
    n = len(values)
    target = int(n * rng.uniform(share_lo, share_hi))
    if target <= 0:
        return values
    out = list(values)
    for _ in range(target):
        i = rng.randrange(n)
        j = rng.randrange(n)
        out[i] = out[j]
    return out


def _plant_ties(values: list, rng) -> list:
    """On ORDER-target columns, plant ties at the top ranks."""
    if len(values) < 3:
        return values
    out = list(values)
    try:
        top = max(out)
    except TypeError:
        return out
    idx = [i for i, v in enumerate(out) if v == top]
    if len(idx) < 2:
        j = rng.randrange(len(out))
        out[j] = top
    return out


def _plant_group_sizes(values: list, rng) -> list:
    """Ensure groups of size 1, 2 and >= 3 exist (for GROUP BY targets)."""
    if len(values) < 6:
        return values
    out = list(values)
    uniq = list(dict.fromkeys(out))
    if len(uniq) < 3:
        return out
    a, b, c = uniq[0], uniq[1], uniq[2]
    out = [v for v in out if v not in (a, b, c)]
    out += [a] + [b, b] + [c, c, c]
    rng.shuffle(out)
    return out


def _plant_aggregate_boundary(values: list, rng, boundary: list) -> list:
    """Ensure COUNT(*) values around the boundary exist (2, 3, 4)."""
    if not boundary or len(values) < 10:
        return values
    out = list(values)
    uniq = list(dict.fromkeys(out))
    if len(uniq) < len(boundary):
        return out
    for k, cnt in enumerate(boundary):
        v = uniq[k]
        out = [x for x in out if x != v]
        out += [v] * cnt
    rng.shuffle(out)
    return out


def _apply_null_rule(values: list, rng, null_share: float) -> list:
    """NULL rule: at least one NULL per nullable target; share follows the compact share."""
    if not values:
        return values
    out = list(values)
    n = len(out)
    k = max(1, int(round(n * null_share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        out[i] = None
    return out


def _compact_null_share(schema, table: str, col: str) -> float:
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.03
    n_null = sum(1 for v in vals if v is None)
    return max(0.02, min(0.05, n_null / max(1, len(vals))))


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance with specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)

    parent_pool: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            parent_pool[(t, cm.name)] = list(schema.original_values.get((t, cm.name), []))

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            samplers[(t, cm.name)] = _make_spec_sampler(
                t, cm.name, schema, literal_pool.get((t, cm.name), []), rng)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = parent_pool.get((pt, pc), [])
            if pv:
                cols[cm.name] = [rng.choice(pv) for _ in range(n)]
            else:
                cols[cm.name] = [None] * n
        for dep in DEPENDENCIES:
            ct, cc, pt, pc, copied = dep
            if ct != t or cc not in cols:
                continue
            for ccol in copied:
                if ccol not in cols:
                    continue
                mapping = {}
                pvals = parent_pool.get((pt, pc), [])
                cvals = parent_pool.get((pt, ccol), [])
                for a, b in zip(pvals, cvals):
                    mapping.setdefault(a, b)
                cols[ccol] = [mapping.get(v) for v in cols[cc]]
        for cm in tm.columns:
            key = (t, cm.name)
            if key in DISTINCT_TARGETS:
                cols[cm.name] = _plant_duplicates(cols[cm.name], rng)
            if key in TIE_TARGETS:
                cols[cm.name] = _plant_ties(cols[cm.name], rng)
            if key in GROUP_SIZE_TARGETS:
                cols[cm.name] = _plant_group_sizes(cols[cm.name], rng)
            if key in AGGREGATE_BOUNDARY:
                cols[cm.name] = _plant_aggregate_boundary(cols[cm.name], rng, AGGREGATE_BOUNDARY[key])
            if key in NULL_TARGETS:
                share = _compact_null_share(schema, t, cm.name)
                cols[cm.name] = _apply_null_rule(cols[cm.name], rng, share)
            if isinstance(cols[cm.name], list) and cols[cm.name] and isinstance(cols[cm.name][0], str):
                if key not in ENUMS and key not in BOUNDARY_LITERALS:
                    cols[cm.name] = _near_variants(cols[cm.name], rng)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_rules(t, tm, cols)
        inst[t] = cols
        for cm in tm.columns:
            if cm.name in cols:
                parent_pool[(t, cm.name)] = parent_pool.get((t, cm.name), []) + list(cols[cm.name])
    return {t: inst[t] for t in schema.tables}


def _apply_rules(table: str, tm, cols: dict) -> dict:
    """Drop rows that violate a semantic rule (SQL three-valued logic: rule holds when not FALSE)."""
    if not cols:
        return cols
    n = min(len(v) for v in cols.values())
    keep = []
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        ok = True
        for cm in tm.columns:
            rule = RULES.get((table, cm.name))
            if rule is not None and not rule(row):
                ok = False
                break
        if ok:
            keep.append(i)
    return _filter(cols, keep)
