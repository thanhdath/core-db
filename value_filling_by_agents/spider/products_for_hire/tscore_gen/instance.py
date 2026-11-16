"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction (spec.py)."""
import datetime as dt
import random

from . import spec
from .schema import q as _q
from .values import (ColumnSampler, DatetimeSampler, EnumSampler, NumberSampler, StringSampler,
                     _init_sampler, base_type, parse_dt)


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
    base = getattr(spec, 'TABLE_SIZES', {})
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                cap = base.get(t)
                if cap is None:
                    min_c = 30 * rng.random()
                    sizes[t] = int(min_c + int(rng.random() * 200))
                else:
                    hi = max(1, cap + rng.randint(-2, 2))
                    lo = max(0, cap - 3)
                    sizes[t] = rng.randint(lo, hi) if hi >= lo else 0
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                cap = base.get(t)
                if cap is None:
                    sizes[t] = int(min(s, 2500))
                else:
                    sizes[t] = max(0, min(int(s), cap + rng.randint(-1, 2)))
            s *= 4
    for t, c in spec.GROUP_SIZES:
        if t in sizes and sizes[t] < spec.GROUP_SIZES_MIN:
            sizes[t] = spec.GROUP_SIZES_MIN
    return sizes


def _enum_values(schema, table: str, column: str):
    for (t, c), vals in spec.ENUMS.items():
        if t.lower() == table.lower() and c.lower() == column.lower():
            return vals
    return None


def _has_pool_list(table: str, column: str):
    out = []
    for (t, c), vals in list(spec.BOUNDARY_STRINGS.items()) + list(spec.LIKE_BASES.items()):
        if t.lower() == table.lower() and c.lower() == column.lower():
            out.extend(vals)
    return out


def _boundary_numbers(table: str, column: str):
    for (t, c), vals in spec.BOUNDARY_NUMBERS.items():
        if t.lower() == table.lower() and c.lower() == column.lower():
            return vals
    return None


def _dedupe_prob(table: str, column: str) -> float:
    for (t, c), share in spec.DUPLICATE_SHARE.items():
        if t.lower() == table.lower() and c.lower() == column.lower():
            return share
    return 0.0


def _is_order_tie(table: str, column: str) -> bool:
    return any(t.lower() == table.lower() and c.lower() == column.lower() for t, c in spec.ORDER_TIES)


def _is_group_size(table: str, column: str) -> bool:
    return any(t.lower() == table.lower() and c.lower() == column.lower() for t, c in spec.GROUP_SIZES)


def _different_group_key(table: str, column: str):
    """Return the grouping key column for a rows_with_different_values target, else None."""
    for t, c, g in spec.DIFFERENT_VALUES:
        if t.lower() == table.lower() and c.lower() == column.lower():
            return g
    return None


def _parent_without_child(schema, table: str, column: str):
    """Return (child_table, child_col) if this parent column must have at least one childless row."""
    for pt, pcol, ct, ccol in getattr(spec, 'PARENT_WITHOUT_CHILD', []):
        if pt.lower() == table.lower() and pcol.lower() == column.lower():
            return ct, ccol
    return None


def _spec_sampler(schema, table, cm, rng, dt_lo, dt_hi):
    """Build a sampler for a non-FK column, applying spec domains (enums, boundary, LIKE, ranges)."""
    pool = schema.original_values.get((table, cm.name), [])
    t = base_type(cm.type_str)

    enums = _enum_values(schema, table, cm.name)
    if enums is not None:
        return EnumSampler(enums, rng, case_variants=('good_or_bad' in cm.name.lower()))

    bnums = _boundary_numbers(table, cm.name)
    if bnums is not None:
        els = list(bnums) + [float(v) for v in pool if _is_floatable(v)][:6]
        floor = spec.rule_value_floor(table, cm.name)
        if floor is not None:
            els = [max(floor, v) for v in els]
        return NumberSampler(els, 0.0, float('inf'), rng, scale=6, is_int=False, precision=4,
                             forced_lo=floor)

    strings = _has_pool_list(table, cm.name)
    if strings:
        els = list(strings) + [str(v) for v in pool if v is not None][:6]
        return StringSampler(els, 0.0, float('inf'), rng)

    if 'date' in t or 'timestamp' in t:
        return DatetimeSampler([], 0.0, float('inf'), rng, lo=dt_lo, hi=dt_hi)

    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        floor = spec.rule_value_floor(table, cm.name)
        return _init_sampler(cm, [], pool, 0.2, rng, len(schema.tables[table].primary_key),
                             max_l0=float('inf'))

    return _init_sampler(cm, [], pool, 0.2, rng, len(schema.tables[table].primary_key),
                         max_l0=float('inf'))


def _is_floatable(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _apply_dedup_share(values: list, share: float, rng) -> list:
    """Force >= share duplicate proportion by copying earlier values; keeps order/length."""
    if not values or share <= 0:
        return values
    n = len(values)
    target = int(round(share * n))
    if target <= 0 or n < 2:
        return values
    dupe_rows = rng.sample(range(n), min(target, n - 1))
    for r in dupe_rows:
        if r <= 0:
            continue
        src = rng.randrange(r)
        values[r] = values[src]
    return values


def _force_group_sizes(values: list, rng) -> list:
    """Ensure at least one singleton, one pair and (when n >= 6) one triple of values."""
    n = len(values)
    if n < 3:
        return values
    triple_rows = []
    if n >= 6:
        triple_rows = rng.sample(range(n), 3)
        base_val = values[triple_rows[0]]
        for r in triple_rows:
            values[r] = base_val
    rest = [r for r in range(n) if r not in triple_rows]
    pair_rows = rng.sample(rest, 2)
    pair_val = values[pair_rows[0]]
    for r in pair_rows:
        values[r] = pair_val
    outside = [r for r in range(n) if r not in triple_rows and r not in pair_rows]
    if outside:
        r = outside[0]
        v = values[r]
        if v == pair_val or (triple_rows and v == values[triple_rows[0]]):
            try:
                values[r] = v + 1 if isinstance(v, int) else (v + 'x' if isinstance(v, str) else v)
            except Exception:
                values[r] = pair_val + '_s' if isinstance(pair_val, str) else pair_val + 1
        if values[r] == pair_val or (triple_rows and values[r] == values[triple_rows[0]]):
            values[r] = (pair_val + '_s') if isinstance(pair_val, str) else (pair_val + 1)
    return values


def _force_order_ties(values: list, rng) -> list:
    """Tie rank-1 on order/limit-targeted columns: at least two rows share the max value."""
    if len(values) < 2:
        return values
    try:
        top = max(values, key=lambda v: (v is None, v))
    except TypeError:
        return values
    idxs = list(range(len(values)))
    rng.shuffle(idxs)
    a, b = idxs[0], idxs[1]
    values[a] = top
    values[b] = top
    return values


def _force_different_in_groups(values: list, group_key: list, rng, parent_pk=None) -> list:
    """Ensure each group (by group_key) has >= 2 rows with distinct values of `values`."""
    if not values or not group_key:
        return values
    groups: dict = {}
    for i, g in enumerate(group_key):
        groups.setdefault(g, []).append(i)
    for g, idxs in groups.items():
        if len(idxs) < 2:
            continue
        distinct = {values[i] for i in idxs}
        if len(distinct) >= 2:
            continue
        v0 = values[idxs[0]]
        if parent_pk:
            cands = [p for p in parent_pk if p != v0]
            if cands:
                values[idxs[1]] = rng.choice(cands)
            continue
        for attempt in range(8):
            try:
                if isinstance(v0, int):
                    cand = v0 + (attempt + 1)
                elif isinstance(v0, float):
                    cand = v0 + 0.5 * (attempt + 1)
                elif isinstance(v0, str):
                    cand = v0 + '_' + str(attempt + 1)
                else:
                    cand = v0
            except Exception:
                cand = v0
            if cand != v0:
                values[idxs[1]] = cand
                if len({values[i] for i in idxs}) >= 2:
                    break
    return values


def _compact_null_share(schema, table: str, column: str) -> float:
    """Per-column NULL share observed in the compact database (fallback ~0.1)."""
    vals = schema.original_values.get((table, column))
    if not vals:
        return spec.NULL_SHARE_FALLBACK
    n = len(vals)
    if n == 0:
        return spec.NULL_SHARE_FALLBACK
    nulls = sum(1 for v in vals if v is None)
    return nulls / n


def _ensure_null(schema, table, cm, values, rng, null_share):
    """NULL rule: each instance has at least one NULL + share of NULLs for every nullable column."""
    if cm.notnull or cm.pk_pos > 0 or not values:
        return values
    n = len(values)
    target = max(1, int(round(null_share * n)))
    existing = sum(1 for v in values if v is None)
    if existing >= target:
        return values
    need = target - existing
    non_null = [i for i, v in enumerate(values) if v is not None]
    if not non_null:
        return values
    idxs = rng.sample(non_null, min(need, len(non_null)))
    for i in idxs:
        values[i] = None
    return values


def _compact_pk_set(schema, table: str, pk_cols: list) -> set:
    """PK tuples already present in the compact database (must not be reused)."""
    out = set()
    if not pk_cols:
        return out
    cols = schema.original_values
    n = len(cols.get((table, pk_cols[0]), []))
    for i in range(n):
        row = []
        ok = True
        for c in pk_cols:
            v = cols.get((table, c), [None] * (i + 1))[i]
            if v is None:
                ok = False
            row.append(v)
        if ok:
            out.add(tuple(row))
    return out


def _finalize_parent(schema, table: str, columns: dict, rng) -> dict:
    """Apply PK dedup, unique-drop, NULL rule to a fully-sampled parent table."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if tm.primary_key:
        compact = _compact_pk_set(schema, table, tm.primary_key)
        seen = set(compact)
        keep = []
        for i in range(n):
            row = []
            ok = True
            for c in tm.primary_key:
                v = columns.get(c, [None] * n)[i]
                if v is None:
                    ok = False
                row.append(v)
            if not ok:
                keep.append(i)
                continue
            kt = tuple(row)
            if kt in seen:
                continue
            seen.add(kt)
            keep.append(i)
        columns = _filter(columns, keep)
    columns = drop_unique_duplicates(tm, columns)
    n_final = len(next(iter(columns.values()))) if columns else 0
    for cm in tm.columns:
        if cm.name not in columns:
            columns[cm.name] = [None] * n_final
        share = _compact_null_share(schema, table, cm.name)
        columns[cm.name] = _ensure_null(schema, table, cm, columns[cm.name], rng, share)
    return columns


def _final_pk_values(schema, table: str, columns: dict) -> list:
    """The surviving PK values of a finalized parent table (list, may contain duplicates only if the PK is composite;
    for single-column PKs it is unique)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return []
    n = len(columns.get(tm.primary_key[0], []))
    out = []
    for i in range(n):
        v = columns[tm.primary_key[0]][i]
        if v is not None:
            out.append(v)
    return out


def _assert_fk_membership(schema, inst: dict, final_pk: dict, rng) -> dict:
    """Post-generation FK-membership assertion."""
    failed: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        pv = final_pk.get(pt) or []
        pset = set(pv)
        vals = inst[ct].get(cc)
        if vals is None:
            continue
        n = len(vals)
        drop = set()
        for i in range(n):
            v = vals[i]
            if v is None:
                continue
            if v not in pset:
                if pv:
                    vals[i] = rng.choice(pv)
                else:
                    drop.add(i)
                failed[ct] = failed.get(ct, 0) + 1
        if drop:
            keep = [i for i in range(n) if i not in drop]
            inst[ct] = _filter(inst[ct], keep)
    return failed


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification."""
    p = 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    final_pk: dict = {}

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n == 0:
            inst[t] = {cm.name: [] for cm in tm.columns}
            final_pk[t] = []
            continue

        samplers = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            dt_lo = spec.RANGE_LO
            dt_hi = spec.RANGE_HI
            samplers[(t, cm.name)] = _spec_sampler(schema, t, cm, rng, dt_lo, dt_hi)
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in samplers:
                s = samplers[key]
                vals = [s.sample() for _ in range(n)]
                cols[cm.name] = vals
        for t2, hi_col, lo_col in spec.DATE_GE:
            if t2 != t:
                continue
            if hi_col not in cols or lo_col not in cols:
                continue
            hi_vals = cols[hi_col]
            lo_vals = cols[lo_col]
            for i in range(n):
                a = parse_dt(lo_vals[i])
                b = parse_dt(hi_vals[i])
                if a is None or b is None:
                    continue
                if b < a:
                    hi_vals[i] = a.strftime(spec.DT_FMT)
        for cm in tm.columns:
            floor = spec.rule_value_floor(t, cm.name)
            if floor is None or cm.name not in cols:
                continue
            vals = cols[cm.name]
            is_int = isinstance(floor, int) and float(floor) == int(floor)
            for i in range(n):
                v = vals[i]
                if v is None:
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv < floor:
                    vals[i] = int(floor) if is_int else round(float(floor), 4)

        for cm in tm.columns:
            if cm.name not in cols:
                continue
            share = _dedupe_prob(t, cm.name)
            if share > 0:
                cols[cm.name] = _apply_dedup_share(cols[cm.name], share, rng)
            if _is_group_size(t, cm.name):
                cols[cm.name] = _force_group_sizes(cols[cm.name], rng)
            if _is_order_tie(t, cm.name):
                cols[cm.name] = _force_order_ties(cols[cm.name], rng)

        fk_cols = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = final_pk.get(pt) or []
            if pv:
                fk_cols[cm.name] = [rng.choice(pv) for _ in range(n)]
            else:
                fk_cols[cm.name] = [None] * n

        for cm in tm.columns:
            gkey = _different_group_key(t, cm.name)
            if gkey is None or cm.name not in cols:
                continue
            gvals = fk_cols.get(gkey) or cols.get(gkey)
            if gvals is None:
                continue
            parent_pk = None
            if (t, cm.name) in schema.fks:
                pt, pc = schema.fks[(t, cm.name)]
                parent_pk = final_pk.get(pt) or []
            cols[cm.name] = _force_different_in_groups(cols[cm.name], gvals, rng, parent_pk)

        columns = {cm.name: cols.get(cm.name) for cm in tm.columns if cm.name in cols}
        columns.update(fk_cols)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = columns.get(pc, [])
                fs = set(final)
                columns[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                    for v in columns.get(cm.name, [])]

        columns = _finalize_parent(schema, t, columns, rng)
        inst[t] = columns
        final_pk[t] = _final_pk_values(schema, t, columns)

    for pt, pcol, ct, ccol in getattr(spec, 'PARENT_WITHOUT_CHILD', []):
        if pt not in inst or ct not in inst:
            continue
        pvals = inst[pt].get(pcol)
        cvals = inst[ct].get(ccol)
        if not pvals or not cvals:
            continue
        child_vals = set(v for v in cvals if v is not None)
        unreferenced = [i for i, v in enumerate(pvals) if v is not None and v not in child_vals]
        if unreferenced:
            idx = unreferenced[0]
            for col in inst[pt]:
                del inst[pt][col][idx]
            final_pk[pt] = _final_pk_values(schema, pt, inst[pt])

    fk_failed = _assert_fk_membership(schema, inst, final_pk, rng)
    if fk_failed:
        inst['__rows_failed__'] = fk_failed
    return {t: inst[t] for t in schema.tables}
