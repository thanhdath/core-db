"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
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


def _compact_max(schema, table: str, col: str):
    """Maximum non-NULL value of a compact column (None if empty)."""
    vals = [v for v in schema.original_values.get((table, col), []) if v is not None]
    return max(vals) if vals else None


def _fresh_pk_values(schema, table: str, cm, n: int, rng) -> list:
    """Fresh sequential keys starting past the compact maximum (never collide)."""
    base = _compact_max(schema, table, cm.name)
    start = (int(base) + 1) if isinstance(base, (int, float)) else 1
    return [start + i for i in range(n)]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's GENERATED values with replacement."""
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


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _boundary_elements(key, rng) -> list:
    """Boundary literals plus one step on each side (step 0.1 REAL, 1 INT)."""
    lits = spec.BOUNDARY.get(key)
    if not lits:
        return []
    out = []
    for v in lits:
        step = 0.1 if isinstance(v, float) else 1
        out += [v - step, v, v + step]
    return out


def _tie_elements(key, rng) -> list:
    """Values that make at least two rows share the value at the listed ranks."""
    t = spec.TIES.get(key)
    if not t:
        return []
    return [rng.choice([1, 2, 3, 10, 100, 500, 1000, 1500, 5000]) for _ in t['ranks']]


def _duplicate_elements(key, rng) -> list:
    """Repeated values so the duplicate share falls in 20-50 %."""
    d = spec.DUPLICATES.get(key)
    if not d:
        return []
    return [rng.choice(['A', 'B', 'C', 'D']) for _ in range(3)]


def _enum_elements(key) -> list:
    return list(spec.ENUMS.get(key, []))


def _fresh_text(rng, base: str) -> str:
    """Fresh near-variant of a text value (prefix / suffix / dropped character)."""
    u = rng.random()
    if u < 0.25:
        return base + rng.choice(['x', 'y', 'z', '1', '2'])
    if u < 0.5:
        return rng.choice(['x', 'y', 'z', '1', '2']) + base
    if u < 0.75 and len(base) > 1:
        i = rng.randrange(len(base))
        return base[:i] + base[i + 1:]
    return base


def _null_plan(n: int, rng) -> list:
    """NULL rule: at least one NULL, share in [NULL_SHARE_MIN, NULL_SHARE_MAX]."""
    if n <= 0:
        return []
    share = rng.uniform(spec.NULL_SHARE_MIN, spec.NULL_SHARE_MAX)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = set(rng.sample(range(n), k))
    return [i in idx for i in range(n)]


def _rule_ok(table: str, row: dict) -> bool:
    """All semantic rules of the table hold (SQL three-valued logic: not FALSE)."""
    for (t, col), fn in spec.RULES.items():
        if t != table:
            continue
        try:
            if not fn(row):
                return False
        except Exception:
            return False
    return True


def _apply_derived(table: str, row: dict, rng) -> None:
    """Derived / dependent columns computed in Python from the sampled values."""
    if table == 'farm':
        th = row.get('Total_Horses')
        wh = row.get('Working_Horses')
        if _is_num(th) and _is_num(wh) and wh > th:
            row['Working_Horses'] = round(rng.uniform(0, th), 1)
        tc = row.get('Total_Cattle')
        parts = [row.get('Oxen'), row.get('Bulls'), row.get('Cows')]
        if _is_num(tc) and all(_is_num(p) for p in parts):
            need = sum(parts)
            if tc < need:
                row['Total_Cattle'] = round(need + rng.uniform(0, 100), 1)
    if table == 'city':
        p = row.get('Population')
        if _is_num(p) and p <= 0:
            row['Population'] = float(rng.randint(1, 10000))
        a = row.get('Area_km_2')
        if _is_num(a) and a <= 0:
            row['Area_km_2'] = round(rng.uniform(0.1, 100.0), 2)


def _build_column_elements(schema, table: str, cm, literal_pool: dict, rng) -> list:
    """Element list for one column: observed + pool literals + spec injections."""
    key = (table, cm.name)
    ov = list(schema.original_values.get(key, []))
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else [])
    els += sorted({str(v) for v in literal_pool.get(key, [])})
    els += _enum_elements(key)
    els += _boundary_elements(key, rng)
    els += _tie_elements(key, rng)
    els += _duplicate_elements(key, rng)
    if cm.type_str and any(k in cm.type_str.lower() for k in ('char', 'text')):
        base = [str(e) for e in els if e is not None]
        if base:
            n_fresh = max(1, int(spec.FRESH_SHARE * max(1, len(base))))
            for _ in range(n_fresh):
                els.append(_fresh_text(rng, rng.choice(base)))
    return els


def _sample_table(schema, table: str, n: int, literal_pool: dict, rng, p: float) -> dict:
    """Sample n rows for one table (non-FK columns), then apply derived columns."""
    tm = schema.tables[table]
    cols: dict = {}
    for cm in tm.columns:
        if (table, cm.name) in schema.fks:
            continue
        if (table, cm.name) in spec.YEAR_COLUMNS:
            lo, hi = spec.YEAR_DOMAIN
            cols[cm.name] = [rng.randint(lo, hi) for _ in range(n)]
            continue
        els = _build_column_elements(schema, table, cm, literal_pool, rng)
        max_l0 = float('inf')
        if cm.pk_pos > 0:
            max_l0 = float('inf') if len(tm.primary_key) == 1 else 30
        s = _init_sampler(cm, els, schema.original_values.get((table, cm.name), []), p, rng,
                          len(tm.primary_key), max_l0)
        cols[cm.name] = [s.sample() for _ in range(n)]
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        _apply_derived(table, row, rng)
        for c in cols:
            cols[c][i] = row[c]
    return cols


def _apply_null_rule(table: str, cols: dict, schema, rng) -> None:
    """NULL rule: every nullable column gets at least one NULL and a small share."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        plan = _null_plan(n, rng)
        if (table, cm.name) in schema.fks:
            max_null = max(1, int((1.0 - spec.FK_NONNULL_MIN) * n))
            null_idx = [i for i, is_null in enumerate(plan) if is_null]
            if len(null_idx) > max_null:
                keep = set(rng.sample(null_idx, max_null))
                plan = [is_null and i in keep for i, is_null in enumerate(plan)]
        for i, is_null in enumerate(plan):
            if is_null:
                cols[cm.name][i] = None


def _apply_unmatched(table: str, cols: dict, schema, rng) -> None:
    """Unmatched-join targets: child rows with NULL FK where allowed."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in cols:
            continue
        tgt = spec.UNMATCHED.get(key)
        if not tgt or not tgt.get('child_rows_with_null_fk'):
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        vals = cols[cm.name]
        if any(v is None for v in vals):
            continue
        i = rng.randrange(n)
        vals[i] = None


def _apply_group_sizes(table: str, cols: dict, schema, rng) -> None:
    """Group-size targets: groups of size 1, 2 and >= 3 for the listed columns."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 6:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.GROUP_SIZES or cm.name not in cols:
            continue
        if cm.pk_pos > 0:
            continue
        vals = cols[cm.name]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 6:
            continue
        base = [vals[i] for i in nonnull]
        v1 = rng.choice(base)
        v2 = rng.choice(base)
        v3 = rng.choice(base)
        idx = list(nonnull)
        rng.shuffle(idx)
        vals[idx[0]] = v1
        vals[idx[1]] = v2
        vals[idx[2]] = v2
        for j in idx[3:6]:
            vals[j] = v3


def _apply_duplicates(table: str, cols: dict, schema, rng) -> None:
    """DISTINCT targets: duplicate share in 20-50 % (NULL cells skipped)."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 3:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.DUPLICATES or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        share = rng.uniform(*spec.DUPLICATES[key])
        k = max(1, int(round(share * len(nonnull))))
        k = min(k, len(nonnull) - 1)
        src = rng.choice(nonnull)
        for j in rng.sample(nonnull, k):
            if j != src:
                vals[j] = vals[src]


def _apply_ties(table: str, cols: dict, schema, rng) -> None:
    """ORDER targets: at least two rows share the value at the listed ranks."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.TIES or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        direction = str(spec.TIES[key].get('direction', 'ASC')).upper()
        desc = 'DESC' in direction
        try:
            ordered = sorted(nonnull, key=lambda i: (vals[i], i), reverse=desc)
        except TypeError:
            ordered = sorted(nonnull, key=lambda i: (str(vals[i]), i), reverse=desc)
        for rank in spec.TIES[key].get('ranks', [1]):
            pos = min(max(int(rank) - 1, 0), len(ordered) - 1)
            src = ordered[pos]
            other = ordered[pos + 1] if pos + 1 < len(ordered) else ordered[pos - 1]
            vals[other] = vals[src]


def _apply_aggregate_boundary(table: str, cols: dict, schema, rng) -> None:
    """Aggregate boundary: groups of size 0, 1 and 2 for the listed columns."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 3:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.AGGREGATE_BOUNDARY or cm.name not in cols:
            continue
        if cm.pk_pos > 0:
            continue
        vals = cols[cm.name]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 3:
            continue
        if key in schema.fks:
            pt, pc = schema.fks[key]
            pv = [v for v in (schema.original_values.get((pt, pc), []) or []) if v is not None]
            pv += [v for v in vals if v is not None]
            pv = sorted(set(pv))
            if len(pv) < 3:
                continue
            g1, g2, g3 = rng.sample(pv, 3)
        else:
            is_int = 'int' in (cm.type_str or '').lower()
            if is_int:
                g1, g2, g3 = (rng.randint(10 ** 6, 10 ** 7) for _ in range(3))
            else:
                g1, g2, g3 = ('g1', 'g2', 'g3')
        a, b, c = rng.sample(nonnull, 3)
        vals[a] = g1
        vals[b] = g2
        vals[c] = g2
        for j in nonnull:
            if j not in (a, b, c):
                vals[j] = g3


def _apply_rows_different(table: str, cols: dict, schema, rng) -> None:
    """Rows with different values: >= 2 qualifying rows per group with different values."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 2:
        return
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in spec.ROWS_DIFFERENT or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) < 2:
            continue
        a, b = rng.sample(nonnull, 2)
        if vals[a] == vals[b]:
            if _is_num(vals[b]):
                vals[b] = vals[b] + 1
            else:
                vals[b] = str(vals[b]) + 'x'


def _apply_spec(table: str, cols: dict, schema, rng) -> None:
    """Apply all specification patterns for one table (by construction)."""
    _apply_null_rule(table, cols, schema, rng)
    _apply_group_sizes(table, cols, schema, rng)
    _apply_duplicates(table, cols, schema, rng)
    _apply_ties(table, cols, schema, rng)
    _apply_aggregate_boundary(table, cols, schema, rng)
    _apply_rows_different(table, cols, schema, rng)
    _apply_unmatched(table, cols, schema, rng)


def _filter_by_rules(table: str, cols: dict) -> dict:
    """Drop rows that fail a semantic rule (counted by the writer as skipped)."""
    if not cols:
        return cols
    n = len(next(iter(cols.values())))
    keep = []
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        if _rule_ok(table, row):
            keep.append(i)
    return _filter(cols, keep)


def _repair_foreign_keys(inst: dict, schema, rng) -> None:
    """Final pass: every non-NULL generated FK value must exist in the final parent list."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        pv = inst.get(pt, {}).get(pc) or []
        pset = set(pv)
        vals = inst[ct][cc]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in pset:
                vals[i] = rng.choice(pv) if pv else None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = dict(spec.TABLE_SIZES)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = _sample_table(schema, t, n, literal_pool, rng, p)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk_cols)
        _apply_spec(t, cols, schema, rng)
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols and len(tm.primary_key) == 1:
                cols[cm.name] = _fresh_pk_values(schema, t, cm, n, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _filter_by_rules(t, cols)
        inst[t] = cols
    _repair_foreign_keys(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
