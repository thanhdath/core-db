"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
from . import spec
from .values import spec_sampler


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


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent column values: compact rows first, then generated rows (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _parent_tuples(instance: dict, schema, pt: str, pcs: tuple) -> list:
    """Parent tuples (compact + generated) for a composite FK, NULL-free."""
    out = []
    idx = {c: i for i, c in enumerate(pcs)}
    for row in schema.original_rows.get(pt, []):
        t = tuple(row[idx[pc]] for pc in pcs)
        if all(v is not None for v in t):
            out.append(t)
    gen = instance.get(pt, {})
    if all(pc in gen for pc in pcs):
        n = min(len(gen[pc]) for pc in pcs)
        for i in range(n):
            t = tuple(gen[pc][i] for pc in pcs)
            if all(v is not None for v in t):
                out.append(t)
    return out


def _composite_fk_groups(schema, table: str) -> dict:
    """Map parent table -> list of child column tuples that form a composite FK."""
    groups: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct != table:
            continue
        groups.setdefault(pt, []).append(cc)
    return {pt: cols for pt, cols in groups.items() if len(cols) > 1}


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows with replacement; empty parent -> NULL."""
    out = {}
    composite = _composite_fk_groups(schema, table)
    handled = set()
    for pt, child_cols in composite.items():
        pcs = tuple(schema.fks[(table, c)][1] for c in child_cols)
        tuples = _parent_tuples(instance, schema, pt, pcs)
        if tuples:
            picks = [rng.choice(tuples) for _ in range(n)]
            for j, c in enumerate(child_cols):
                out[c] = [p[j] for p in picks]
        else:
            for c in child_cols:
                out[c] = [None] * n
        handled.update(child_cols)
    for cm in schema.tables[table].columns:
        if cm.name in handled:
            continue
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Extra rows appended per table (spec.EXTRA_ROWS); compact rows are kept."""
    sizes = {}
    for t in schema.tables:
        lo, hi = spec.EXTRA_ROWS.get(t, (0, 10))
        sizes[t] = rng.randint(lo, hi)
    return sizes


def _plant_nulls(table: str, cols: dict, rng) -> None:
    """NULL rule: every nullable column gets >=1 NULL row and a 2-5% NULL share."""
    n = _n_rows(cols)
    if n == 0:
        return
    composite_cols = {}
    for (t, group) in spec.COMPOSITE_NULL_FKS:
        if t == table:
            composite_cols[group] = True
    done = set()
    for group in composite_cols:
        present = [c for c in group if c in cols]
        if len(present) != len(group):
            continue
        share = rng.uniform(*spec.NULL_SHARE)
        k = min(n, max(1, int(round(share * n))))
        idx = rng.sample(range(n), k)
        for c in present:
            for i in idx:
                cols[c][i] = None
            done.add(c)
    for (t, c) in spec.NULLABLE:
        if t != table or c not in cols or c in done:
            continue
        share = rng.uniform(*spec.NULL_SHARE)
        k = min(n, max(1, int(round(share * n))))
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[c][i] = None


def _apply_formulas(table: str, cols: dict) -> list:
    """Return the indices of rows that satisfy every semantic formula (Python only)."""
    keep = []
    names = list(cols.keys())
    n = _n_rows(cols)
    for i in range(n):
        row = {c: cols[c][i] for c in names}
        if spec.check_formulas(table, row):
            keep.append(i)
    return keep


def _compact_pk_tuples(schema, table: str, tm) -> set:
    """Full PK tuples of the compact rows (all PK columns)."""
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min(len(c) for c in cols) if cols else 0
    return {tuple(c[i] for c in cols) for i in range(n)}


def _realize_group_sizes(table: str, cols: dict, schema, rng) -> None:
    """Realize group-size targets (1, 2, >=3) on the final written set."""
    for (t, c) in spec.GROUP_SIZE_COLUMNS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 6:
            continue
        if t == 'prereq':
            pool = [v for v in cols[c] if v is not None]
            if len(set(pool)) < 3:
                continue
            vals = rng.sample(sorted(set(pool)), 3)
            cols[c][0] = vals[0]
            cols[c][1] = vals[1]
            cols[c][2] = vals[1]
            for i in range(3, min(n, 6)):
                cols[c][i] = vals[2]
            if 'prereq_id' in cols:
                for i in range(n):
                    if cols['prereq_id'][i] is None:
                        cols['prereq_id'][i] = str(rng.randint(100, 999))


def _realize_department_group_sizes(inst: dict, schema, rng) -> None:
    """Force child tables (course/instructor/student) to produce dept group sizes 1, 2, >=3."""
    depts = [v for v in schema.original_values.get(('department', 'dept_name'), []) if v is not None]
    depts += [v for v in inst.get('department', {}).get('dept_name', []) if v is not None]
    depts = sorted(set(depts))
    if len(depts) < 3:
        return
    counts: dict = {d: 0 for d in depts}
    for child in ('course', 'instructor', 'student'):
        for v in schema.original_values.get((child, 'dept_name'), []):
            if v in counts:
                counts[v] += 1
        for v in inst.get(child, {}).get('dept_name', []):
            if v in counts:
                counts[v] += 1
    order = sorted(depts, key=lambda d: counts[d])
    d1, d2, d3 = order[0], order[1], order[2]
    plan = {d1: 1, d2: 2, d3: 3}
    assigned = {d1: 0, d2: 0, d3: 0}
    for child in ('course', 'instructor', 'student'):
        cols = inst.get(child, {})
        if 'dept_name' not in cols:
            continue
        for i in range(len(cols['dept_name'])):
            for d, need in plan.items():
                if assigned[d] < need:
                    cols['dept_name'][i] = d
                    assigned[d] += 1
                    break


def _revalidate_fks(inst: dict, schema, rng) -> None:
    """Re-point or NULL FK values that no longer exist in the final parent sets."""
    parent_sets: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        s = parent_sets.setdefault((pt, pc), set())
        s.update(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        s.update(v for v in inst.get(pt, {}).get(pc, []) if v is not None)
    parent_tuples: dict = {}
    groups: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        groups.setdefault((ct, pt), []).append(cc)
    for (ct, pt), child_cols in groups.items():
        if len(child_cols) < 2:
            continue
        pcs = tuple(schema.fks[(ct, c)][1] for c in child_cols)
        idx = {c: i for i, c in enumerate(pcs)}
        s = parent_tuples.setdefault(pt, set())
        for row in schema.original_rows.get(pt, []):
            tup = tuple(row[idx[pc]] for pc in pcs)
            if all(v is not None for v in tup):
                s.add(tup)
        gen = inst.get(pt, {})
        if all(pc in gen for pc in pcs):
            n = min(len(gen[pc]) for pc in pcs)
            for i in range(n):
                tup = tuple(gen[pc][i] for pc in pcs)
                if all(v is not None for v in tup):
                    s.add(tup)
    for (ct, cc), (pt, pc) in schema.fks.items():
        cols = inst.get(ct, {})
        if cc not in cols:
            continue
        valid = parent_sets.get((pt, pc), set())
        vals = cols[cc]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in valid:
                vals[i] = rng.choice(sorted(valid)) if valid else None
    for (ct, pt), child_cols in groups.items():
        if len(child_cols) < 2:
            continue
        cols = inst.get(ct, {})
        if not all(c in cols for c in child_cols):
            continue
        tuples = sorted(parent_tuples.get(pt, set()))
        n = min(len(cols[c]) for c in child_cols)
        for i in range(n):
            tup = tuple(cols[c][i] for c in child_cols)
            if all(v is None for v in tup):
                continue
            if any(v is None for v in tup) or tup not in parent_tuples.get(pt, set()):
                if tuples:
                    pick = rng.choice(tuples)
                    for j, c in enumerate(child_cols):
                        cols[c][i] = pick[j]
                else:
                    for c in child_cols:
                        cols[c][i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as *appended* rows."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            inst[t] = {cm.name: [] for cm in tm.columns}
            continue
        compact_pks = _compact_pk_tuples(schema, t, tm)
        taken_ids: set = set()
        for k in compact_pks:
            for v in k:
                if v is not None:
                    taken_ids.add(str(v))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = spec_sampler(t, cm.name, cm, literal_pool.get((t, cm.name), []),
                             schema.original_values.get((t, cm.name), []), rng, taken_ids)
            cols[cm.name] = [s.sample() for _ in range(n)]
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        keep = _apply_formulas(t, cols)
        cols = _filter(cols, keep)
        inst[t] = cols
    _realize_department_group_sizes(inst, schema, rng)
    for t in order:
        if t in inst:
            _realize_group_sizes(t, inst[t], schema, rng)
    for t in order:
        if t in inst:
            _plant_nulls(t, inst[t], rng)
    _revalidate_fks(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}


def verify_group_sizes(schema, instance: dict) -> dict:
    """Verify group-size targets (1, 2, >=3) on the final written set."""
    out = {}
    counts: dict = {}
    for v in schema.original_values.get(('prereq', 'course_id'), []):
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    for v in instance.get('prereq', {}).get('course_id', []):
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    sizes = set(counts.values())
    out['prereq.course_id'] = (1 in sizes) and (2 in sizes) and any(s >= 3 for s in sizes)
    child_counts: dict = {}
    for child in ('course', 'instructor', 'student'):
        for v in schema.original_values.get((child, 'dept_name'), []):
            if v is not None:
                child_counts[v] = child_counts.get(v, 0) + 1
        for v in instance.get(child, {}).get('dept_name', []):
            if v is not None:
                child_counts[v] = child_counts.get(v, 0) + 1
    csizes = set(child_counts.values())
    out['department.dept_name'] = (1 in csizes) and (2 in csizes) and any(s >= 3 for s in csizes)
    return out
