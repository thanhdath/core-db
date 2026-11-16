"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt

from . import spec
from .values import (rand_date, rand_date_after, rand_name, rand_amount, rand_small,
                     rand_enum, pad_char, group_size_plan, duplicate_plan, tie_plan,
                     null_plan, _init_sampler)


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


def _is_date_col(cm):
    t = (cm.type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _is_int_col(cm):
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'number', 'numeric', 'decimal', 'real', 'float', 'double'))


def _is_char_col(cm):
    t = (cm.type_str or '').lower()
    return 'char' in t or 'text' in t or 'varchar' in t


def _char_len(cm):
    import re
    m = re.search(r'\((\d+)\)', cm.type_str or '')
    return int(m.group(1)) if m else 15


def _sample_base_values(table, cm, n, rng, literal_pool, original_values):
    """Sample n independent values for a non-FK, non-derived column."""
    key = (table, cm.name)
    if key in spec.ENUMS:
        vals = spec.ENUMS[key]
        out = [rand_enum(rng, vals) for _ in range(n)]
        if _is_char_col(cm) and 'char' in (cm.type_str or '').lower():
            L = _char_len(cm)
            out = [pad_char(v, L) for v in out]
        return out
    if cm.name.lower() in ('customer_details', 'name', 'details'):
        return [rand_name(rng) for _ in range(n)]
    if _is_date_col(cm):
        return [rand_date(rng) for _ in range(n)]
    if _is_int_col(cm):
        if 'amount' in cm.name.lower():
            return [rand_amount(rng) for _ in range(n)]
        return [rand_small(rng) for _ in range(n)]
    s = _init_sampler(cm, literal_pool.get(key, []), original_values.get(key, []), 0.2, rng,
                      len(schema_pk_placeholder(cm)))
    return [s.sample() for _ in range(n)]


def schema_pk_placeholder(cm):
    return [cm.name] if cm.pk_pos > 0 else []


def _apply_group_size_plan(table, cm, values, rng):
    """Make the value multiset contain groups of size 1, 2 and >= 3."""
    key = (table, cm.name)
    if key not in spec.GROUP_SIZE_TARGETS or not values:
        return values
    n = len(values)
    if n < 6:
        return values
    reps = []
    seen = set()
    for v in values:
        if v not in seen:
            seen.add(v)
            reps.append(v)
    while len(reps) < 3:
        base = reps[0] if reps else values[0]
        if isinstance(base, dt.date):
            cand = base + dt.timedelta(days=len(reps) + 1)
        elif isinstance(base, int):
            cand = base + len(reps) + 1
        elif isinstance(base, str):
            cand = base + '_' + str(len(reps))
        else:
            cand = base
        if cand not in seen:
            seen.add(cand)
            reps.append(cand)
        else:
            reps.append(cand)
    plan = group_size_plan(rng, n)
    out = list(values)
    gid_to_rep = {0: reps[0], 1: reps[1], 2: reps[2]}
    next_rep = 3
    for i, gid in enumerate(plan):
        if gid not in gid_to_rep:
            if next_rep < len(reps):
                gid_to_rep[gid] = reps[next_rep]
                next_rep += 1
            else:
                base = reps[0]
                if isinstance(base, dt.date):
                    cand = base + dt.timedelta(days=1000 + gid)
                elif isinstance(base, int):
                    cand = base + 1000 + gid
                elif isinstance(base, str):
                    cand = base + '_g' + str(gid)
                else:
                    cand = base
                gid_to_rep[gid] = cand
        out[i] = gid_to_rep[gid]
    return out


def _apply_duplicate_plan(table, cm, values, rng):
    """Ensure duplicate_share in 20-50 % of rows (duplicates_for_distinct)."""
    key = (table, cm.name)
    if key not in spec.DISTINCT_TARGETS or not values:
        return values
    n = len(values)
    flags = duplicate_plan(rng, n)
    out = list(values)
    for i in range(n):
        if flags[i] and i > 0:
            out[i] = out[rng.randrange(i)]
    return out


def _apply_tie_plan(table, cm, values, rng):
    """Ensure a tie at LIMIT rank 1 (ties_for_order_limit)."""
    key = (table, cm.name)
    if key not in spec.TIE_TARGETS or not values:
        return values
    direction, tie_on = spec.TIE_TARGETS[key]
    n = len(values)
    out = list(values)
    if tie_on == 'COUNT':
        distinct = []
        seen = set()
        for v in out:
            if v is not None and v not in seen:
                seen.add(v)
                distinct.append(v)
        if len(distinct) < 2:
            base = distinct[0] if distinct else out[0]
            if isinstance(base, str):
                extra = base + '_x'
            elif isinstance(base, int):
                extra = base + 1
            elif isinstance(base, dt.date):
                extra = base + dt.timedelta(days=1)
            else:
                extra = base
            distinct.append(extra)
        top = max(2, n // max(2, len(distinct)))
        counts = {distinct[0]: top, distinct[1]: top}
        remaining = n - 2 * top
        idx = 2
        while remaining > 0 and idx < len(distinct):
            c = min(remaining, max(1, top - 1))
            counts[distinct[idx]] = c
            remaining -= c
            idx += 1
        if remaining > 0:
            counts[distinct[0]] += remaining
        seq = []
        for v, c in counts.items():
            seq.extend([v] * c)
        seq = seq[:n]
        while len(seq) < n:
            seq.append(distinct[0])
        rng.shuffle(seq)
        return seq
    flags = tie_plan(rng, n)
    try:
        if direction == 'ASC':
            rank1 = min(v for v in out if v is not None)
        else:
            rank1 = max(v for v in out if v is not None)
    except ValueError:
        return values
    for i in range(n):
        if flags[i]:
            out[i] = rank1
    return out


def _apply_null_plan(table, cm, values, rng):
    """NULL rule: nullable columns get NULL and non-NULL rows."""
    key = (table, cm.name)
    if key not in spec.NULLABLE or not values:
        return values
    n = len(values)
    flags = null_plan(rng, n)
    out = list(values)
    for i in range(n):
        if flags[i]:
            out[i] = None
    return out


def _apply_date_order(table, cm, values, rng, pair_values):
    """date_order: earlier date first, later date in [earlier, earlier+400]."""
    key = (table, cm.name)
    for (t, a, b) in spec.DATE_PAIRS:
        if t != table:
            continue
        if cm.name == a:
            hi = spec.DATE_HI - dt.timedelta(days=spec.DATE_SPAN_DAYS)
            return [rand_date(rng, spec.DATE_LO, hi) for _ in range(len(values))]
        if cm.name == b:
            earlier = pair_values.get(a) or []
            out = []
            for i in range(len(values)):
                e = earlier[i] if i < len(earlier) and earlier[i] is not None else rand_date(rng)
                out.append(rand_date_after(rng, e))
            return out
    return values


def _build_table_rows(table, tm, n, rng, literal_pool, original_values, parent_rows):
    """Build n rows for one table as a dict of column -> list of values."""
    cols = {}
    fk_cols = {cc for (ct, cc, _pt, _pc) in spec.FKS if ct == table}
    copied_cols = set()
    for (ct, cc), copies in spec.COPIED.items():
        if ct == table:
            for (child_col, _parent_col) in copies:
                copied_cols.add(child_col)
    for cm in tm.columns:
        key = (table, cm.name)
        if key in spec.COPIED:
            continue
        if cm.name in fk_cols:
            continue
        if cm.name in copied_cols:
            continue
        if cm.pk_pos > 0:
            cols[cm.name] = list(range(1, n + 1))
            continue
        vals = _sample_base_values(table, cm, n, rng, literal_pool, original_values)
        cols[cm.name] = vals
    for (t, a, b) in spec.DATE_PAIRS:
        if t != table:
            continue
        if a in cols and a not in copied_cols:
            cols[a] = _apply_date_order(table, _col(tm, a), cols[a], rng, {})
        if b in cols and b not in copied_cols:
            cols[b] = _apply_date_order(table, _col(tm, b), cols[b], rng, cols)
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if (table, cm.name) in spec.PK_COLUMNS:
            continue
        if cm.name in copied_cols:
            continue
        cols[cm.name] = _apply_group_size_plan(table, cm, cols[cm.name], rng)
        cols[cm.name] = _apply_duplicate_plan(table, cm, cols[cm.name], rng)
        cols[cm.name] = _apply_tie_plan(table, cm, cols[cm.name], rng)
        cols[cm.name] = _apply_null_plan(table, cm, cols[cm.name], rng)
    for (ct, cc, pt, pc) in spec.FKS:
        if ct != table:
            continue
        pv = parent_rows.get(pt, {}).get(pc) or []
        if pv:
            cols[cc] = [rng.choice(pv) for _ in range(n)]
        else:
            cols[cc] = [None] * n
    for (ct, cc), copies in spec.COPIED.items():
        if ct != table:
            continue
        parent = parent_rows.get('Claims', {})
        parent_pk = parent.get('Claim_ID') or []
        key_to_idx = {}
        for idx, k in enumerate(parent_pk):
            if k not in key_to_idx:
                key_to_idx[k] = idx
        child_fk = cols.get(cc) or []
        for (child_col, parent_col) in copies:
            src = parent.get(parent_col) or []
            out = []
            for i in range(n):
                k = child_fk[i] if i < len(child_fk) else None
                if k is None or k not in key_to_idx:
                    out.append(None)
                else:
                    j = key_to_idx[k]
                    out.append(src[j] if j < len(src) else None)
            cols[child_col] = out
    return cols


def _col(tm, name):
    for cm in tm.columns:
        if cm.name == name:
            return cm
    return None


def _ensure_unmatched_parents(instance, rng):
    """Ensure at least one parent row without children (unmatched_join_rows)."""
    for (pt, ct) in spec.PARENT_WITHOUT_CHILDREN:
        if pt not in instance or ct not in instance:
            continue
        fk_col = None
        parent_pk = None
        for (c_t, c_c, p_t, p_c) in spec.FKS:
            if c_t == ct and p_t == pt:
                fk_col = c_c
                parent_pk = p_c
                break
        if fk_col is None or parent_pk is None:
            continue
        child_vals = set(v for v in instance[ct].get(fk_col, []) if v is not None)
        parent_vals = instance[pt].get(parent_pk, [])
        unmatched = [v for v in parent_vals if v not in child_vals]
        if not unmatched and parent_vals:
            if len(parent_vals) >= 2:
                keep = parent_vals[0]
                for i, v in enumerate(instance[ct].get(fk_col, [])):
                    if v == keep:
                        instance[ct][fk_col][i] = parent_vals[1]
                        break


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with spec-driven construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = dict(spec.TABLE_SIZES)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        parent_rows = {pt: inst.get(pt, {}) for (ct, cc, pt, pc) in spec.FKS if ct == t}
        cols = _build_table_rows(t, tm, n, rng, literal_pool, schema.original_values, parent_rows)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    _ensure_unmatched_parents(inst, rng)
    return {t: inst[t] for t in schema.tables}
