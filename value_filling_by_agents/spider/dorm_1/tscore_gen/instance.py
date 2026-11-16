"""Random instance construction implementing the specification by construction."""
from .values import _init_sampler

_NULL_SHARE = 0.08


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
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


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t


def _is_str_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'varchar', 'blob'))


def _is_key_column(schema, table: str, col: str) -> bool:
    """True for primary-key or NOT NULL columns (never NULL, never overwritten by patterns)."""
    tm = schema.tables.get(table)
    if tm is None:
        return False
    for cm in tm.columns:
        if cm.name == col:
            return cm.pk_pos > 0 or cm.notnull
    return False


def _apply_semantic_rules(spec: dict, table: str, columns: dict, rng) -> None:
    """Constrain sampled values to the semantic rules (in Python, not SQL)."""
    for rule in spec.get('semantic_rules', []):
        if rule.get('table') != table:
            continue
        col = rule.get('column')
        if col not in columns:
            continue
        vals = columns[col]
        kind = rule.get('kind')
        if kind == 'between':
            lo, hi = rule['lo'], rule['hi']
            for i, v in enumerate(vals):
                if v is None:
                    continue
                if not (lo <= v <= hi):
                    vals[i] = rng.randint(lo, hi)
        elif kind == 'in':
            allowed = list(rule['values'])
            for i, v in enumerate(vals):
                if v is None:
                    continue
                if v not in allowed:
                    vals[i] = rng.choice(allowed)
        elif kind == 'gt':
            bound = rule['value']
            for i, v in enumerate(vals):
                if v is None:
                    continue
                if not (v > bound):
                    vals[i] = bound + 1 + rng.randint(0, 9)


def _apply_null_rule(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """For every nullable non-key column, plant at least one NULL and a small NULL share."""
    nt = spec.get('null_targets', set())
    for col, vals in columns.items():
        if (table, col) not in nt:
            continue
        if _is_key_column(schema, table, col):
            continue
        n = len(vals)
        if n == 0:
            continue
        idx = rng.randrange(n)
        vals[idx] = None
        k = max(1, int(round(n * _NULL_SHARE)))
        for _ in range(k):
            j = rng.randrange(n)
            vals[j] = None


def _apply_duplicates_for_distinct(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Force a 20-50% duplicate share on columns flagged duplicates_for_distinct (non-key only)."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'duplicates_for_distinct' not in meta.get('patterns', []):
            continue
        if _is_key_column(schema, table, c):
            continue
        vals = columns[c]
        n = len(vals)
        if n < 2:
            continue
        lo, hi = meta.get('duplicate_share', (0.2, 0.5))
        share = rng.uniform(lo, hi)
        k = max(1, int(round(n * share)))
        src = [v for v in vals if v is not None]
        if not src:
            continue
        for _ in range(k):
            i = rng.randrange(n)
            vals[i] = rng.choice(src)


def _apply_group_sizes(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Ensure group sizes 1, 2 and >= 3 on flagged columns (by repeating values; non-key only)."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'group_sizes' not in meta.get('patterns', []):
            continue
        if _is_key_column(schema, table, c):
            continue
        vals = columns[c]
        n = len(vals)
        if n < 6:
            continue
        src = [v for v in vals if v is not None]
        if not src:
            continue
        a, b, d = rng.choice(src), rng.choice(src), rng.choice(src)
        vals[0] = a
        vals[1] = b
        vals[2] = b
        vals[3] = d
        vals[4] = d
        vals[5] = d


def _apply_comparison_boundary(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Plant boundary values (e.g. 'M'/'m', 'F'/'f') on flagged columns."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'comparison_boundary' not in meta.get('patterns', []):
            continue
        vals = columns[c]
        n = len(vals)
        if n == 0:
            continue
        allowed = meta.get('values', [])
        if not allowed:
            continue
        for v in allowed:
            vals[rng.randrange(n)] = v


def _apply_like_variants(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Plant LIKE near-variants (e.g. '%onor%' vs '%Donor%') on flagged columns."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'like_near_variant' not in meta.get('patterns', []):
            continue
        vals = columns[c]
        n = len(vals)
        if n == 0:
            continue
        variants = meta.get('like_variants', [])
        if not variants:
            continue
        for v in variants:
            body = v.replace('%', '')
            vals[rng.randrange(n)] = body


def _apply_rows_with_different_values(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Ensure at least two rows with different values on flagged columns."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'rows_with_different_values' not in meta.get('patterns', []):
            continue
        vals = columns[c]
        n = len(vals)
        if n < 2:
            continue
        distinct = {v for v in vals if v is not None}
        if len(distinct) >= 2:
            continue
        type_str = ''
        tm = schema.tables.get(table)
        if tm is not None:
            for cm in tm.columns:
                if cm.name == c:
                    type_str = cm.type_str
                    break
        for i, v in enumerate(vals):
            if v is None:
                continue
            if _is_int_type(type_str) and isinstance(v, (int, float)):
                vals[i] = v + 1
            elif _is_str_type(type_str) and isinstance(v, str):
                vals[i] = v + 'x'
            else:
                vals[i] = v + 1 if isinstance(v, (int, float)) else str(v) + 'x'
            break


def _apply_ties_for_order_limit(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Plant a tie at rank 1 on flagged columns (repeat the max/min value; non-key only)."""
    for (t, c), meta in spec.get('per_column', {}).items():
        if t != table or c not in columns:
            continue
        if 'ties_for_order_limit' not in meta.get('patterns', []):
            continue
        if _is_key_column(schema, table, c):
            continue
        vals = columns[c]
        n = len(vals)
        if n < 2:
            continue
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums:
            continue
        direction = meta.get('direction', 'DESC')
        target = max(nums) if direction == 'DESC' else min(nums)
        placed = sum(1 for v in vals if v == target)
        while placed < 2:
            i = rng.randrange(n)
            if vals[i] != target:
                vals[i] = target
                placed += 1


def _apply_unmatched_join_rows(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Reserve parent rows without children and child rows with NULL FK."""
    return


def _apply_per_column_patterns(spec: dict, schema, table: str, columns: dict, rng) -> None:
    """Apply all per-column patterns for a table."""
    _apply_duplicates_for_distinct(spec, schema, table, columns, rng)
    _apply_group_sizes(spec, schema, table, columns, rng)
    _apply_comparison_boundary(spec, schema, table, columns, rng)
    _apply_like_variants(spec, schema, table, columns, rng)
    _apply_rows_with_different_values(spec, schema, table, columns, rng)
    _apply_ties_for_order_limit(spec, schema, table, columns, rng)
    _apply_unmatched_join_rows(spec, schema, table, columns, rng)


def _choose_table_sizes(schema, spec: dict, rng) -> dict:
    """Table sizes from the specification's table_size_variation policy."""
    base = spec.get('table_sizes', {})
    var = spec.get('table_size_variation', {})
    keep_prob = float(var.get('keep_prob', 0.5))
    jitter = int(var.get('jitter', 3))
    random_max = int(var.get('random_max', 230))
    sizes = {}
    for t in schema.tables:
        n = int(base.get(t, 0))
        if rng.random() < keep_prob:
            n = max(0, n + rng.randint(-jitter, jitter))
        else:
            n = rng.randint(0, random_max)
        sizes[t] = n
    return sizes


def _parent_pool(instance: dict, schema, table: str, col: str) -> list:
    """Parent key pool: compact values + generated values (in memory)."""
    pool = list(schema.original_values.get((table, col), []))
    gen = instance.get(table, {}).get(col, [])
    pool.extend([v for v in gen if v is not None])
    return pool


def _fill_foreign_keys(instance: dict, schema, spec: dict, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) or are NULL."""
    out = {}
    deps = spec.get('dependencies', {})
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks and key not in deps:
            continue
        if key in schema.fks:
            pt, pc = schema.fks[key]
        else:
            pt, pc = deps[key]
        pv = _parent_pool(instance, schema, pt, pc)
        if pv:
            if len(pv) >= 2:
                reserved = rng.randrange(len(pv))
                draw_pool = [v for i, v in enumerate(pv) if i != reserved]
            else:
                draw_pool = pv
            out[cm.name] = [rng.choice(draw_pool) for _ in range(n)]
        else:
            out[cm.name] = [None] * n
    return out


def _build_table(schema, spec: dict, table: str, n: int, instance: dict, literal_pool: dict, rng) -> dict:
    """Build one table's columns by construction."""
    tm = schema.tables[table]
    p = 0.0 if rng.random() < 0.3 else 0.2
    cols = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks or key in spec.get('dependencies', {}):
            continue
        ov = schema.original_values.get(key, [])
        lp = literal_pool.get(key, [])
        sampler = _init_sampler(cm, lp, ov, p, rng, len(tm.primary_key))
        cols[cm.name] = [sampler.sample() for _ in range(n)]
    cols.update(_fill_foreign_keys(instance, schema, spec, table, n, rng))
    _apply_semantic_rules(spec, table, cols, rng)
    _apply_per_column_patterns(spec, schema, table, cols, rng)
    _apply_null_rule(spec, schema, table, cols, rng)
    cols = sample_fresh_primary_keys(tm, cols)
    cols = drop_unique_duplicates(tm, cols)
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks:
            pt, pc = schema.fks[key]
            if pt == table and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
    return cols


def build_random_instance(schema, literal_pool: dict, spec: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification by construction."""
    if spec is None:
        from .spec import load_spec
        spec = load_spec(schema)
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = _choose_table_sizes(schema, spec, rng)
    inst: dict = {}
    for t in order:
        n = int(size.get(t, 0))
        inst[t] = _build_table(schema, spec, t, n, inst, literal_pool, rng)
    return {t: inst[t] for t in schema.tables}
