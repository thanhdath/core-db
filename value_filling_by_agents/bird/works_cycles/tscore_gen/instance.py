"""Random instance construction (fuzz/fuzz.py:83-196), specification wired in."""
from .values import _init_sampler
from .spec import (
    ENUMS, RANGES, BOUNDARIES, NEAR_VARIANTS, LIKE_VARIANTS,
    DUP_COLUMNS, TIE_COLUMNS, GROUP_COLUMNS, DIFFERENT_COLUMNS,
    NULL_COUNT_COLUMNS, UNMATCHED_COLUMNS, FORMULAS, DATE_ORDER,
    TABLE_SIZES, NULL_TARGETS, NULL_SHARE, DEFAULT_NULL_SHARE,
)


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _col_idx(columns: dict) -> dict:
    return {c: i for i, c in enumerate(columns)}


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


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples=None) -> dict:
    """Drop rows repeating any single-column UNIQUE value or composite UNIQUE tuple."""
    seen_single = set()
    seen_composite = set()
    n = len(next(iter(columns.values()))) if columns else 0
    keep = []
    uniq_tuples = unique_tuples or []
    for i in range(n):
        ok = True
        for cm in table_meta.columns:
            if cm.unique and cm.name in columns:
                v = columns[cm.name][i]
                k = (cm.name, v)
                if k in seen_single and v is not None:
                    ok = False
                    break
        if ok:
            for cols in uniq_tuples:
                if not all(c in columns for c in cols):
                    continue
                k = tuple(columns[c][i] for c in cols)
                if k in seen_composite:
                    ok = False
                    break
        if ok:
            for cm in table_meta.columns:
                if cm.unique and cm.name in columns:
                    seen_single.add((cm.name, columns[cm.name][i]))
            for cols in uniq_tuples:
                if all(c in columns for c in cols):
                    seen_composite.add(tuple(columns[c][i] for c in cols))
            keep.append(i)
    return _filter(columns, keep)


def choose_table_sizes(schema, rng) -> dict:
    """Per-instance sizes: observed sizes (spec) with light variation; level sizes x4 capped at 2500."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = TABLE_SIZES.get(t, 50)
                lo = max(1, int(base * 0.7))
                hi = max(lo, int(base * 1.3))
                sizes[t] = rng.randint(lo, hi)
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _numeric(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _near_variants(value, rng):
    """Exact, lower, upper, one-char-edit and one-char-append variants."""
    s = str(value)
    out = [s]
    if s.isdigit():
        n = int(s)
        out += [str(n - 1), str(n + 1), str(n + 2)]
    else:
        out.append(s.lower())
        out.append(s.upper())
        if len(s) > 1:
            i = rng.randrange(len(s))
            out.append(s[:i] + s[i + 1:])
            out.append(s[:i] + s[i] + s[i:])
        out.append(s + 'x')
    return out


def _apply_enum(table, col, values, rng):
    if (table, col) in ENUMS:
        vals = ENUMS[(table, col)]
        return [rng.choice(vals) for _ in values]
    return values


def _apply_range(table, col, values, rng):
    if (table, col) in RANGES:
        lo, hi = RANGES[(table, col)]
        out = []
        for v in values:
            f = _numeric(v)
            if f is None:
                out.append(rng.randint(int(lo), int(hi)) if isinstance(lo, int) else rng.uniform(lo, hi))
            else:
                f = max(lo, min(hi, f))
                out.append(int(round(f)) if isinstance(lo, int) and isinstance(hi, int) else round(f, 4))
        return out
    return values


def _apply_boundary(table, col, values, rng):
    if (table, col) in BOUNDARIES and values:
        choices = BOUNDARIES[(table, col)]
        k = max(1, len(values) // 4)
        for i in range(k):
            values[i] = rng.choice(choices)
    return values


def _apply_near_variants(table, col, values, rng):
    if (table, col) in NEAR_VARIANTS and values:
        seps = NEAR_VARIANTS[(table, col)]
        k = max(1, len(values) // 4)
        for i in range(k):
            values[i] = rng.choice(_near_variants(rng.choice(seps), rng))
    return values


def _apply_like(table, col, values, rng):
    if (table, col) in LIKE_VARIANTS and values:
        sos = LIKE_VARIANTS[(table, col)]
        if not sos:
            return values
        k = max(1, len(values) // 6)
        for i in range(k):
            s = rng.choice(sos)
            v = rng.random()
            if v < 0.3:
                values[i] = '%' + s
            elif v < 0.6:
                values[i] = s + '%'
            elif v < 0.8:
                values[i] = '%' + s + '%'
            else:
                values[i] = s
    return values


def _apply_duplicates(table, col, values, rng):
    if (table, col) in DUP_COLUMNS and len(values) > 2:
        k = max(2, int(len(values) * 0.3))
        for i in range(k):
            values[i] = rng.choice(values)
    return values


def _apply_ties(table, col, values, rng):
    if (table, col) in TIE_COLUMNS and len(values) > 2:
        k = max(2, int(len(values) * 0.2))
        for i in range(k):
            values[i] = rng.choice(values)
    return values


def _apply_group_sizes(table, col, values, rng):
    if (table, col) in GROUP_COLUMNS and len(values) > 2:
        k = max(2, int(len(values) * 0.2))
        for i in range(k):
            values[i] = rng.choice(values)
    return values


def _apply_different_values(table, col, values, rng):
    if (table, col) in DIFFERENT_COLUMNS and len(values) > 2:
        n = len(values)
        for i in range(max(2, int(n * 0.2)), min(n, int(n * 0.4))):
            if _numeric(values[i]) is not None:
                base = _numeric(values[i])
                inc = 1.0 if base >= 0 else -1.0
                values[i] = round(base + inc, 4) if not float(base).is_integer() else int(base) + int(inc)
            elif isinstance(values[i], str):
                values[i] = values[i] + 'x' if not values[i].endswith('x') else values[i][:-1]
    return values


def _apply_null_counts(table, col, values, rng):
    if (table, col) in NULL_COUNT_COLUMNS and len(values) > 2:
        k = max(2, int(len(values) * 0.2))
        for i in range(k):
            values[i] = rng.choice(values)
    return values


def _apply_unmatched(table, col, values, rng):
    if (table, col) in UNMATCHED_COLUMNS and len(values) > 2:
        for i in range(1, max(2, int(len(values) * 0.1))):
            if i < len(values):
                values[i] = values[0]
    return values


def _apply_formulas(table, col, columns: dict, rng):
    if (table, col) not in FORMULAS or col not in columns:
        return
    fn = FORMULAS[(table, col)]
    n = len(columns[col])
    idx = _col_idx(columns)
    row = {}
    out = list(columns[col])
    for i in range(n):
        for c in columns:
            row[c] = columns[c][i] if idx[c] != idx[col] else None
        operands = _formula_operands(col)
        if operands and any(row.get(o) is None for o in operands):
            continue
        try:
            out[i] = fn(row)
        except Exception:
            pass
    columns[col] = out


def _formula_operands(col):
    return {
        'TotalDue': ('SubTotal', 'TaxAmt', 'Freight'),
        'LineTotal': ('OrderQty', 'UnitPrice'),
        'StockedQty': ('ReceivedQty', 'RejectedQty'),
    }.get(col)


def _apply_date_order(table, col, columns: dict):
    if (table, col) not in DATE_ORDER or col not in columns:
        return
    anchor = DATE_ORDER[(table, col)]
    if anchor not in columns:
        return
    vals = list(columns[col])
    for i in range(len(vals)):
        if vals[i] is None or columns[anchor][i] is None:
            continue
        if str(vals[i]) < str(columns[anchor][i]):
            vals[i] = columns[anchor][i]
    columns[col] = vals


def _apply_null(table, col, values, rng):
    key = '%s.%s' % (table, col)
    if key not in NULL_TARGETS or not values:
        return values
    share = NULL_SHARE.get(key, DEFAULT_NULL_SHARE)
    n = len(values)
    cnt = max(1, int(round(n * share)))
    out = list(values)
    positions = list(range(n))
    rng.shuffle(positions)
    for i in positions[:cnt]:
        out[i] = None
    return out


def _sample_pools(schema, literal_pool, rng):
    """Initialise a per-column fuzzer for every non-FK column from the compact values."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    samplers = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            ov = [v for v in schema.original_values.get((t, cm.name), []) if v is not None]
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), ov, p, rng,
                len(tm.primary_key))
    return samplers


def _parent_pools(schema, inst, table) -> dict:
    """For each FK column of `table`, the pool of parent key values (compact + generated)."""
    pools = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        compact = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        gen = inst.get(pt, {}).get(pc) or []
        pools[cm.name] = compact + [g for g in gen if g is not None]
    return pools


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of appended rows (compact rows are never modified)."""
    samplers = _sample_pools(schema, literal_pool, rng)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    key_offset = {}
    for t, tm in schema.tables.items():
        mx = 0
        for c in tm.primary_key:
            for v in schema.original_values.get((t, c), []):
                f = _numeric(v)
                if f is not None:
                    mx = max(mx, int(f))
        key_offset[t] = mx

    for lvl in schema.table_order:
        for t in lvl:
            tm = schema.tables[t]
            n = max(1, int(size.get(t, 0)))
            cols: dict = {}
            for cm in tm.columns:
                if (t, cm.name) in samplers:
                    cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
            pools = _parent_pools(schema, inst, t)
            for cm in tm.columns:
                key = (t, cm.name)
                if key not in schema.fks:
                    continue
                pv = pools.get(cm.name) or []
                if pv:
                    cols[cm.name] = [rng.choice(pv) for _ in range(n)]
                else:
                    cols[cm.name] = [None] * n
            if tm.primary_key and len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
                pk = tm.primary_key[0]
                base = key_offset.get(t, 0)
                cols[pk] = [base + i + 1 for i in range(n)]
            full = {}
            for cm in tm.columns:
                full[cm.name] = cols.get(cm.name, [None] * n)
            cols = full

            for cm in tm.columns:
                key = (t, cm.name)
                if key in cols and key not in schema.fks:
                    cols[cm.name] = _apply_enum(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_range(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_boundary(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_near_variants(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_like(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_duplicates(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_ties(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_group_sizes(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_different_values(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_null_counts(t, cm.name, cols[cm.name], rng)
                    cols[cm.name] = _apply_unmatched(t, cm.name, cols[cm.name], rng)
            for cm in tm.columns:
                _apply_formulas(t, cm.name, cols, rng)
            for cm in tm.columns:
                _apply_date_order(t, cm.name, cols)
            for cm in tm.columns:
                pk = cm.name in tm.primary_key
                if not pk and (t, cm.name) in NULL_TARGETS:
                    cols[cm.name] = _apply_null(t, cm.name, cols[cm.name], rng)

            cols = sample_fresh_primary_keys(tm, cols)
            cols = drop_unique_duplicates(tm, cols, schema.unique_tuples.get(t))

            inst[t] = cols

    return {t: inst.get(t, {}) for t in (c for lvl in schema.table_order for c in lvl) if t in schema.tables}
