"""Random instance construction (spec-driven by construction)."""
import sqlite3

from .values import _init_sampler

_HOURS_RANGE = (1, 1000)
_HOUR_BOUNDARIES = [99, 100, 101, 299, 300, 301, 302]
_CODE_LEN = 4
_SSN_MIN = 1
_SPEC_SIZES = {'Scientists': 12, 'Projects': 14, 'AssignedTo': 12}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _domain_for(cname: str):
    low = cname.lower()
    if low == 'hours':
        return _HOURS_RANGE
    if low == 'ssn':
        return (_SSN_MIN, None)
    return (None, None)


def _is_scientist(table: str, cname: str) -> bool:
    return table == 'Scientists' and cname.lower() == 'ssn'


def _is_projects(table: str, cname: str) -> bool:
    return table == 'Projects' and cname.lower() == 'code'


def _is_hours(table: str, cname: str) -> bool:
    return table == 'Projects' and cname.lower() == 'hours'


def _is_assigned_project(table: str, cname: str) -> bool:
    return table == 'AssignedTo' and cname.lower() == 'project'


def _is_assigned_scientist(table: str, cname: str) -> bool:
    return table == 'AssignedTo' and cname.lower() == 'scientist'


def _drop_primary_key_duplicates(table_meta, columns: dict, existing_keys: set) -> dict:
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen = set(existing_keys)
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if any(v is None for v in k):
            continue
        if k in seen:
            continue
        seen.add(k)
        keep.append(i)
    return _filter(columns, keep)


def _drop_unique_duplicates(table_meta, columns: dict, unique_groups: list, existing: set) -> dict:
    """Drop duplicate (unique-columns) tuples; composite groups handled by unique_groups."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing. get(cm.name, set())) if isinstance(existing, dict) else set()
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v in seen:
                    continue
                seen.add(v)
                keep.append(i)
            columns = _filter(columns, keep)
    for gi, group in enumerate(unique_groups):
        if not all(c in columns for c in group):
            continue
        seen = set(existing.get(('composite', gi), set())) if isinstance(existing, dict) else set()
        keep = []
        for i in range(len(next(iter(columns.values())))):
            key = tuple(columns[c][i] for c in group)
            if key in seen:
                continue
            seen.add(key)
            keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _existing_uniq(schema, table: str) -> dict:
    tm = schema.tables[table]
    single = {}
    for cm in tm.columns:
        if cm.unique:
            single[cm.name] = set(schema.original_values.get((table, cm.name), []))
    out = {}
    for gi, group in enumerate(schema.unique_groups.get(table, [])):
        cols = [schema.original_values.get((table, c), []) for c in group]
        if not cols:
            out[('composite', gi)] = set()
            continue
        k = min(len(c) for c in cols)
        out[('composite', gi)] = {tuple(cols[j][i] for j in range(len(group))) for i in range(k)}
    out.update(single)
    return out


def _existing_pk(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    if not cols:
        return set()
    k = min(len(c) for c in cols)
    return {tuple(cols[j][i] for j in range(len(tm.primary_key))) for i in range(k)}


def choose_appended_sizes(schema, rng) -> dict:
    """Appended-row counts per table."""
    out = {}
    for t in schema.tables:
        base = _SPEC_SIZES.get(t, schema.original_sizes.get(t, 0))
        lo = max(1, base)
        hi = max(lo, base + max(1, base // 2))
        out[t] = rng.randint(lo, hi)
    return out


def _fill_foreign_keys(schema, table: str, n: int, rng, parent_pools: dict) -> dict:
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = parent_pools.get(pt, {}).get(pc) or []
        if not pv:
            raise RuntimeError('empty parent pool for %s.%s -> %s.%s' % (table, cm.name, pt, pc))
        out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def _plant_hours_values(hours_col, rng):
    """Plant the spec's boundary values and a tie at max, without destroying the NULL."""
    n = len(hours_col)
    if n == 0:
        return hours_col
    nonnull_idx = [i for i, v in enumerate(hours_col) if v is not None]
    if not nonnull_idx:
        return hours_col
    bounds = list(_HOUR_BOUNDARIES)
    for i, b in enumerate(bounds):
        if i >= len(nonnull_idx):
            break
        hours_col[nonnull_idx[i]] = b
    if len(nonnull_idx) >= 2:
        hours_col[nonnull_idx[0]] = 300
        hours_col[nonnull_idx[1]] = 300
    return hours_col


def _assign_project_groups(project_col, n, rng):
    """Ensure group sizes 1, 2, >=3 exist; leave at least one project childless."""
    if n == 0:
        return project_col
    vals = []
    for v in project_col:
        if v is not None and v not in vals:
            vals.append(v)
    if len(vals) < 3:
        return project_col
    big, mid, small = vals[0], vals[1], vals[2]
    out = list(project_col)
    i = 0
    for v, k in ((big, 3), (mid, 2), (small, 1)):
        for _ in range(k):
            if i < n:
                out[i] = v
                i += 1
    while i < n:
        out[i] = rng.choice(vals)
        i += 1
    return out


def _assign_scientist_duplicates(scientist_col, n, rng):
    """Plant a duplicate share of the scientist column (20-50% of the joined result)."""
    if n < 4:
        return scientist_col
    vals = [v for v in scientist_col if v is not None]
    if not vals:
        return scientist_col
    k = max(1, n // 3)
    for i in range(k):
        if i < len(scientist_col):
            scientist_col[i] = rng.choice(vals)
    return scientist_col


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Return appended-row columns per table (compact rows untouched)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_appended_sizes(schema, rng)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            lo, hi = _domain_for(cm.name)
            extra = []
            if _is_hours(t, cm.name):
                extra = list(_HOUR_BOUNDARIES)
            pool_col = list(literal_pool.get((t, cm.name), [])) + extra
            samplers[(t, cm.name)] = _init_sampler(
                cm, pool_col, schema.original_values.get((t, cm.name), []), p, rng,
                len(tm.primary_key), dom_lo=lo, dom_hi=hi)

    appended: dict = {}
    parent_pools: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            appended[t] = {c.name: [] for c in tm.columns}
            parent_pools[t] = {c.name: list(schema.original_values.get((t, c.name), []))
                              for c in tm.columns}
            continue
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        fk_cols = _fill_foreign_keys(schema, t, n, rng, parent_pools)
        cols.update(fk_cols)

        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            if cm.name not in cols or not cols[cm.name]:
                continue
            k = rng.randrange(len(cols[cm.name]))
            cols[cm.name][k] = None

        for cm in tm.columns:
            if _is_hours(t, cm.name) and cm.name in cols:
                cols[cm.name] = [v if v is None else max(_HOURS_RANGE[0], min(_HOURS_RANGE[1], int(v)))
                                 for v in cols[cm.name]]
                cols[cm.name] = _plant_hours_values(cols[cm.name], rng)
            if _is_assigned_project(t, cm.name) and cm.name in cols:
                cols[cm.name] = _assign_project_groups(cols[cm.name], n, rng)
            if _is_assigned_scientist(t, cm.name) and cm.name in cols:
                cols[cm.name] = _assign_scientist_duplicates(cols[cm.name], n, rng)
            if _is_projects(t, cm.name) and cm.name in cols:
                cols[cm.name] = [(v if isinstance(v, str) and len(v) == _CODE_LEN
                                  else (str(v)[:_CODE_LEN].ljust(_CODE_LEN, 'x') if v is not None else None))
                                 for v in cols[cm.name]]

        groups = schema.unique_groups.get(t, [])
        existing = _existing_uniq(schema, t)
        existing_pk = _existing_pk(schema, t)
        cols = _drop_primary_key_duplicates(tm, cols, existing_pk)
        cols = _drop_unique_duplicates(tm, cols, groups, existing)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols and cm.name in cols:
                final = [v for v in cols[pc] if v is not None]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]

        appended[t] = cols
        pool = {}
        for cm in tm.columns:
            pool[cm.name] = list(schema.original_values.get((t, cm.name), [])) + \
                            [v for v in cols.get(cm.name, []) if v is not None]
        parent_pools[t] = pool

    return {t: appended[t] for t in schema.tables}
