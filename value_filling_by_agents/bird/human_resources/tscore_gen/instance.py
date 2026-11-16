"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
from .values import spec_sampler, CurrencySampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns and cm.pk_pos == 0:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def choose_table_sizes(schema, rng) -> dict:
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = rng.randint(*spec.GEN_SIZE_RANGE)
    else:
        s = rng.randint(1, 30)
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, spec.PARENT_LEVEL_CAP))
            s *= spec.PARENT_LEVEL_MULT
    return sizes


def _plant_nulls(values: list, share: float, force: bool, rng) -> list:
    """NULL rule: at least one NULL per nullable column; share = compact share."""
    n = len(values)
    if n == 0:
        return values
    k = int(round(share * n))
    if force and k < 1:
        k = 1
    if k <= 0:
        return values
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _plant_duplicates(values: list, share: float, rng) -> list:
    """Plant repeated values at the given share (DISTINCT duplicates)."""
    n = len(values)
    if n < 2:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, max(1, n // 2))
    out = list(values)
    for i in range(1, k):
        out[i] = out[0]
    return out


def _plant_group_sizes_text(values: list, rng) -> list:
    """Ensure groups of size 1, 2 and >= 3 exist on a TEXT column."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    tag = rng.randint(0, 10 ** 6)
    out[0] = 'g%d_1' % tag
    out[1] = 'g%d_2' % tag
    out[2] = 'g%d_2' % tag
    for i in range(3, n):
        out[i] = 'g%d_3' % tag
    return out


def _plant_group_sizes_int(values: list, lo: int, hi: int, rng) -> list:
    """Ensure groups 1, 2, >=3 can form by giving a small set of integers."""
    n = len(values)
    if n < 6:
        return [rng.randint(lo, hi) for _ in values]
    out = list(values)
    v1 = rng.randint(lo, hi)
    v2 = rng.randint(lo, hi)
    while v2 == v1:
        v2 = rng.randint(lo, hi)
    v3 = rng.randint(lo, hi)
    while v3 in (v1, v2):
        v3 = rng.randint(lo, hi)
    out[0], out[1], out[2] = v1, v2, v3
    return out


def _plant_ties(values: list, target: str, rng) -> list:
    """Plant >= 2 rows sharing the sort key (rank-1 tie)."""
    n = len(values)
    if n < 2:
        return values
    out = list(values)
    if target == spec.TIE_ANY:
        out[1] = out[0]
        return out
    if target == spec.TIE_AGG_COUNT_TITLE or target == spec.TIE_AGG_COUNT_STATE \
            or target == spec.TIE_AGG_COUNT_ADDRESS:
        k = max(2, n // 4)
        out[1] = out[0]
        for i in range(2, min(k, n)):
            out[i] = out[0]
        return out
    if target == spec.TIE_EDU_LENGTH:
        if isinstance(out[0], str):
            L = len(out[0])
            for i in range(1, n):
                if isinstance(out[i], str) and len(out[i]) == L:
                    out[i] = out[0]
                    return out
            out[1] = out[0]
        return out
    if target == spec.TIE_SALARY_CENTS:
        def cents(v):
            if not isinstance(v, str):
                return None
            try:
                return v[6:]
            except Exception:
                return None
        base = out[0]
        c = cents(base)
        if c is not None:
            for i in range(1, n):
                ci = cents(out[i])
                if ci is not None and ci == c:
                    return out
            try:
                prefix = base.split('US$', 1)[1]
                int_part = prefix.split(',')[0]
                out[1] = 'US$%s,%s' % (int_part, c)
            except Exception:
                pass
        return out
    out[1] = out[0]
    return out


def _apply_group_sizes(cols: dict, t: str, cm, target: str, rng) -> None:
    """GROUP BY planting restricted to safe columns."""
    vals = cols[cm.name]
    if target == 'text':
        cols[cm.name] = _plant_group_sizes_text(vals, rng)
    elif target == 'int_typed':
        if cm.type_str.lower().startswith('int'):
            cols[cm.name] = _plant_group_sizes_int(vals, 1000, 99999, rng)
    elif target == 'int_pk':
        pass
    elif target == 'int_fk':
        pass
    elif target == 'int_text':
        out = list(vals)
        n = len(out)
        if n >= 6:
            a = out[0]
            b = out[1] if out[1] != a else 'GA'
            out[0] = a
            out[1] = b
            out[2] = b
            for i in range(3, n):
                out[i] = b
        cols[cm.name] = out


def _apply_formula(values: list, f, rng) -> list:
    """Prune values failing a semantic formula to NULL (rule holds by construction)."""
    return [v if f(v) else None for v in values]


def _draw_child_fk(n: int, parent_values: list, nullable: bool, share: float, force_null: bool,
                   rng) -> list:
    """Draw FK values from the *final* parent key set; ensure >=1 NULL on nullable."""
    pv = [v for v in parent_values if v is not None]
    if not pv:
        return [None] * n
    vals = [rng.choice(pv) for _ in range(n)]
    if nullable:
        vals = _plant_nulls(vals, share, force_null, rng)
    return vals


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    taken_pk = {t: {tuple(schema.original_values.get((t, c), [])[i] for c in schema.tables[t].primary_key)
                    for i in range(schema.original_sizes.get(t, 0))}
                for t in schema.tables if schema.tables[t].primary_key}

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}

        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            s = spec_sampler(t, cm.name, cm, literal_pool.get(key, []),
                             schema.original_values.get(key, []), p, float('inf'), rng)
            vals = [s.sample() for _ in range(n)]

            is_pk = cm.pk_pos > 0
            share = spec.NULL_SHARE.get(key, 0.0)
            force = key in spec.FORCE_NULL
            if cm.notnull or is_pk:
                if any(v is None for v in vals):
                    vals = [v if v is not None else _resample(s, cm, rng) for v in vals]
            else:
                vals = _plant_nulls(vals, share, force, rng)

            if not is_pk and key in spec.DUP_SHARE and key not in spec.GROUP_SIZE_TARGETS:
                vals = _plant_duplicates(vals, spec.DUP_SHARE[key], rng)

            if key in spec.GROUP_SIZE_TARGETS:
                _apply_group_sizes({cm.name: vals}, t, cm, spec.GROUP_SIZE_TARGETS[key], rng)
                vals = cols.get(cm.name) or vals
                tmp = {cm.name: vals}
                _apply_group_sizes(tmp, t, cm, spec.GROUP_SIZE_TARGETS[key], rng)
                vals = tmp[cm.name]

            if key in spec.TIE_TARGETS and not is_pk:
                vals = _plant_ties(vals, spec.TIE_TARGETS[key], rng)

            f = spec.FORMULAS.get(key)
            if f is not None:
                vals = [v if (v is None or f(v)) else None for v in vals]

            if (cm.notnull or is_pk) and any(v is None for v in vals):
                vals = [v if v is not None else _resample(s, cm, rng) for v in vals]

            cols[cm.name] = vals

        for cm in tm.columns:
            if cm.pk_pos > 0:
                base = 1
                if tm.primary_key and len(tm.primary_key) == 1:
                    existing = [v for v in schema.original_values.get((t, cm.name), []) if isinstance(v, int)]
                    base = (max(existing) + 1) if existing else 1
                elif tm.primary_key:
                    pass
                if cm.type_str.lower().startswith('int'):
                    cols[cm.name] = list(range(base, base + n))
                    taken_pk.setdefault(t, set())

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv_gen = inst.get(pt, {}).get(pc)
            if pv_gen is None:
                pv_gen = []
            pv_compact = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
            parent_values = pv_compact + [v for v in pv_gen if v is not None]
            nullable = (not cm.notnull) and cm.pk_pos == 0
            share = spec.NULL_SHARE.get(key, 0.0)
            force_null = nullable
            cols[cm.name] = _draw_child_fk(n, parent_values, nullable, share, force_null, rng)

        cols = sample_fresh_primary_keys(tm, cols, taken_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(v for v in final if v is not None)
                if fs:
                    cols[cm.name] = [v if v is None or v in fs else rng.choice(list(fs))
                                     for v in cols[cm.name]]

        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def _resample(s, cm, rng):
    """Resample one value when a NOT NULL slot got NULL (defensive)."""
    for _ in range(20):
        v = s.sample()
        if v is not None:
            return v
    if (cm.type_str or '').lower().startswith('int'):
        return 0
    return ''
