"""Random instance construction (fuzz/fuzz.py:83-196), adapted for copy-and-append."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact key), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing_keys), []
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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Combined compact + generated values of the parent key column."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _boundary_values(table: str, col: str) -> set:
    """Values reserved by the spec for a column (never overwritten by duplicate enforcement)."""
    if (table, col) == ('Student', 'Major'):
        return set(spec.MAJOR_BOUNDARY)
    if (table, col) == ('Student', 'Advisor'):
        return set(spec.ADVISOR_BOUNDARY) | {n.replace('%', '') for n in spec.ADVISOR_NEAR}
    if (table, col) == ('Student', 'city_code'):
        return set(spec.CITY_BOUNDARY)
    if (table, col) == ('Student', 'Sex'):
        return set(spec.SEX_BOUNDARY)
    if (table, col) == ('Voting_record', 'Election_Cycle'):
        return set(spec.CYCLE_BOUNDARY)
    return set()


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's combined values; a share is NULL (never out-of-pool)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        col = []
        for _ in range(n):
            u = rng.random()
            if u < spec.UNMATCHED_CHILD_NULL_MIN * 0.0:
                pass
            if pv:
                col.append(rng.choice(pv))
            else:
                col.append(None)
            if rng.random() < 0.02 and pv:
                col[-1] = None
        out[cm.name] = col
    return out


def _plant_nulls(columns: dict, table: str, n: int, rng) -> dict:
    """NULL rule: for every nullable column, plant NULL in a share of rows (>= 1 row)."""
    for (t, c) in spec.NULL_COLUMNS:
        if t != table or c not in columns:
            continue
        share = rng.uniform(spec.NULL_SHARE_MIN, spec.NULL_SHARE_MAX)
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            columns[c][i] = None
    return columns


def _enforce_duplicate_share(columns: dict, table: str, n: int, rng) -> dict:
    """DISTINCT-targeted columns: reuse values from a small pool to reach the duplicate share."""
    for (t, c) in spec.DUP_COLUMNS:
        if t != table or c not in columns:
            continue
        reserved = _boundary_values(t, c)
        share = rng.uniform(spec.DUP_SHARE_MIN, spec.DUP_SHARE_MAX)
        k = max(1, int(round(share * n)))
        if k >= n:
            k = n - 1
        if k <= 0:
            continue
        pool = list({v for v in columns[c] if v is not None and v not in reserved})
        if not pool:
            continue
        candidates = [i for i in range(n) if columns[c][i] not in reserved]
        if not candidates:
            continue
        idx = rng.sample(candidates, min(k, len(candidates)))
        for i in idx:
            columns[c][i] = rng.choice(pool)
    return columns


def _reverify_nulls(columns: dict, table: str, n: int, rng) -> None:
    """Re-plant NULLs if the NULL share is outside [NULL_SHARE_MIN, NULL_SHARE_MAX]."""
    if n == 0:
        return
    for (t, c) in spec.NULL_COLUMNS:
        if t != table or c not in columns:
            continue
        col = columns[c]
        n_null = sum(1 for v in col if v is None)
        share = n_null / n
        if n_null >= 1 and share >= spec.NULL_SHARE_MIN:
            continue
        target = max(1, int(round(spec.NULL_SHARE_TARGET * n)))
        if target <= n_null:
            target = max(1, int(round(spec.NULL_SHARE_MIN * n)))
        need = target - n_null
        cand = [i for i, v in enumerate(col) if v is not None]
        if not cand:
            continue
        for i in rng.sample(cand, min(need, len(cand))):
            col[i] = None


def _reverify_duplicates(columns: dict, table: str, n: int, rng) -> None:
    """Re-plant duplicate share if it is outside [DUP_SHARE_MIN, DUP_SHARE_MAX]."""
    if n == 0:
        return
    for (t, c) in spec.DUP_COLUMNS:
        if t != table or c not in columns:
            continue
        col = columns[c]
        reserved = _boundary_values(t, c)
        non_null = [v for v in col if v is not None]
        if not non_null:
            continue
        n_dup = len(non_null) - len(set(non_null))
        share = n_dup / n
        if share >= spec.DUP_SHARE_MIN:
            continue
        pool = list({v for v in non_null if v not in reserved})
        if not pool:
            continue
        target = max(1, int(round(spec.DUP_SHARE_TARGET * n)))
        need = target - n_dup
        cand = [i for i, v in enumerate(col) if v is not None and v not in reserved]
        if not cand:
            continue
        for i in rng.sample(cand, min(need, len(cand))):
            col[i] = rng.choice(pool)


def choose_table_sizes(schema, rng) -> dict:
    """Fixed compact sizes (spec.table_sizes_per_instance): generated rows per instance."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = spec.STUDENT_ROWS if t == 'Student' else spec.VOTING_ROWS
    return sizes


def _plant_unmatched_joins(inst: dict, schema, rng) -> dict:
    """Plant unmatched-join rows exactly once and report counts."""
    report: dict = {}
    for (ct, cc), (pt, pc) in sorted(schema.fks.items()):
        if ct not in inst or pt not in inst:
            continue
        child_vals = inst[ct].get(cc)
        parent_vals = inst[pt].get(pc)
        if child_vals is None or parent_vals is None:
            continue
        pset = set(v for v in parent_vals if v is not None)
        pset |= set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        bad = [i for i, v in enumerate(child_vals) if v is None]
        if len(bad) < spec.UNMATCHED_CHILD_NULL_MIN and child_vals:
            i = rng.randrange(len(child_vals))
            child_vals[i] = None
            bad = [i]
        referenced = set(v for v in child_vals if v is not None)
        childless = [v for v in parent_vals if v is not None and v not in referenced]
        if len(childless) < spec.UNMATCHED_PARENT_MIN and parent_vals:
            target = parent_vals[rng.randrange(len(parent_vals))]
            for i, v in enumerate(child_vals):
                if v == target:
                    child_vals[i] = None
            referenced = set(v for v in child_vals if v is not None)
            childless = [v for v in parent_vals if v is not None and v not in referenced]
        report['%s.%s->%s.%s' % (ct, cc, pt, pc)] = {
            'child_rows_unmatched': len(bad),
            'parent_rows_without_children': len(childless),
        }
    return report


def _shares(inst: dict) -> dict:
    """Post-generation NULL and duplicate shares per targeted column, reported as fractions in [0,1]."""
    out: dict = {}
    for (t, c) in spec.NULL_COLUMNS:
        col = inst.get(t, {}).get(c)
        if col:
            out['%s.%s.null_share' % (t, c)] = round(sum(1 for v in col if v is None) / len(col), 3)
    for (t, c) in spec.DUP_COLUMNS:
        col = inst.get(t, {}).get(c)
        if col:
            nn = [v for v in col if v is not None]
            if nn:
                out['%s.%s.dup_share' % (t, c)] = round((len(nn) - len(set(nn))) / len(col), 3)
    return out


def build_random_instance(schema, literal_pool: dict, size, rng):
    """Build one random instance (fuzz.py:111-196), adapted for copy-and-append."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
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
        _plant_unmatched_joins(inst, schema, rng)
        cols = _plant_nulls(cols, t, n, rng)
        cols = _enforce_duplicate_share(cols, t, n, rng)
        existing = set()
        if tm.primary_key:
            pk_idx = [c.name for c in tm.columns]
            for row in schema.original_rows.get(t, []):
                existing.add(tuple(row[pk_idx.index(c)] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing)
        cols = drop_unique_duplicates(tm, cols)
        n2 = len(next(iter(cols.values()))) if cols else 0
        _reverify_nulls(cols, t, n2, rng)
        _reverify_duplicates(cols, t, n2, rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    inst = {t: inst[t] for t in schema.tables}
    unmatched = _collect_unmatched_report(inst, schema)
    meta = {'unmatched': unmatched, 'shares': _shares(inst)}
    return inst, meta


def _collect_unmatched_report(inst: dict, schema) -> dict:
    """Read-only recount of the unmatched-join structure (no mutation)."""
    report: dict = {}
    for (ct, cc), (pt, pc) in sorted(schema.fks.items()):
        if ct not in inst or pt not in inst:
            continue
        child_vals = inst[ct].get(cc)
        parent_vals = inst[pt].get(pc)
        if child_vals is None or parent_vals is None:
            continue
        pset = set(v for v in parent_vals if v is not None)
        pset |= set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        bad = [i for i, v in enumerate(child_vals) if v is None]
        referenced = set(v for v in child_vals if v is not None)
        childless = [v for v in parent_vals if v is not None and v not in referenced]
        report['%s.%s->%s.%s' % (ct, cc, pt, pc)] = {
            'child_rows_unmatched': len(bad),
            'parent_rows_without_children': len(childless),
        }
    return report
