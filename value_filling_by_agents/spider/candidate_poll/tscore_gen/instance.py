"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification by construction."""
import re

from .values import _init_sampler

NULL_TARGETS = {('candidate', 'People_ID'), ('candidate', 'Oppose_rate')}
DUPLICATE_TARGETS = {('people', 'Name'), ('candidate', 'Poll_Source')}
GROUP_TARGETS = {('candidate', 'People_ID'), ('people', 'Sex'), ('candidate', 'Poll_Source'),
                 ('candidate', 'Support_rate'), ('candidate', 'Date')}
TIE_TARGETS = {('candidate', 'People_ID'), ('candidate', 'Oppose_rate'), ('candidate', 'Support_rate'),
               ('candidate', 'Unsure_rate'), ('candidate', 'Candidate_ID'), ('people', 'Sex')}
BOUNDARY_TARGETS = {('people', 'Sex'): ['F', 'f']}
DIFFERENT_VALUE_TARGETS = {('candidate', 'Support_rate'), ('candidate', 'Unsure_rate')}
DIFFERENT_VALUE_GROUPS = {('candidate', 'Support_rate'): ('people', 'Sex'),
                          ('candidate', 'Unsure_rate'): ('people', 'Sex')}
PARENT_ROWS_WITHOUT_CHILDREN = True

RATE_RANGES = {('candidate', 'Support_rate'): (0.0, 1.0),
               ('candidate', 'Consider_rate'): (0.0, 1.0),
               ('candidate', 'Oppose_rate'): (0.0, 1.0),
               ('candidate', 'Unsure_rate'): (0.0, 1.0)}
MEASURE_RANGES = {('people', 'Height'): (150.0, 230.0),
                  ('people', 'Weight'): (50.0, 150.0)}
SEX_VALUES = ('M', 'F')
DOB_PATTERN = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')

_SEX_OK = {'M', 'F', 'm', 'f', 'M ', 'F ', ' M', ' F'}


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


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
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


def _compact_null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _null_share_for(schema, table: str, column: str) -> float:
    """NULL share: compact share clamped to 5-30% for flagged columns, else compact share."""
    share = _compact_null_share(schema, table, column)
    if (table, column) in NULL_TARGETS:
        share = min(max(share, 0.05), 0.30)
    return share


def _plant_nulls(schema, table: str, cols: dict, rng) -> dict:
    """NULL rule (applied once, last): every nullable column gets NULL rows with the compact share (>= 1 row only
    when the compact share is > 0 or the column is flagged)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.pk_pos > 0 or cm.notnull or cm.name not in cols:
            continue
        share = _null_share_for(schema, table, cm.name)
        if share <= 0.0:
            continue
        k = max(1, int(round(share * n)))
        k = min(k, n)
        null_idx = [i for i, v in enumerate(cols[cm.name]) if v is None]
        if len(null_idx) >= k:
            continue
        need = k - len(null_idx)
        pool = [i for i in range(n) if cols[cm.name][i] is not None]
        if not pool:
            continue
        for i in rng.sample(pool, min(need, len(pool))):
            cols[cm.name][i] = None
    return cols


def _plant_duplicates(schema, table: str, cols: dict, rng) -> dict:
    """Duplicate share 20-50% for DISTINCT columns (duplicates after joins and filters)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return cols
    for cm in tm.columns:
        if (table, cm.name) not in DUPLICATE_TARGETS or cm.name not in cols:
            continue
        nonnull = [i for i, v in enumerate(cols[cm.name]) if v is not None]
        if len(nonnull) < 2:
            continue
        share = rng.uniform(0.20, 0.50)
        k = max(1, int(round(share * n)))
        k = min(k, len(nonnull) - 1)
        for _ in range(k):
            i, j = rng.sample(nonnull, 2)
            cols[cm.name][j] = cols[cm.name][i]
    return cols


def _rate_variants(base: float, lo: float, hi: float, count: int) -> list:
    """Distinct in-range variants of a rate value, robust to clamping near the bounds."""
    out = []
    span = hi - lo
    for step in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40):
        for sign in (1, -1):
            v = round(base + sign * step, 2)
            if lo <= v <= hi and v != base and v not in out:
                out.append(v)
            if len(out) >= count:
                return out
    for k in range(1, count + 1):
        v = round(lo + span * k / (count + 1), 2)
        if v != base and v not in out:
            out.append(v)
        if len(out) >= count:
            break
    return out


def _plant_group_sizes(schema, table: str, cols: dict, rng) -> dict:
    """Group sizes 1, 2 and >= 3 for GROUP columns (distinct groups)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 6:
        return cols
    for cm in tm.columns:
        if (table, cm.name) not in GROUP_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull = [v for v in vals if v is not None]
        if not nonnull:
            continue
        base = nonnull[0]
        if (table, cm.name) in RATE_RANGES:
            lo, hi = RATE_RANGES[(table, cm.name)]
            base = round(min(max(float(base), lo + 0.1), hi - 0.1), 2)
            variants = _rate_variants(base, lo, hi, 2)
            if len(variants) < 2:
                continue
            g1, g2 = variants[0], variants[1]
        else:
            def _var(k):
                if isinstance(base, (int, float)) and not isinstance(base, bool):
                    return base + k + 1
                return str(base) + str(k + 1)
            g1 = _var(0)
            g2 = _var(1)
            if g1 == base:
                g1 = _var(1)
                g2 = _var(2)
            if g2 in (base, g1):
                g2 = _var(3)
        vals[0] = base
        vals[1] = g1
        vals[2] = g1
        for i in range(3, min(n, 6)):
            vals[i] = g2
        for i in range(6, n):
            if (table, cm.name) in RATE_RANGES:
                lo, hi = RATE_RANGES[(table, cm.name)]
                vals[i] = round(min(max(float(base) + 0.01 * (i - 5), lo), hi), 2)
            elif isinstance(base, (int, float)) and not isinstance(base, bool):
                vals[i] = base + 10 + i
            else:
                vals[i] = str(base) + str(10 + i)
    return cols


def _plant_ties(schema, table: str, cols: dict, rng) -> dict:
    """Ties at rank 1 for ORDER columns: at least two non-NULL rows share the extreme value."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return cols
    for cm in tm.columns:
        if (table, cm.name) not in TIE_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull_idx = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull_idx) < 2:
            continue
        nums = [vals[i] for i in nonnull_idx
                if isinstance(vals[i], (int, float)) and not isinstance(vals[i], bool)]
        if nums:
            extreme = max(nums)
        else:
            extreme = max((vals[i] for i in nonnull_idx), key=lambda x: str(x))
        vals[nonnull_idx[0]] = extreme
        vals[nonnull_idx[1]] = extreme
    return cols


def _plant_boundaries(schema, table: str, cols: dict, rng) -> dict:
    """Boundary literals: one row at the literal and one step on each side (case variant)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 3:
        return cols
    for cm in tm.columns:
        lits = BOUNDARY_TARGETS.get((table, cm.name))
        if not lits or cm.name not in cols:
            continue
        lit = lits[0]
        vals = cols[cm.name]
        idx = [i for i, v in enumerate(vals) if v is not None]
        if len(idx) < 3:
            continue
        vals[idx[0]] = lit
        vals[idx[1]] = lit.lower() if lit.isupper() else lit.upper()
        vals[idx[2]] = lit + ' '
    return cols


def _enforce_rate_ranges(schema, table: str, cols: dict) -> dict:
    for cm in schema.tables[table].columns:
        rng_ = RATE_RANGES.get((table, cm.name))
        if not rng_ or cm.name not in cols:
            continue
        lo, hi = rng_
        cols[cm.name] = [None if v is None else round(min(max(float(v), lo), hi), 2) for v in cols[cm.name]]
    return cols


def _enforce_measure_ranges(schema, table: str, cols: dict) -> dict:
    for cm in schema.tables[table].columns:
        rng_ = MEASURE_RANGES.get((table, cm.name))
        if not rng_ or cm.name not in cols:
            continue
        lo, hi = rng_
        cols[cm.name] = [None if v is None else round(min(max(float(v), lo), hi), 1) for v in cols[cm.name]]
    return cols


def _enforce_sex(schema, table: str, cols: dict) -> dict:
    """Sex case-insensitive IN (M,F): preserve case/whitespace boundary variants of M/F."""
    if table != 'people' or 'Sex' not in cols:
        return cols
    out = []
    for v in cols['Sex']:
        if v is None:
            out.append(None)
        elif v in _SEX_OK:
            out.append(v)
        else:
            s = str(v).strip()
            if s.upper() == 'F':
                out.append('F')
            elif s.upper() == 'M':
                out.append('M')
            else:
                out.append('M')
    cols['Sex'] = out
    return cols


def _enforce_dob(schema, table: str, cols: dict) -> dict:
    if table != 'people' or 'Date_of_Birth' not in cols:
        return cols
    out = []
    for v in cols['Date_of_Birth']:
        if v is None or DOB_PATTERN.match(str(v)):
            out.append(v)
        elif isinstance(v, str) and re.fullmatch(r'\d{2}[-/]\d{2}[-/]\d{4}', v):
            out.append(v.replace('-', '.').replace('/', '.'))
        else:
            out.append('01.01.1975')
    cols['Date_of_Birth'] = out
    return cols


def _enforce_domain(schema, table: str, cols: dict) -> dict:
    cols = _enforce_rate_ranges(schema, table, cols)
    cols = _enforce_measure_ranges(schema, table, cols)
    cols = _enforce_sex(schema, table, cols)
    cols = _enforce_dob(schema, table, cols)
    return cols


def _fk_col_for_group(schema, table: str, gt: str, gc: str):
    """Find the child FK column that references (gt, gc)."""
    tm = schema.tables[table]
    for cm2 in tm.columns:
        pt, pc = schema.fks.get((table, cm2.name), (None, None))
        if pt == gt and pc == gc:
            return cm2.name
    return None


def _group_labels(schema, table: str, cols: dict, inst: dict, group_col) -> list:
    """Per-row group label from the parent's grouping column (None = excluded from grouping)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if group_col is None:
        return ['0'] * n
    gt, gc = group_col
    fk_col = _fk_col_for_group(schema, table, gt, gc)
    groups = [None] * n
    if fk_col is None or fk_col not in cols:
        return groups
    parent_pk = schema.tables[gt].primary_key
    pk_name = parent_pk[0] if parent_pk else None
    if pk_name is None:
        return groups
    pkeys = inst.get(gt, {}).get(pk_name, [])
    gvals = inst.get(gt, {}).get(gc, [])
    lookup = dict(zip(pkeys, gvals))
    for i in range(n):
        child = cols[fk_col][i]
        if child is not None and child in lookup:
            groups[i] = str(lookup[child])
    return groups


def _enforce_different_values(schema, table: str, cols: dict, inst: dict, rng) -> dict:
    """>= 2 qualifying rows per group with different values for aggregate columns."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return cols
    for cm in tm.columns:
        if (table, cm.name) not in DIFFERENT_VALUE_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        tie_idx = set()
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) >= 2:
            nums = [vals[i] for i in nonnull
                    if isinstance(vals[i], (int, float)) and not isinstance(vals[i], bool)]
            if nums:
                ext = max(nums)
                tie_cand = [i for i in nonnull if vals[i] == ext]
            else:
                ext = max((vals[i] for i in nonnull), key=lambda x: str(x))
                tie_cand = [i for i in nonnull if vals[i] == ext]
            tie_idx |= set(tie_cand[:2])
        groups = _group_labels(schema, table, cols, inst, DIFFERENT_VALUE_GROUPS.get((table, cm.name)))
        seen_by_group: dict = {}
        for i in range(n):
            if vals[i] is None or groups[i] is None:
                continue
            seen_by_group.setdefault(groups[i], []).append(i)
        for g, idxs in seen_by_group.items():
            if len(idxs) < 2:
                continue
            if len({vals[i] for i in idxs}) >= 2:
                continue
            pick = [i for i in idxs if i not in tie_idx]
            if not pick:
                pick = idxs
            i = pick[0]
            base = vals[i]
            if isinstance(base, (int, float)) and not isinstance(base, bool):
                lo, hi = RATE_RANGES.get((table, cm.name), (0.0, 1.0))
                v = round(float(base) + 0.01, 2)
                if v > hi:
                    v = round(float(base) - 0.01, 2)
                vals[i] = round(min(max(v, lo), hi), 2)
            elif isinstance(base, str):
                vals[i] = base + str(len(idxs))
    return cols


def _fresh_primary_keys(schema, table: str, cols: dict, rng) -> dict:
    """Primary keys fresh against the compact rows: sequential integers above the compact max."""
    tm = schema.tables[table]
    if not tm.primary_key or not cols:
        return cols
    n = len(next(iter(cols.values())))
    for pk in tm.primary_key:
        if pk not in cols:
            continue
        compact = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
        start = (max(compact) + 1) if compact else 1
        cols[pk] = list(range(start, start + n))
    return cols


def _final_parent_keys(schema, table: str, inst: dict, pc: str) -> list:
    """FINAL parent key set actually written: compact values + generated values."""
    compact = [v for v in schema.original_values.get((table, pc), []) if v is not None]
    generated = [v for v in inst.get(table, {}).get(pc, []) if v is not None]
    return compact + generated


def _fk_from_parents(schema, table: str, cols: dict, inst: dict, rng, reserved: dict) -> dict:
    """FK columns ALWAYS get a list of length n (final parent keys, or NULL share)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        parent_vals = _final_parent_keys(schema, pt, inst, pc)
        if pt != table and pt in reserved:
            rk = reserved[pt]
            draw_vals = [v for v in parent_vals if v != rk]
            if not draw_vals:
                draw_vals = parent_vals
        else:
            draw_vals = parent_vals
        if not draw_vals:
            cols[cm.name] = [None] * n
            continue
        share = _null_share_for(schema, table, cm.name)
        k = max(1, int(round(share * n))) if (n and share > 0) else 0
        k = min(k, n)
        null_idx = set(rng.sample(range(n), k)) if k else set()
        vals = [None if i in null_idx else rng.choice(draw_vals) for i in range(n)]
        pset = set(parent_vals)
        for v in vals:
            if v is not None and v not in pset:
                raise AssertionError('orphan FK %s.%s=%r not in %s.%s' % (table, cm.name, v, pt, pc))
        cols[cm.name] = vals
    return cols


def _verify_and_replant(schema, table: str, cols: dict, inst: dict, rng) -> dict:
    """Check each per_column_exceptions target on the final column lists and re-plant any that were destroyed."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols

    for cm in tm.columns:
        if (table, cm.name) not in GROUP_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        counts: dict = {}
        for v in vals:
            if v is None:
                continue
            counts[v] = counts.get(v, 0) + 1
        sizes = sorted(counts.values())
        has1 = 1 in sizes
        has2 = 2 in sizes
        has3 = any(s >= 3 for s in sizes)
        if has1 and has2 and has3:
            continue
        nonnull_idx = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull_idx) < 6:
            continue
        base = vals[nonnull_idx[0]]
        if (table, cm.name) in RATE_RANGES:
            lo, hi = RATE_RANGES[(table, cm.name)]
            base = round(min(max(float(base), lo + 0.1), hi - 0.1), 2)
            variants = _rate_variants(base, lo, hi, 2)
            if len(variants) < 2:
                continue
            g1, g2 = variants[0], variants[1]
        else:
            if isinstance(base, (int, float)) and not isinstance(base, bool):
                g1, g2 = base + 1, base + 2
            else:
                g1, g2 = str(base) + '1', str(base) + '2'
        vals[nonnull_idx[0]] = base
        vals[nonnull_idx[1]] = g1
        vals[nonnull_idx[2]] = g1
        for k in range(3, min(len(nonnull_idx), 6)):
            vals[nonnull_idx[k]] = g2

    for cm in tm.columns:
        if (table, cm.name) not in TIE_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull_idx = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull_idx) < 2:
            continue
        nums = [vals[i] for i in nonnull_idx
                if isinstance(vals[i], (int, float)) and not isinstance(vals[i], bool)]
        if nums:
            extreme = max(nums)
        else:
            extreme = max((vals[i] for i in nonnull_idx), key=lambda x: str(x))
        tied = [i for i in nonnull_idx if vals[i] == extreme]
        if len(tied) >= 2:
            continue
        vals[nonnull_idx[0]] = extreme
        vals[nonnull_idx[1]] = extreme

    for cm in tm.columns:
        if (table, cm.name) not in DUPLICATE_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull_idx = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull_idx) < 2:
            continue
        distinct = len({vals[i] for i in nonnull_idx})
        dup_share = 1.0 - distinct / float(len(nonnull_idx))
        if 0.20 <= dup_share <= 0.50:
            continue
        target_dup = max(1, int(round(0.30 * len(nonnull_idx))))
        for _ in range(target_dup):
            i, j = rng.sample(nonnull_idx, 2)
            vals[j] = vals[i]

    for cm in tm.columns:
        lits = BOUNDARY_TARGETS.get((table, cm.name))
        if not lits or cm.name not in cols:
            continue
        lit = lits[0]
        vals = cols[cm.name]
        nonnull_idx = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull_idx) < 3:
            continue
        present = {vals[i] for i in nonnull_idx}
        need = [lit, lit.lower() if lit.isupper() else lit.upper(), lit + ' ']
        missing = [x for x in need if x not in present]
        if not missing:
            continue
        for k, x in enumerate(missing):
            if k < len(nonnull_idx):
                vals[nonnull_idx[k]] = x

    for cm in tm.columns:
        if (table, cm.name) not in DIFFERENT_VALUE_TARGETS or cm.name not in cols:
            continue
        vals = cols[cm.name]
        groups = _group_labels(schema, table, cols, inst, DIFFERENT_VALUE_GROUPS.get((table, cm.name)))
        by_group: dict = {}
        for i in range(n):
            if vals[i] is None or groups[i] is None:
                continue
            by_group.setdefault(groups[i], []).append(i)
        for g, idxs in by_group.items():
            if len(idxs) < 2:
                continue
            if len({vals[i] for i in idxs}) >= 2:
                continue
            i = idxs[0]
            base = vals[i]
            if isinstance(base, (int, float)) and not isinstance(base, bool):
                lo, hi = RATE_RANGES.get((table, cm.name), (0.0, 1.0))
                v = round(float(base) + 0.01, 2)
                if v > hi:
                    v = round(float(base) - 0.01, 2)
                vals[i] = round(min(max(v, lo), hi), 2)
            elif isinstance(base, str):
                vals[i] = base + 'x'
    return cols


def _reserve_parent_keys(schema, inst: dict, rng) -> dict:
    """Reserve one parent key per parent table that has children, so at least one parent row has no children by
    construction."""
    reserved: dict = {}
    parents_with_children = {pt for (ct, cc), (pt, pc) in schema.fks.items() if pt != ct}
    for pt in parents_with_children:
        tm = schema.tables.get(pt)
        if not tm or not tm.primary_key:
            continue
        pk = tm.primary_key[0]
        keys = _final_parent_keys(schema, pt, inst, pk)
        if keys:
            reserved[pt] = rng.choice(keys)
    return reserved


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the round-1 specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key),
                                                       nullable=not cm.notnull and cm.pk_pos == 0)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        cols = _fresh_primary_keys(schema, t, cols, rng)
        cols = _enforce_domain(schema, t, cols)
        cols = _plant_ties(schema, t, cols, rng)
        cols = _plant_group_sizes(schema, t, cols, rng)
        cols = _plant_boundaries(schema, t, cols, rng)
        inst[t] = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}
        cols = _enforce_different_values(schema, t, cols, inst, rng)
        cols = _plant_duplicates(schema, t, cols, rng)
        inst[t] = cols
        reserved = _reserve_parent_keys(schema, inst, rng)
        cols = _fk_from_parents(schema, t, cols, inst, rng, reserved)
        inst[t] = cols
        cols = _plant_nulls(schema, t, cols, rng)
        inst[t] = cols
        cols = _verify_and_replant(schema, t, cols, inst, rng)
        cols = _enforce_domain(schema, t, cols)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        cols = _verify_and_replant(schema, t, cols, inst, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
