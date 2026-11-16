"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import re

from .values import _init_sampler, _near_variants

NULL_ROWS_PER_COLUMN = 1


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
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with per-instance variation (base +/- 30%, capped at 230, never below original size)."""
    spec_sizes = (schema.spec or {}).get('table_sizes_per_instance') or {}
    sizes = {}
    for t in schema.tables:
        base = int(spec_sizes.get(t, 0))
        if base <= 0:
            base = int(schema.original_sizes.get(t, 0))
        if base <= 0:
            sizes[t] = 0
            continue
        lo = max(0, int(base * 0.7))
        hi = min(230, int(base * 1.3) + 1)
        if hi < lo:
            hi = lo
        lo = max(lo, int(schema.original_sizes.get(t, 0)))
        if hi < lo:
            hi = lo
        sizes[t] = rng.randint(lo, hi)
    return sizes


def _column_exceptions(schema, table: str, col: str) -> dict:
    """Collect boundary values, near-variants and case variants for one column from the specification."""
    out = {'boundaries': [], 'near_variants': []}
    for exc in (schema.spec or {}).get('per_column_exceptions') or []:
        if exc.get('column') != '%s.%s' % (table, col):
            continue
        pat = exc.get('pattern')
        tg = exc.get('targets') or {}
        if pat == 'comparison_boundary':
            for v in tg.get('values') or []:
                out['boundaries'].append(v)
                if isinstance(v, str):
                    out['near_variants'].append(v)
                    out['near_variants'].append(v.lower())
                    out['near_variants'].append(v.upper())
        elif pat == 'like_near_variant':
            for v in tg.get('variants') or []:
                out['near_variants'].append(v)
            for v in tg.get('literals') or []:
                out['near_variants'].extend(_near_variants(str(v)))
    seen = set()
    for k in ('boundaries', 'near_variants'):
        vals = []
        for v in out[k]:
            key = (type(v).__name__, str(v))
            if key not in seen:
                seen.add(key)
                vals.append(v)
        out[k] = vals
    return out


def _apply_formulas(schema, table: str, cols: dict, rng) -> dict:
    """Semantic formulas (range checks) applied in Python to non-NULL operands."""
    rules = []
    for r in (schema.spec or {}).get('semantic_rules_and_formulas') or []:
        if r.get('table') == table:
            rules.append(r)
    if not rules:
        return cols
    n = len(next(iter(cols.values()))) if cols else 0
    for r in rules:
        col = r.get('column')
        formula = (r.get('formula') or '').strip()
        if col not in cols:
            continue
        m = re.fullmatch(r'(\w+)\s*>\s*(-?\d+)', formula)
        m2 = re.fullmatch(r'(\w+)\s+BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', formula, re.I)
        if not (m or m2):
            continue
        boundary = set()
        for b in _column_exceptions(schema, table, col)['boundaries']:
            try:
                boundary.add(int(b))
            except (TypeError, ValueError):
                pass
        for i in range(n):
            v = cols[col][i]
            if v is None:
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            ok = True
            if m:
                ok = iv > int(m.group(2))
            else:
                ok = int(m2.group(2)) <= iv <= int(m2.group(3))
            if ok or iv in boundary:
                continue
            if m:
                lo, hi = int(m.group(2)) + 1, int(m.group(2)) + 200
            else:
                lo, hi = int(m2.group(2)), int(m2.group(3))
            cols[col][i] = rng.randint(lo, hi)
    return cols


def _apply_null_rule(schema, table: str, cols: dict, rng) -> dict:
    """NULL is a value: each nullable column gets at most NULL_ROWS_PER_COLUMN NULL rows (never a share)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        if not any(v is None for v in cols[cm.name]):
            idx = rng.randrange(n)
            cols[cm.name][idx] = None
    return cols


def _userid_pool(schema, table: str, col: str, n: int, rng) -> list:
    """Answer.UserID duplicates_for_distinct: draw from a pool of ~120-160 distinct ids."""
    excs = (schema.spec or {}).get('per_column_exceptions') or []
    want = None
    for e in excs:
        if e.get('column') == '%s.%s' % (table, col) and e.get('pattern') == 'duplicates_for_distinct':
            want = (e.get('targets') or {})
            break
    if want is None:
        return []
    ov = [v for v in schema.original_values.get((table, col), []) if v is not None]
    try:
        ivs = sorted({int(v) for v in ov})
    except (TypeError, ValueError):
        return []
    if not ivs:
        return []
    lo, hi = ivs[0], ivs[-1]
    d_lo = 120
    d_hi = 160
    target = rng.randint(d_lo, d_hi)
    span = hi - lo + 1
    if span <= target:
        ids = list(ivs)
        extra = target - len(ids)
        base = hi + 1
        ids += [base + k for k in range(max(0, extra))]
    else:
        ids = rng.sample(range(lo, hi + 1), target)
    return ids


def _fresh_primary_keys(schema, table: str, cols: dict, rng) -> dict:
    """Assign single-column primary keys."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return cols
    pk = tm.primary_key[0]
    if pk not in cols:
        return cols
    n = len(cols[pk])
    if n == 0:
        return cols
    coded = schema.coded_pk.get((table, pk)) if schema.coded_pk else None
    if coded:
        existing = set()
        try:
            for v in schema.original_values.get((table, pk), []):
                if v is not None:
                    existing.add(int(v))
        except (TypeError, ValueError):
            existing = set()
        cand = [k for k in coded if k not in existing]
        if len(cand) >= n:
            chosen = rng.sample(cand, n)
        else:
            chosen = list(cand)
            nxt = max(coded) + 1 if coded else 1
            while len(chosen) < n:
                while nxt in existing:
                    nxt += 1
                chosen.append(nxt)
                nxt += 1
        rng.shuffle(chosen)
        cols[pk] = chosen
        return cols
    ov = [v for v in schema.original_values.get((table, pk), []) if v is not None]
    try:
        base = max(int(v) for v in ov)
    except (TypeError, ValueError):
        base = 0
    if base < 0:
        base = 0
    cols[pk] = [base + i + 1 for i in range(n)]
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                exc = _column_exceptions(schema, t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key),
                    boundaries=exc['boundaries'], near_variants=exc['near_variants'])
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
        cols = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}
        if t == 'Answer' and 'UserID' in cols:
            pool = _userid_pool(schema, t, 'UserID', n, rng)
            if pool:
                cols['UserID'] = [rng.choice(pool) for _ in range(n)]
        cols = _fresh_primary_keys(schema, t, cols, rng)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc)
                if final:
                    fs = set(final)
                    cols[cm.name] = [v if v is None or v in fs else rng.choice(final)
                                     for v in cols[cm.name]]
        cols = _apply_formulas(schema, t, cols, rng)
        cols = _apply_null_rule(schema, t, cols, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
