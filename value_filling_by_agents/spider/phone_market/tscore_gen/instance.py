"""Random instance construction (fuzz/fuzz.py:83-196) with the specification applied by construction."""
from . import specification as spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _is_int_pk_column(schema, table: str, column: str) -> bool:
    tm = schema.tables[table]
    if tm.primary_key != [column]:
        return False
    cm = next((c for c in tm.columns if c.name == column), None)
    if cm is None:
        return False
    declared = (cm.type_str or '').lower()
    if any(k in declared for k in ('int',)):
        return True
    key = (table, column)
    if key in spec.INT_PRIMARY_KEYS:
        return True
    ov = [v for v in schema.original_values.get(key, []) if v is not None]
    return bool(ov) and all(isinstance(v, int) and not isinstance(v, bool) for v in ov[::max(1, len(ov) // 20)])


def _compact_pk_values(schema, table: str, column: str) -> list:
    return [v for v in schema.original_values.get((table, column), []) if v is not None]


def assign_integer_primary_keys(schema, inst: dict, table: str, n: int, rng) -> dict:
    """Sequential 1..N offset past any compact keys; never NULL; never random."""
    col = spec.INT_PRIMARY_KEYS.get(table)
    if col is None:
        tm = schema.tables[table]
        if len(tm.primary_key) == 1 and _is_int_pk_column(schema, table, tm.primary_key[0]):
            col = tm.primary_key[0]
    if col is None:
        return None
    existing = _compact_pk_values(schema, table, col)
    existing = [int(v) for v in existing if _as_int(v) is not None]
    start = (max(existing) + 1) if existing else 1
    keys = list(range(start, start + n))
    compact = set(existing)
    fixed = []
    nxt = start
    for k in keys:
        while nxt in compact:
            nxt += 1
        fixed.append(nxt)
        nxt += 1
    return fixed


def _as_int(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return None
    try:
        if float(v) != float(iv):
            return None
    except (TypeError, ValueError):
        return None
    return iv


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
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


def choose_compact_aware_pks(table_meta, columns: dict, compact_keys: set) -> dict:
    """Ensure generated PK tuples do not collide with compact PK tuples; drop colliders."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
    seen = set(compact_keys)
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def _render_fk_value(value, render):
    """Render a copied parent key for a text foreign key (spec: text_foreign_key)."""
    if value is None:
        return None
    if render == 'text':
        return str(value)
    return value


def _is_text_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'blob')) and not any(
        k in t for k in ('int', 'real', 'float', 'double', 'numeric', 'decimal'))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the FINAL parent rows (compact + finalised generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        render = 'text' if _is_text_column(cm) else None
        pv = [v for v in (instance.get(pt, {}).get(pc) or []) if v is not None]
        if not pv:
            out[cm.name] = [None] * n
            continue
        distinct = list(dict.fromkeys(pv))
        if len(distinct) >= 2:
            excluded = rng.choice(distinct)
            draw_pool = [v for v in pv if v != excluded]
            if not draw_pool:
                draw_pool = pv
        else:
            draw_pool = pv
        out[cm.name] = [_render_fk_value(rng.choice(draw_pool), render) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes when listed, else uniform rand_lin / level sizes x4 capped at 2500."""
    sizes = {}
    if all(t in spec.TABLE_SIZES for t in schema.tables):
        for t in schema.tables:
            sizes[t] = int(spec.TABLE_SIZES[t])
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


def _apply_group_sizes(inst: dict, schema, rng) -> None:
    """Ensure groups of size 1, 2 and >= 3 exist for listed NON-PK columns (by construction)."""
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for t, c in spec.GROUP_SIZE_COLUMNS:
        if (t, c) in pk_cols:
            continue
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        if len(vals) < 3:
            continue
        base = vals[0]
        if isinstance(base, (int, float)) and not isinstance(base, bool):
            a, b, cc = base, base + 1, base + 2
        else:
            a = base
            b = (str(base) + '_b') if base is not None else 'b'
            cc = (str(base) + '_c') if base is not None else 'c'
        vals[0] = a
        if len(vals) >= 2:
            vals[1] = b
        if len(vals) >= 3:
            vals[2] = b
        for i in range(3, len(vals)):
            vals[i] = cc


def _apply_duplicates(inst: dict, schema, rng) -> None:
    """Duplicate share 20-50 % for DISTINCT columns (phone.Name)."""
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for t, c in spec.DUPLICATE_SHARE:
        if (t, c) in pk_cols:
            continue
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        if len(vals) < 2:
            continue
        lo, hi = spec.DUPLICATE_SHARE[(t, c)]
        share = lo + (hi - lo) * rng.random()
        n_dup = max(1, int(len(vals) * share))
        for i in range(n_dup):
            j = rng.randrange(len(vals))
            vals[i] = vals[j]


def _apply_ties(inst: dict, schema, rng) -> None:
    """Ties for ORDER BY: at least two rows share the sort value."""
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for t, c in spec.TIE_COLUMNS:
        if (t, c) in pk_cols:
            continue
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        if len(vals) >= 2:
            vals[1] = vals[0]


def _apply_different_values(inst: dict, schema, rng) -> None:
    """Rows with different values for scalar MAX: >= 2 distinct values."""
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for t, c in spec.DIFFERENT_VALUE_COLUMNS:
        if (t, c) in pk_cols:
            continue
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        if len(vals) < 2:
            continue
        if vals[0] == vals[1]:
            if isinstance(vals[1], (int, float)) and not isinstance(vals[1], bool):
                vals[1] = vals[1] + 1
            else:
                vals[1] = (str(vals[1]) + 'x') if vals[1] is not None else 'x'


def _coerce_numeric(v):
    """Coerce a sampled value to int/float for a numeric comparison; None if impossible."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            if any(ch in s for ch in '.eE'):
                return float(s)
            return int(s)
        except ValueError:
            return None
    return None


def _coerce_like(v, arg):
    """Coerce v so that comparisons with arg (numeric tuple or string tuple) are possible."""
    if isinstance(arg, tuple) and arg and all(isinstance(a, (int, float)) and not isinstance(a, bool) for a in arg):
        return _coerce_numeric(v)
    return v


def _apply_formulas(inst: dict, schema, rng) -> None:
    """Semantic formulas: a rule holds when its expression is not FALSE (NULL operands pass)."""
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for (t, c), (op, arg) in spec.FORMULAS.items():
        if t not in inst or c not in inst[t]:
            continue
        vals = inst[t][c]
        is_pk = (t, c) in pk_cols
        for i, v in enumerate(vals):
            if v is None:
                continue
            cv = _coerce_like(v, arg) if op in ('>', '>=') else v
            ok = True
            if op == '>':
                ok = cv is not None and cv > arg
            elif op == '>=':
                ok = cv is not None and cv >= arg
            elif op == 'in':
                ok = v in arg
            if ok:
                if cv is not None and cv != v and op in ('>', '>='):
                    vals[i] = cv
                continue
            if is_pk:
                raise ValueError('PK formula failed for %s.%s value %r %s %r' % (t, c, v, op, arg))
            if op == 'in':
                vals[i] = rng.choice(list(arg))
            elif op == '>':
                vals[i] = arg + 1
            elif op == '>=':
                vals[i] = arg


def plant_nulls(inst: dict, schema, table: str, rng) -> None:
    """NULL rule: at least one NULL per nullable non-PK column; share follows compact DB (>=5%)."""
    tm = schema.tables[table]
    cols = inst.get(table)
    if not cols:
        return
    n = _nrows(cols)
    if n == 0:
        return
    for cm in tm.columns:
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if cm.name not in cols:
            continue
        ov = schema.original_values.get((table, cm.name), [])
        base = spec.NULL_SHARE
        if ov:
            nulls = sum(1 for x in ov if x is None)
            base = max(spec.NULL_SHARE, nulls / max(1, len(ov)))
        k = max(1, min(n, int(round(n * base))))
        for i in rng.sample(range(n), k):
            cols[cm.name][i] = None


def _apply_aggregate_boundary(inst: dict, schema, rng) -> None:
    """SUM(phone_market.Num_of_stock) around the aggregate boundary values."""
    t, c = spec.AGGREGATE_BOUNDARY['column']
    if t not in inst or c not in inst[t]:
        return
    vals = inst[t][c]
    non_null_idx = [i for i, v in enumerate(vals) if v is not None]
    if not non_null_idx:
        return
    target = rng.choice(spec.AGGREGATE_BOUNDARY['values'])
    m = len(non_null_idx)
    base = target // m
    rem = target - base * m
    for j, idx in enumerate(non_null_idx):
        vals[idx] = base + (1 if j < rem else 0)


def _rebalance_aggregate(inst: dict, rng) -> None:
    """Re-verify and re-balance SUM(Num_of_stock) over GENERATED non-null rows."""
    t, c = spec.AGGREGATE_BOUNDARY['column']
    if t not in inst or c not in inst[t]:
        return
    vals = inst[t][c]
    non_null_idx = [i for i, v in enumerate(vals) if v is not None]
    if not non_null_idx:
        return
    total = sum(vals[i] for i in non_null_idx)
    targets = spec.AGGREGATE_BOUNDARY['values']
    if total in targets:
        return
    target = min(targets, key=lambda x: abs(x - total))
    m = len(non_null_idx)
    base = max(0, target // m)
    rem = max(0, target - base * m)
    for j, idx in enumerate(non_null_idx):
        vals[idx] = base + (1 if j < rem else 0)


def _refill_table(inst: dict, schema, table: str, target_n: int, samplers: dict, rng,
                  fill_fk) -> None:
    """Refill TABLE[t] to exactly target_n generated rows after dropping transforms."""
    cols = inst[table]
    tm = schema.tables[table]
    n = _nrows(cols)
    if n >= target_n:
        return
    add = target_n - n
    pk_cols = list(tm.primary_key)
    compact = _compact_keys_of(schema, table)
    seen = set(compact)
    for i in range(n):
        seen.add(tuple(cols[c][i] for c in pk_cols)) if pk_cols else None
    added = 0
    guard = 0
    while added < add and guard < 100 * (add + 1):
        guard += 1
        row = {}
        ok = True
        for cm in tm.columns:
            key = (table, cm.name)
            if key in schema.fks:
                continue
            if (table, cm.name) in _pk_columns(schema, table) and cm.pk_pos > 0:
                continue
            s = samplers.get(key)
            row[cm.name] = s.sample() if s is not None else None
        if pk_cols:
            k = tuple(row.get(c) for c in pk_cols)
            if k in seen or any(v is None for v in k):
                continue
            seen.add(k)
        for c, v in row.items():
            cols.setdefault(c, []).append(v)
        added += 1
    for c in cols:
        while len(cols[c]) < target_n:
            cols[c].append(cols[c][-1] if cols[c] else None)


def _pk_columns(schema, table: str) -> set:
    return {(table, c) for c in schema.tables[table].primary_key}


def _compact_keys_of(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    ov = schema.original_values
    n = len(ov.get((table, tm.columns[0].name), [])) if tm.columns else 0
    keys = set()
    for i in range(n):
        keys.add(tuple(ov[(table, c)][i] for c in tm.primary_key))
    return keys


def _verify_fks(inst: dict, schema, table: str) -> None:
    """Confirm every non-NULL FK references a surviving final parent key (rendered exactly)."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        render = 'text' if _is_text_column(cm) else None
        parent_vals = inst.get(pt, {}).get(pc)
        if parent_vals is None:
            continue
        final = {_render_fk_value(v, render) for v in parent_vals if v is not None}
        for v in inst[table][cm.name]:
            if v is None:
                continue
            if v not in final:
                raise ValueError('FK violation %s.%s=%r not in final parent %s.%s' % (table, cm.name, v, pt, pc))


def _apply_pk_formula_assertions(inst: dict, schema) -> None:
    """PK formulas are assertions only; sequential PKs already satisfy them."""
    pk_cols = _pk_columns(schema, None) if False else {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    for (t, c), (op, arg) in spec.FORMULAS.items():
        if (t, c) not in pk_cols:
            continue
        if t not in inst or c not in inst[t]:
            continue
        for v in inst[t][c]:
            if v is None:
                continue
            cv = _coerce_numeric(v)
            ok = True
            if op == '>':
                ok = cv is not None and cv > arg
            elif op == '>=':
                ok = cv is not None and cv >= arg
            elif op == 'in':
                ok = v in arg
            if not ok:
                raise ValueError('PK formula assertion failed for %s.%s value %r %s %r' % (t, c, v, op, arg))


def _finalize_table(inst: dict, schema, table: str, compact_keys: dict, rng,
                    samplers: dict, target_n: int) -> None:
    """Finalise one table's generated rows in place, before any child draws FKs."""
    tm = schema.tables[table]
    cols = inst[table]
    cols = choose_compact_aware_pks(tm, cols, compact_keys.get(table, set()))
    cols = sample_fresh_primary_keys(tm, cols)
    cols = drop_unique_duplicates(tm, cols)
    inst[table] = cols
    _apply_duplicates(inst, schema, rng)
    _apply_ties(inst, schema, rng)
    _apply_different_values(inst, schema, rng)
    _apply_group_sizes(inst, schema, rng)
    _apply_formulas(inst, schema, rng)
    plant_nulls(inst, schema, table, rng)
    _refill_table(inst, schema, table, target_n, samplers, rng, None)


def _fill_pk_column(inst: dict, schema, table: str, n: int, rng) -> list:
    """Assign the sequential single-column integer PK for `table` (length n)."""
    keys = assign_integer_primary_keys(schema, inst, table, n, rng)
    if keys is None:
        return None
    return keys


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance with the specification applied by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and _is_int_pk_column(schema, t, cm.name):
                continue
            samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                  schema.original_values.get((t, cm.name), []), p, rng,
                                                  len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    compact_keys = {}
    for t in order:
        tm = schema.tables[t]
        compact_keys[t] = _compact_keys_of(schema, t)
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        pk_keys = _fill_pk_column(inst, schema, t, n, rng)
        if pk_keys is not None:
            pk_col = spec.INT_PRIMARY_KEYS.get(t) or tm.primary_key[0]
            inst[t][pk_col] = pk_keys
        cols = inst[t]
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        inst[t] = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}
        for cm in tm.columns:
            if cm.name not in inst[t]:
                inst[t][cm.name] = [None] * n
        _finalize_table(inst, schema, t, compact_keys, rng, samplers, n)
    if spec.AGGREGATE_BOUNDARY['column'][0] in inst:
        _apply_aggregate_boundary(inst, schema, rng)
        _rebalance_aggregate(inst, rng)
    _apply_pk_formula_assertions(inst, schema)
    for t in order:
        _verify_fks(inst, schema, t)
    return {t: inst[t] for t in schema.tables}
