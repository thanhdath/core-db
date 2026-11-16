"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
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


def _spec_key(table: str, column: str) -> str:
    return '%s.%s' % (table, column)


def _col_spec(spec: dict, table: str, column: str) -> dict:
    """Per-column specification slice: enum, range, boundaries, numeric-string flag."""
    key = _spec_key(table, column)
    out = {'enum': None, 'lo': None, 'hi': None, 'boundaries': [], 'numeric_string': False}
    enums = spec.get('enums') or {}
    if key in enums:
        out['enum'] = list(enums[key])
    ranges = spec.get('ranges') or {}
    if key in ranges:
        lo, hi = ranges[key]
        out['lo'], out['hi'] = lo, hi
    bounds = spec.get('boundaries') or {}
    if key in bounds:
        out['boundaries'] = list(bounds[key])
    return out


def _is_numeric_text(schema, table: str, column: str) -> bool:
    vals = [v for v in schema.original_values.get((table, column), []) if v is not None]
    if not vals:
        return False
    for v in vals:
        try:
            float(v)
        except (TypeError, ValueError):
            return False
    return True


def _parent_keys(schema, instance: dict, pt: str, pc: str) -> list:
    """Parent key values: compact rows first, then generated rows (in memory)."""
    out = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    out += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return out


def _is_nullable(schema, table: str, column: str) -> bool:
    tm = schema.tables.get(table)
    if tm is None:
        return False
    cm = next((x for x in tm.columns if x.name == column), None)
    if cm is None:
        return False
    return (not cm.notnull) and cm.pk_pos == 0


def _fill_foreign_keys(instance: dict, schema, table: str, n: int, rng, spec: dict,
                       null_targets: set) -> dict:
    """FK child columns draw from the parent's compact+generated values; NULL by the NULL rule."""
    out = {}
    cmp_pairs = set()
    for a, b in spec.get('comparison_boundary') or []:
        cmp_pairs.add((a, b))
        cmp_pairs.add((b, a))
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_keys(schema, instance, pt, pc)
        col_key = _spec_key(table, cm.name)
        nullable = _is_nullable(schema, table, cm.name)
        pv_set = set(pv)
        vals = []
        for i in range(n):
            if nullable and (col_key in null_targets or rng.random() < 0.05):
                vals.append(None)
                continue
            if not pv:
                vals.append(None)
                continue
            if (col_key, _spec_key(pt, pc)) in cmp_pairs and rng.random() < 0.3:
                base = rng.choice(pv)
                try:
                    cand = int(base) + rng.choice([-1, 0, 1])
                except (TypeError, ValueError):
                    cand = base
                vals.append(cand if cand in pv_set else base)
                continue
            vals.append(rng.choice(pv))
        out[cm.name] = vals
    return out


def _plantable(table_meta, column: str) -> bool:
    """Planting helpers never touch PK or UNIQUE columns."""
    cm = next((x for x in table_meta.columns if x.name == column), None)
    if cm is None:
        return False
    return cm.pk_pos == 0 and not cm.unique


def _plant_group_sizes(columns: dict, column: str, n: int, rng) -> None:
    """On GROUP-target columns produce groups of size 1, 2 and >= 3 (in place)."""
    if column not in columns or n < 6:
        return
    vals = columns[column]
    uniq = []
    for v in vals:
        if v not in uniq:
            uniq.append(v)
        if len(uniq) >= 3:
            break
    while len(uniq) < 3:
        uniq.append('g%d' % len(uniq))
    plan = [uniq[0]] + [uniq[1]] * 2 + [uniq[2]] * max(3, n - 3)
    plan = plan[:n]
    rng.shuffle(plan)
    columns[column] = plan


def _plant_duplicates(columns: dict, column: str, n: int, rng) -> None:
    """On DISTINCT-target columns allow 20-50% duplicate values (in place)."""
    if column not in columns or n < 4:
        return
    vals = columns[column]
    k = max(1, int(n * rng.uniform(0.2, 0.5)))
    for _ in range(k):
        i, j = rng.randrange(n), rng.randrange(n)
        if i != j:
            vals[j] = vals[i]


def _plant_order_ties(columns: dict, column: str, n: int, rng, rank: int) -> None:
    """On ORDER/LIMIT-target columns plant ties at the listed rank (in place)."""
    if column not in columns or n < 2:
        return
    vals = columns[column]
    if rank <= 0 or rank > n:
        rank = 1
    vals[rank - 1] = vals[0]


def _drop_child_rows(instance: dict, ct: str, cc: str, predicate) -> None:
    """Drop child rows whose FK value satisfies predicate (keeps FK valid, no NULLs)."""
    cols = instance.get(ct)
    if not cols or cc not in cols:
        return
    n = len(cols[cc])
    keep = [i for i in range(n) if not predicate(cols[cc][i])]
    if len(keep) == n:
        return
    for c in list(cols.keys()):
        cols[c] = [cols[c][i] for i in keep]


def _plant_parent_without_children(instance: dict, schema, spec: dict, rng) -> None:
    """Ensure at least one parent row (compact or generated) has no child rows."""
    for key in spec.get('parent_without_children') or []:
        if '.' not in key:
            continue
        pt, pc = key.split('.', 1)
        if pt not in schema.tables:
            continue
        children = [(t, c) for (t, c), (pp, pcc) in schema.fks.items() if pp == pt and pcc == pc]
        if not children:
            continue
        ct, cc = children[0]
        used = set(v for v in instance.get(ct, {}).get(cc, []) if v is not None)
        used |= set(v for v in schema.original_values.get((ct, cc), []) if v is not None)
        parents = _parent_keys(schema, instance, pt, pc)
        if parents and all(p in used for p in parents):
            victim = parents[0]
            _drop_child_rows(instance, ct, cc, lambda v, x=victim: v == x)


def _plant_aggregate_boundary(instance: dict, schema, spec: dict, rng) -> None:
    """Aggregate boundary: some parent keys have 0, 1 and 2 child rows (COUNT(*))."""
    for key in spec.get('aggregate_boundary') or []:
        if '.' not in key:
            continue
        t, c = key.split('.', 1)
        if t not in schema.tables:
            continue
        children = [(ct, cc) for (ct, cc), (pt, pc) in schema.fks.items() if pt == t and pc == c]
        if not children:
            continue
        ct, cc = children[0]
        col = instance.get(ct, {}).get(cc)
        if not col:
            continue
        parents = _parent_keys(schema, instance, t, c)
        if len(parents) < 3:
            continue
        p0, p1, p2 = parents[0], parents[1], parents[2]
        _drop_child_rows(instance, ct, cc, lambda v, x=p0: v == x)
        col = instance.get(ct, {}).get(cc)
        if col:
            seen = 0
            drop = []
            for i, v in enumerate(col):
                if v == p1:
                    seen += 1
                    if seen > 1:
                        drop.append(i)
            if drop:
                keep = [i for i in range(len(col)) if i not in set(drop)]
                for cc2 in list(instance[ct].keys()):
                    instance[ct][cc2] = [instance[ct][cc2][i] for i in keep]
        col = instance.get(ct, {}).get(cc)
        if col:
            seen = 0
            drop = []
            for i, v in enumerate(col):
                if v == p2:
                    seen += 1
                    if seen > 2:
                        drop.append(i)
            if drop:
                keep = [i for i in range(len(col)) if i not in set(drop)]
                for cc2 in list(instance[ct].keys()):
                    instance[ct][cc2] = [instance[ct][cc2][i] for i in keep]


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification table sizes per instance (fallback: upstream rand_lin / level sizes)."""
    fixed = spec.get('table_sizes') or {}
    sizes = {}
    if fixed:
        for t in schema.tables:
            n = fixed.get(t)
            if n is None:
                n = int(30 * rng.random() + int(rng.random() * 200))
            sizes[t] = int(n)
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


def _fresh_pk_values(schema, table: str, column: str, n: int, rng, spec: dict) -> list:
    """Fresh primary-key integers: sequential from max(compact)+1, never NULL."""
    existing = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 1
    return [start + i for i in range(n)]


def _dedupe_against_compact(schema, table: str, columns: dict) -> dict:
    """Drop generated rows whose PK tuple collides with a compact PK tuple."""
    tm = schema.tables[table]
    if not tm.primary_key or not columns:
        return columns
    compact = set()
    n_compact = len(schema.original_values.get((table, tm.primary_key[0]), []))
    for i in range(n_compact):
        try:
            compact.add(tuple(schema.original_values[(table, c)][i] for c in tm.primary_key))
        except (KeyError, IndexError):
            pass
    n = len(next(iter(columns.values())))
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in tm.primary_key)
        if k not in compact:
            keep.append(i)
    return _filter(columns, keep)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    spec = spec or {}
    null_targets = set(spec.get('null_targets') or [])
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            cs = _col_spec(spec, t, cm.name)
            numeric_string = _is_numeric_text(schema, t, cm.name) and 'text' in (cm.type_str or '').lower()
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), enum_values=cs['enum'], lo=cs['lo'], hi=cs['hi'],
                boundaries=cs['boundaries'], numeric_string=numeric_string)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and len(tm.primary_key) == 1 and _is_int_type(cm.type_str):
                cols[cm.name] = _fresh_pk_values(schema, t, cm.name, n, rng, spec)
            else:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        inst[t] = cols
        fk_cols = _fill_foreign_keys(inst, schema, t, n, rng, spec, null_targets)
        cols.update(fk_cols)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        cols = _dedupe_against_compact(schema, t, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for key in spec.get('group_sizes') or []:
        if '.' in key:
            t, c = key.split('.', 1)
            if t in inst and _plantable(schema.tables[t], c):
                _plant_group_sizes(inst[t], c, len(inst[t].get(c, [])), rng)
    for key in spec.get('distinct_dups') or []:
        if '.' in key:
            t, c = key.split('.', 1)
            if t in inst and _plantable(schema.tables[t], c):
                _plant_duplicates(inst[t], c, len(inst[t].get(c, [])), rng)
    for key, tgt in (spec.get('order_ties') or {}).items():
        if '.' in key:
            t, c = key.split('.', 1)
            if t in inst and _plantable(schema.tables[t], c):
                _plant_order_ties(inst[t], c, len(inst[t].get(c, [])), rng, int(tgt.get('rank', 1)))
    _plant_parent_without_children(inst, schema, spec, rng)
    _plant_aggregate_boundary(inst, schema, spec, rng)
    for t in list(inst.keys()):
        tm = schema.tables[t]
        inst[t] = sample_fresh_primary_keys(tm, inst[t])
        inst[t] = drop_unique_duplicates(tm, inst[t])
        inst[t] = _dedupe_against_compact(schema, t, inst[t])
    return {t: inst[t] for t in schema.tables}


def _is_int_type(t: str) -> bool:
    t = (t or '').lower()
    return 'int' in t and 'point' not in t
