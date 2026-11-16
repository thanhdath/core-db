"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
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
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += list(schema.original_values.get((pt, pc), []) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (spec.table_sizes_per_instance), jittered per instance."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 40
        jitter = rng.randint(-max(1, base // 5), max(1, base // 5))
        sizes[t] = max(0, base + jitter)
    return sizes


def _null_share(table: str, col: str, rng) -> float:
    """NULL share for a nullable column: compact share, forced into the spec band if listed."""
    if (table, col) in spec.NULL_BAND:
        lo, hi = spec.NULL_BAND[(table, col)]
        return rng.uniform(lo, hi)
    return spec.NULL_RATE.get((table, col), 0.0)


def _apply_nulls(table: str, col: str, values: list, rng) -> list:
    """NULL rule: at least one NULL row per nullable column, share from the compact database."""
    share = _null_share(table, col, rng)
    n = len(values)
    if n == 0:
        return values
    k = int(round(share * n))
    if share > 0:
        k = max(1, k)
    k = min(k, n)
    idx = set(rng.sample(range(n), k)) if k else set()
    return [None if i in idx else v for i, v in enumerate(values)]


def _apply_duplicates(table: str, col: str, values: list, rng) -> list:
    """duplicate_distinct: 20-50 % of rows share values on the DISTINCT column."""
    share = spec.DUP_SHARE.get((table, col))
    if share is None or len(values) < 2:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    idx = rng.sample(range(n), min(k, n))
    for i in idx:
        values[i] = rng.choice(pool)
    return values


def _apply_ties(table: str, columns: dict, rng) -> None:
    """tie_order: at least two rows share the top value of the ORDER expression."""
    for (t, col), (expr, direction, rank) in spec.TIE_TARGETS.items():
        if t != table or col not in columns:
            continue
        vals = columns[col]
        n = len(vals)
        if n < 2:
            continue
        if expr is None:
            top = max(v for v in vals if v is not None) if any(v is not None for v in vals) else None
            if top is None:
                continue
            idx = [i for i, v in enumerate(vals) if v == top]
            if len(idx) < 2:
                j = rng.randrange(n)
                vals[j] = top
            continue
        a, b = [s.strip() for s in expr.split('-')]
        if a not in columns or b not in columns:
            continue
        keys = []
        for i in range(n):
            x, y = columns[a][i], columns[b][i]
            if x is None or y is None:
                keys.append(None)
            else:
                keys.append(x - y)
        valid = [(k, i) for i, k in enumerate(keys) if k is not None]
        if not valid:
            continue
        top = max(k for k, _ in valid) if direction == 'DESC' else min(k for k, _ in valid)
        idx = [i for k, i in valid if k == top]
        if len(idx) < 2:
            j = rng.randrange(n)
            if columns[a][j] is not None and columns[b][j] is not None:
                columns[a][j] = columns[b][j] + top


def _apply_diff_values(table: str, columns: dict, rng) -> None:
    """rows_with_different_values: >= 2 rows per group with different values."""
    for (t, col) in spec.DIFF_VALUE_COLUMNS:
        if t != table or col not in columns:
            continue
        vals = columns[col]
        n = len(vals)
        if n < 2:
            continue
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        i, j = rng.sample(nonnull, 2)
        if vals[i] == vals[j]:
            vals[j] = vals[j] + 1 if isinstance(vals[j], (int, float)) else vals[j]


def _apply_min_max(table: str, columns: dict, rng) -> None:
    """min_qty <= max_qty (semantic rule), only on non-NULL operands."""
    if 'min_qty' in columns and 'max_qty' in columns:
        for i in range(len(columns['min_qty'])):
            lo, hi = columns['min_qty'][i], columns['max_qty'][i]
            if lo is not None and hi is not None and lo > hi:
                columns['min_qty'][i], columns['max_qty'][i] = hi, lo


def _fresh_pk_start(schema, table: str, col: str) -> int:
    """First primary-key value above the compact maximum (keys fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification rules by construction."""
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
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                start = _fresh_pk_start(schema, t, cm.name)
                cols[cm.name] = [start + i for i in range(n)]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                cols[cm.name] = _apply_nulls(t, cm.name, cols[cm.name], rng)
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_duplicates(t, cm.name, cols[cm.name], rng)
        _apply_min_max(t, cols, rng)
        _apply_ties(t, cols, rng)
        _apply_diff_values(t, cols, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
