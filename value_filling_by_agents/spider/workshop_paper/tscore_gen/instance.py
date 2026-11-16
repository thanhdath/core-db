"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven samplers."""
import math
from collections import Counter

from .values import _init_sampler

SPEC_SIZES = {'workshop': 6, 'submission': 10, 'Acceptance': 6}
SPEC_NULLABLE = {('submission', 'Scores'), ('submission', 'Author'), ('submission', 'College'),
                 ('workshop', 'Date'), ('workshop', 'Venue'), ('workshop', 'Name'),
                 ('Acceptance', 'Result')}
SPEC_ENUMS = {('Acceptance', 'Result'): ['Accepted', 'Rejected']}
SPEC_RANGES = {('submission', 'Scores'): (0.0, 100.0)}
SPEC_DUP_COLS = {('submission', 'Author'), ('submission', 'College'), ('Acceptance', 'Workshop_ID'),
                 ('Acceptance', 'Submission_ID'), ('workshop', 'Date'), ('workshop', 'Venue')}
SPEC_GROUP_COLS = {('submission', 'Author'), ('submission', 'College')}
SPEC_TIE_COLS = {('submission', 'College'), ('submission', 'Scores')}
SPEC_COMPOSITE_PK = {'Acceptance': ['Submission_ID', 'Workshop_ID']}
SPEC_GROUP_REPORT = {('submission', 'Author'), ('submission', 'College')}


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


def _spec_size(schema, table: str, rng) -> int:
    """Table size: specification size with a small per-instance jitter (0-230 rows allowed)."""
    base = SPEC_SIZES.get(table)
    if base is None:
        return int(rng.randint(0, 30))
    jitter = rng.choice([-1, 0, 0, 0, 1])
    return max(0, min(230, base + jitter))


def _null_share(schema, key: tuple) -> float:
    """NULL share of a nullable column in the compact database (0 if no NULLs observed)."""
    vals = schema.original_values.get(key, [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _apply_null_rule(schema, table: str, cols: dict, rng) -> dict:
    """NULL rule: at least one NULL per nullable column, share following the compact DB; never replace a planted
    NULL."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in SPEC_NULLABLE or cm.name not in cols:
            continue
        if cm.pk_pos > 0 or cm.notnull:
            continue
        share = _null_share(schema, key)
        target = max(1, int(round(share * n)))
        target = min(target, n)
        cur = [i for i, v in enumerate(cols[cm.name]) if v is None]
        if len(cur) >= target:
            continue
        need = target - len(cur)
        cand = [i for i, v in enumerate(cols[cm.name]) if v is not None]
        rng.shuffle(cand)
        for i in cand[:need]:
            cols[cm.name][i] = None
    return cols


def _apply_enum(schema, table: str, cols: dict, rng) -> dict:
    """Enum columns draw only from the enum list (non-NULL values)."""
    for (t, c), vals in SPEC_ENUMS.items():
        if t != table or c not in cols:
            continue
        for i, v in enumerate(cols[c]):
            if v is None:
                continue
            if v not in vals:
                cols[c][i] = rng.choice(vals)
    return cols


def _apply_range(schema, table: str, cols: dict, rng) -> dict:
    """Numeric range rule: clamp into [lo,hi]; include the boundary values themselves."""
    for (t, c), (lo, hi) in SPEC_RANGES.items():
        if t != table or c not in cols:
            continue
        vals = cols[c]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if not nonnull:
            continue
        for i in nonnull:
            try:
                f = float(vals[i])
            except (TypeError, ValueError):
                f = rng.uniform(lo, hi)
            if f < lo or f > hi:
                f = min(hi, max(lo, f))
            vals[i] = f
        rng.shuffle(nonnull)
        planted = [lo, hi]
        for i, v in zip(nonnull, planted):
            vals[i] = v
    return cols


def _apply_ties(schema, table: str, cols: dict, rng) -> dict:
    """tie_at_rank: plant a tie at the top rank for ORDER ..."""
    for (t, c) in SPEC_TIE_COLS:
        if t != table or c not in cols:
            continue
        vals = cols[c]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        rng.shuffle(nonnull)
        if c == 'Scores':
            top = 100.0
            vals[nonnull[0]] = top
            vals[nonnull[1]] = top
            if len(nonnull) >= 4:
                vals[nonnull[2]] = 0.0
                vals[nonnull[3]] = 0.0
        else:
            top = 'Z' + str(rng.randint(0, 10 ** 6))
            vals[nonnull[0]] = top
            vals[nonnull[1]] = top
    return cols


def _dup_k(n: int, rng) -> int:
    """Duplicate count k: share drawn from [0.2,0.5], floored at ceil(0.2*n), capped at n-1."""
    share = rng.uniform(0.2, 0.5)
    k = max(int(math.ceil(0.2 * n)), int(round(share * n)))
    return max(1, min(k, n - 1))


def _apply_duplicates(schema, table: str, cols: dict, rng) -> dict:
    """duplicate_share 20-50 %: force some non-NULL values to repeat an existing value."""
    comp = SPEC_COMPOSITE_PK.get(table)
    for (t, c) in sorted(SPEC_DUP_COLS):
        if t != table or c not in cols:
            continue
        vals = cols[c]
        n = len(vals)
        if n < 2:
            continue
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        k = _dup_k(n, rng)
        k = min(k, len(nonnull) - 1)
        rng.shuffle(nonnull)
        src = nonnull[0]
        for i in nonnull[1:1 + k]:
            vals[i] = vals[src]
        if comp and c in comp:
            _repair_composite_pk(cols, comp, rng)
    return cols


def _repair_composite_pk(cols: dict, comp: list, rng, exclude: set = None) -> None:
    """Re-draw one key column of a composite PK so no full key tuple repeats (in place)."""
    if not all(c in cols for c in comp):
        return
    exclude = exclude or set()
    n = len(cols[comp[0]])
    seen = set()
    for i in range(n):
        k = tuple(cols[c][i] for c in comp)
        if k in seen:
            other = comp[-1]
            pool = [v for v in cols[other] if v is not None and v not in exclude]
            if pool:
                for _ in range(8):
                    cand = rng.choice(pool)
                    k2 = tuple(cand if c == other else cols[c][i] for c in comp)
                    if k2 not in seen:
                        cols[other][i] = cand
                        k = k2
                        break
        seen.add(k)


def _apply_group_sizes(schema, table: str, cols: dict, rng) -> dict:
    """group_sizes "1, 2 and >= 3": ensure at least one group of size 1, one of size 2, one of size >= 3."""
    tm = schema.tables[table]
    pk = set(tm.primary_key)
    for (t, c) in sorted(SPEC_GROUP_COLS):
        if t != table or c not in cols or c in pk:
            continue
        vals = cols[c]
        n = len(vals)
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 6:
            if len(nonnull) < 3:
                continue
        rng.shuffle(nonnull)
        vals[nonnull[0]] = 'g1_' + str(rng.randint(0, 10 ** 6))
        if len(nonnull) >= 3:
            g2 = 'g2_' + str(rng.randint(0, 10 ** 6))
            vals[nonnull[1]] = g2
            vals[nonnull[2]] = g2
        if len(nonnull) >= 6:
            g3 = 'g3_' + str(rng.randint(0, 10 ** 6))
            for i in nonnull[3:6]:
                vals[i] = g3
    return cols


def _ensure_unmatched_parents(schema, instance: dict, rng) -> dict:
    """Parent rows without children: guarantee at least one parent PK value is unreferenced."""
    skips: dict = {}
    for (ct, cc), (pt, pc) in sorted(schema.fks.items()):
        if ct == pt:
            continue
        pv = instance.get(pt, {}).get(pc) or []
        cv = instance.get(ct, {}).get(cc) or []
        if not pv or not cv:
            continue
        uniq_pv = sorted({v for v in pv if v is not None}, key=lambda x: str(x))
        if len(uniq_pv) < 2:
            continue
        referenced = {v for v in cv if v is not None}
        if len(referenced) < len(uniq_pv):
            missing = [v for v in uniq_pv if v not in referenced]
            if missing:
                skips[(ct, cc)] = missing[0]
            continue
        skip = rng.choice(uniq_pv)
        others = [v for v in uniq_pv if v != skip]
        for i, v in enumerate(cv):
            if v == skip:
                cv[i] = rng.choice(others)
        skips[(ct, cc)] = skip
    return skips


def _revalidate_duplicates(schema, instance: dict, rng, skips: dict) -> None:
    """After the unmatched-parent stage, re-plant duplicates if a duplicate share fell below 20 %."""
    for (t, c) in sorted(SPEC_DUP_COLS):
        cols = instance.get(t, {})
        if c not in cols:
            continue
        vals = cols[c]
        n = len(vals)
        if n < 2:
            continue
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        distinct = len({v for v in vals if v is not None})
        dup_share = (len(nonnull) - distinct) / float(n)
        if dup_share >= 0.2:
            continue
        k = _dup_k(n, rng)
        k = min(k, len(nonnull) - 1)
        rng.shuffle(nonnull)
        src = nonnull[0]
        for i in nonnull[1:1 + k]:
            vals[i] = vals[src]
        comp = SPEC_COMPOSITE_PK.get(t)
        if comp and c in comp:
            exclude = set()
            for (ct, cc), skip in skips.items():
                if ct == t and cc in comp:
                    exclude.add(skip)
            _repair_composite_pk(cols, comp, rng, exclude=exclude)


def _revalidate_unmatched_parents(schema, instance: dict, skips: dict) -> dict:
    """Re-check the parent-unmatched invariant after re-planting duplicates."""
    report: dict = {}
    for (ct, cc), (pt, pc) in sorted(schema.fks.items()):
        if ct == pt:
            continue
        pv = instance.get(pt, {}).get(pc) or []
        cv = instance.get(ct, {}).get(cc) or []
        uniq_pv = sorted({v for v in pv if v is not None}, key=lambda x: str(x))
        referenced = {v for v in cv if v is not None}
        missing = [v for v in uniq_pv if v not in referenced]
        if not missing and len(uniq_pv) >= 2:
            skip = skips.get((ct, cc))
            if skip is None or skip not in uniq_pv:
                skip = uniq_pv[0]
            others = [v for v in uniq_pv if v != skip]
            for i, v in enumerate(cv):
                if v == skip:
                    cv[i] = others[0] if others else v
            skips[(ct, cc)] = skip
            referenced = {v for v in cv if v is not None}
            missing = [v for v in uniq_pv if v not in referenced]
        report['%s.%s' % (ct, cc)] = {
            'parent': '%s.%s' % (pt, pc),
            'unmatched': bool(missing),
            'skip': skips.get((ct, cc)),
        }
    return report


def _fresh_pk_values(schema, table: str, n: int, rng) -> list:
    """Fresh integer PK values that do not collide with the compact rows."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    existing = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 1
    return list(range(start, start + n))


def _group_size_stats(cols: dict, col: str) -> dict:
    """Observed group-size distribution for a column (for the stats sidecar)."""
    c = Counter(str(v) for v in cols.get(col, []) if v is not None)
    sizes = Counter(c.values())
    return {'size_1': sizes.get(1, 0), 'size_2': sizes.get(2, 0),
            'size_ge3': sum(n for s, n in sizes.items() if s >= 3)}


def _verify_targets(schema, instance: dict, skips: dict) -> dict:
    """Verify and report the specification targets in the stats sidecar."""
    out: dict = {'group_sizes': {}, 'scores_distinct': None, 'unmatched_parents': {},
                 'null_share': {}}
    for (t, c) in sorted(SPEC_GROUP_REPORT):
        if t in instance and c in instance[t]:
            out['group_sizes']['%s.%s' % (t, c)] = _group_size_stats(instance[t], c)
    if 'submission' in instance and 'Scores' in instance['submission']:
        vals = [v for v in instance['submission']['Scores'] if v is not None]
        out['scores_distinct'] = len({float(v) for v in vals})
    out['unmatched_parents'] = _revalidate_unmatched_parents(schema, instance, skips)
    for (t, c) in sorted(SPEC_NULLABLE):
        out['null_share']['%s.%s' % (t, c)] = round(_null_share(schema, (t, c)), 4)
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification-driven samplers."""
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
        size = {t: _spec_size(schema, t, rng) for t in schema.tables}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        fresh = _fresh_pk_values(schema, t, n, rng)
        if fresh is not None:
            cols[tm.primary_key[0]] = fresh
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_enum(schema, t, cols, rng)
        cols = _apply_range(schema, t, cols, rng)
        cols = _apply_ties(schema, t, cols, rng)
        cols = _apply_duplicates(schema, t, cols, rng)
        cols = _apply_null_rule(schema, t, cols, rng)
        cols = _apply_group_sizes(schema, t, cols, rng)
        inst[t] = cols
    skips = _ensure_unmatched_parents(schema, inst, rng)
    _revalidate_duplicates(schema, inst, rng, skips)
    _revalidate_unmatched_parents(schema, inst, skips)
    inst['__stats__'] = _verify_targets(schema, inst, skips)
    return {t: inst[t] for t in schema.tables}
