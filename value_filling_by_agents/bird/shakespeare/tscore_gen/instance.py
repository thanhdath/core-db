"""Random instance construction (fuzz/fuzz.py:83-196) + the specification by construction."""
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _col_key(spec: dict, table: str, col: str):
    """Look a column up in a spec dict keyed 'table.Column' (case-insensitive)."""
    for k, v in spec.items():
        if '.' in k:
            t, c = k.split('.', 1)
            if t.lower() == table.lower() and c.lower() == col.lower():
                return v
    return None


def _is_int_type(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'year', 'bool', 'bit'))


def _is_text_type(cm) -> bool:
    t = (cm.type_str or '').lower()
    return t == '' or any(k in t for k in ('char', 'text', 'clob', 'blob'))


def _max_int(values) -> int:
    m = 0
    for v in values:
        try:
            m = max(m, int(v))
        except (TypeError, ValueError):
            pass
    return m


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification target sizes with per-instance jitter (0-230 rows per table, level x4 cap 2500)."""
    targets = spec.get('table_sizes') or {}
    jit = float(spec.get('size_jitter', 0.25))
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = targets.get(t)
            if base is None:
                base = int(30 * rng.random() + rng.random() * 200)
            lo = max(0, int(base * (1 - jit)))
            hi = min(2500, max(lo, int(base * (1 + jit))))
            sizes[t] = rng.randint(lo, hi)
    return sizes


def _column_elements(schema, spec, table, cm, literal_pool, rng):
    """Observed values + pool literals + specification text pool + boundary literals + enum."""
    ov = list(schema.original_values.get((table, cm.name), []))
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    pool = _col_key(spec.get('text_pools', {}), table, cm.name)
    if pool:
        els += list(pool)
    enum = _col_key(spec.get('enums', {}), table, cm.name)
    if enum:
        els += list(enum)
    bnd = _col_key(spec.get('boundaries', {}), table, cm.name)
    if bnd:
        els += list(bnd)
    return els


def _range_for(spec, table, cm):
    r = _col_key(spec.get('ranges', {}), table, cm.name)
    if r and len(r) == 2:
        return int(r[0]), int(r[1])
    return None, None


def _make_samplers(schema, spec, literal_pool, rng, p):
    samplers = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            els = _column_elements(schema, spec, t, cm, literal_pool.get((t, cm.name), []), rng)
            lo, hi = _range_for(spec, t, cm)
            if _is_text_type(cm) and lo is None:
                tl = spec.get('text_lengths', {})
                if cm.name.lower() in ('description', 'plaintext', 'longtitle'):
                    lo, hi = tl.get('long', [20, 120])
                else:
                    lo, hi = tl.get('short', [3, 24])
            samplers[(t, cm.name)] = _init_sampler(cm, els, schema.original_values.get((t, cm.name), []),
                                                   p, rng, len(tm.primary_key), lo=lo, hi=hi)
    return samplers


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pk: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(compact_pk), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, schema, compact_unique: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195), compact values included."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(compact_unique.get((table_meta.name, cm.name), ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for t, cols in schema.unique_tuples:
        if t != table_meta.name or not all(c in columns for c in cols):
            continue
        seen, keep = set(compact_unique.get((t, tuple(cols)), ())), []
        for i in range(_n_rows(columns)):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   unmatched_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        pool = list(pv)
        if unmatched_share > 0 and len(pool) > 1:
            k = max(1, int(len(pool) * unmatched_share))
            pool = pool[:len(pool) - k] if k < len(pool) else pool[:1]
        out[cm.name] = [rng.choice(pool) for _ in range(n)]
    return out


def _plant_duplicates(columns: dict, col: str, share: float, rng) -> None:
    """DISTINCT columns: 20-50 % duplicate share among the generated values."""
    vals = columns.get(col)
    if not vals or len(vals) < 2:
        return
    k = int(len(vals) * share)
    for i in range(len(vals) - k, len(vals)):
        vals[i] = vals[rng.randrange(0, len(vals) - k)]


def _plant_ties(columns: dict, col: str, share: float, rng) -> None:
    """ORDER/LIMIT columns: plant ties at rank 1 (a block of equal values)."""
    vals = columns.get(col)
    if not vals or len(vals) < 2:
        return
    k = max(2, int(len(vals) * share))
    v = vals[0]
    for i in range(min(k, len(vals))):
        vals[i] = v


def _clamp(v, lo, hi):
    if lo is None or hi is None:
        return v
    if isinstance(v, int):
        return max(int(lo), min(int(hi), v))
    return v


def _plant_boundaries(columns: dict, col: str, literals: list, share: float, rng, lo=None, hi=None) -> None:
    """A share of rows draws a listed boundary literal (plus one step on each side for numbers)."""
    vals = columns.get(col)
    if not vals or not literals:
        return
    k = int(len(vals) * share)
    for i in range(k):
        v = rng.choice(literals)
        if isinstance(v, int) and rng.random() < 0.5:
            v = _clamp(v + rng.choice((-1, 1)), lo, hi)
        vals[i] = v


def _plant_like_variant(columns: dict, col: str, needle: str, rng) -> None:
    """One generated value matches LIKE '%needle%' but differs from the exact literal."""
    vals = columns.get(col)
    if not vals:
        return
    i = rng.randrange(len(vals))
    vals[i] = 'The ' + needle + ' of our stage'


def _plant_nulls(columns: dict, col: str, share: float, rng) -> None:
    """NULL rule: at least one NULL row and a share following the compact database's share."""
    vals = columns.get(col)
    if not vals:
        return
    k = max(1, int(len(vals) * share))
    k = min(k, len(vals))
    idx = list(range(len(vals)))
    rng.shuffle(idx)
    for i in idx[:k]:
        vals[i] = None


def _plant_aggregate_boundary(instance: dict, schema, spec: dict, rng) -> None:
    """HAVING COUNT(paragraphs.id) = 5: one chapter gets exactly 5 generated paragraphs."""
    target = spec.get('aggregate_boundary') or {}
    if not target:
        return
    for key, want in target.items():
        t, c = key.split('.', 1)
        if t not in instance or 'paragraphs' not in instance:
            continue
        ch = instance['chapters'].get('id') or []
        if not ch:
            continue
        used = set(instance['paragraphs'].get('chapter_id') or [])
        free = [x for x in ch if x not in used]
        if not free:
            continue
        pick = free[rng.randrange(len(free))]
        pcols = instance['paragraphs']
        n = _n_rows(pcols)
        for i in range(n):
            if pcols['chapter_id'][i] == pick:
                pcols['chapter_id'][i] = rng.choice(ch)
        idx = list(range(n))
        rng.shuffle(idx)
        for i in idx[:int(want)]:
            pcols['chapter_id'][i] = pick


def _check_semantic_rules(instance: dict, schema, spec: dict) -> list:
    """Post-build check of non-NULL range formulas (returns a list of violations)."""
    bad = []
    ranges = spec.get('ranges') or {}
    for key, (lo, hi) in ranges.items():
        t, c = key.split('.', 1)
        if t not in instance or c not in instance[t]:
            continue
        for i, v in enumerate(instance[t][c]):
            if v is None:
                continue
            try:
                if (lo is not None and v < lo) or (hi is not None and v > hi):
                    bad.append((t, c, i, v))
            except TypeError:
                pass
    return bad


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz/fuzz.py:111-196) as *appended* rows over the compact DB."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = _make_samplers(schema, spec, literal_pool, rng, p)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)

    inst: dict = {}
    for t in schema.tables:
        inst[t] = {c.name: list(schema.original_values.get((t, c.name), [])) for c in schema.tables[t].columns}

    dup = spec.get('duplicate_share', {})
    ties = spec.get('tie_columns', {})
    bnd = spec.get('boundaries', {})
    bshare = float(spec.get('boundary_share', 0.15))
    tshare = float(spec.get('tie_share', 0.20))
    unmatched = spec.get('unmatched_parents', {})
    null_targets = spec.get('null_targets') or {}

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            continue
        pk_cols = tm.primary_key
        start = {}
        for c in pk_cols:
            start[c] = _max_int(schema.original_values.get((t, c), [])) + 1
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.name in pk_cols and len(pk_cols) == 1 and _is_int_type(cm):
                cols[cm.name] = list(range(start[cm.name], start[cm.name] + n))
            else:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        ushare = 0.0
        for k, v in unmatched.items():
            kt, kc = k.split('.', 1)
            if kt.lower() == t.lower():
                ushare = max(ushare, float(v))
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, ushare))
        for cm in tm.columns:
            key = '%s.%s' % (t, cm.name)
            if key in dup:
                _plant_duplicates(cols, cm.name, float(dup[key]), rng)
            if key in ties:
                _plant_ties(cols, cm.name, tshare, rng)
            if key in bnd:
                lo, hi = _range_for(spec, t, cm)
                _plant_boundaries(cols, cm.name, bnd[key], bshare, rng, lo, hi)
        for key, needle in (spec.get('like_near_variants') or {}).items():
            kt, kc = key.split('.', 1)
            if kt.lower() == t.lower() and kc in cols:
                _plant_like_variant(cols, kc, needle, rng)
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.2
            if share <= 0:
                share = 0.2
            _plant_nulls(cols, cm.name, share, rng)
        compact_pk = set()
        if pk_cols:
            rows = zip(*[schema.original_values.get((t, c), []) for c in pk_cols])
            compact_pk = {tuple(r) for r in rows}
        compact_unique = {}
        for cm in tm.columns:
            if cm.unique:
                compact_unique[(t, cm.name)] = set(schema.original_values.get((t, cm.name), []))
        for ut, ucols in schema.unique_tuples:
            if ut == t:
                compact_unique[(ut, tuple(ucols))] = set(
                    zip(*[schema.original_values.get((ut, c), []) for c in ucols]))
        cols = sample_fresh_primary_keys(tm, cols, compact_pk)
        cols = drop_unique_duplicates(tm, cols, schema, compact_unique)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            inst[t][cm.name] = inst[t].get(cm.name, []) + cols.get(cm.name, [])

    _plant_aggregate_boundary(inst, schema, spec, rng)
    bad = _check_semantic_rules(inst, schema, spec)
    if bad:
        pass
    return {t: inst[t] for t in schema.tables}
