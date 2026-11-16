"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from .spec import spec_for
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


def _compact_rows(schema, table: str) -> dict:
    """Compact rows of ``table`` as {column: [values]} (read-only, kept in memory)."""
    tm = schema.tables[table]
    return {c.name: list(schema.original_values.get((table, c.name), [])) for c in tm.columns}


def _compact_null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _next_pk(schema, table: str, column: str, n: int) -> list:
    """Fresh sequential PK values starting after the compact maximum."""
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, (int, float))]
    start = int(max(vals)) + 1 if vals else 1
    return list(range(start, start + n))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        nullable = not cm.notnull and cm.pk_pos == 0
        if nullable:
            share = _compact_null_share(schema, table, cm.name)
            if share <= 0.0:
                share = spec.get('null_share', 0.15)
            share = max(share, 1.0 / max(n, 1))
            k_null = max(1, int(round(share * n)))
            idx = list(range(n))
            rng.shuffle(idx)
            for j in idx[:k_null]:
                vals[j] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes with per-instance variation (0-230 rows, or level x4 capped at 2500)."""
    sizes = {}
    base = spec.get('table_sizes') or {}
    if base:
        for lvl in schema.table_order:
            for t in lvl:
                b = int(base.get(t, 0))
                if b <= 0:
                    sizes[t] = 0
                    continue
                lo = max(1, int(b * 0.75))
                hi = max(lo, int(b * 1.25))
                sizes[t] = rng.randint(lo, hi)
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


def _is_pk(table_meta, column: str) -> bool:
    return column in table_meta.primary_key


def _plant_nulls(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """NULL rule: every nullable column gets at least one NULL row (compact share)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0 or _is_pk(tm, cm.name):
            continue
        if cm.name not in cols:
            continue
        share = _compact_null_share(schema, table, cm.name)
        if share <= 0.0:
            share = spec.get('null_share', 0.15)
        share = max(share, 1.0 / max(n, 1))
        k = max(1, int(round(share * n)))
        idx = list(range(n))
        rng.shuffle(idx)
        for j in idx[:k]:
            cols[cm.name][j] = None


def _plant_group_sizes(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """Group sizes 1, 2, >=3 for the specified column (by construction)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if _is_pk(tm, cm.name):
            continue
        info = spec_for(spec, table, cm.name)
        gs = info.get('group_sizes')
        if not gs or cm.name not in cols or n < 6:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        distinct = []
        for v in pool:
            if v not in distinct:
                distinct.append(v)
        base = distinct[0] if distinct else ''
        while len(distinct) < 3:
            cand = (str(base) + '_%d' % len(distinct)) if isinstance(base, str) else (len(distinct) + 1)
            if cand not in distinct:
                distinct.append(cand)
        v1, v2, v3 = distinct[0], distinct[1], distinct[2]
        idx = list(range(n))
        rng.shuffle(idx)
        cols[cm.name][idx[0]] = v1
        cols[cm.name][idx[1]] = v2
        cols[cm.name][idx[2]] = v2
        for j in idx[3:]:
            cols[cm.name][j] = v3


def _plant_aggregate_boundary(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """At least one group with COUNT(*) > 2 and one with COUNT(*) <= 1 (by construction)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if _is_pk(tm, cm.name):
            continue
        info = spec_for(spec, table, cm.name)
        ab = info.get('aggregate_boundary')
        if not ab or cm.name not in cols or n < 4:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        distinct = []
        for v in pool:
            if v not in distinct:
                distinct.append(v)
        base = distinct[0] if distinct else ''
        while len(distinct) < 2:
            cand = (str(base) + '_%d' % len(distinct)) if isinstance(base, str) else (len(distinct) + 1)
            if cand not in distinct:
                distinct.append(cand)
        big, small = distinct[0], distinct[1]
        idx = list(range(n))
        rng.shuffle(idx)
        cols[cm.name][idx[0]] = small
        for j in idx[1:]:
            cols[cm.name][j] = big


def _plant_ties(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """At least two rows tie at rank 1 for the specified column (by construction)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if _is_pk(tm, cm.name):
            continue
        info = spec_for(spec, table, cm.name)
        if not info.get('tie') or cm.name not in cols or n < 2:
            continue
        pool = [v for v in cols[cm.name] if v is not None]
        if not pool:
            continue
        v = rng.choice(pool)
        idx = list(range(n))
        rng.shuffle(idx)
        cols[cm.name][idx[0]] = v
        cols[cm.name][idx[1]] = v


def _plant_different_values(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """At least two rows with different values for MAX/MIN/SUM/AVG aggregates."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if _is_pk(tm, cm.name):
            continue
        info = spec_for(spec, table, cm.name)
        if not info.get('different_values') or cm.name not in cols or n < 2:
            continue
        vals = [v for v in cols[cm.name] if isinstance(v, (int, float))]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        if lo == hi:
            idx = list(range(n))
            rng.shuffle(idx)
            cols[cm.name][idx[0]] = lo
            cols[cm.name][idx[1]] = hi + 1


def _plant_duplicates(schema, table: str, cols: dict, n: int, rng, spec: dict) -> None:
    """Enforce a 20-50 % duplicate share on DISTINCT text columns (by construction)."""
    tm = schema.tables[table]
    for cm in tm.columns:
        if _is_pk(tm, cm.name) or (table, cm.name) in schema.fks:
            continue
        info = spec_for(spec, table, cm.name)
        if not info.get('duplicate_target') or cm.name not in cols or n < 4:
            continue
        share = rng.uniform(0.2, 0.5)
        k = max(1, int(round(n * (1.0 - share))))
        if k >= n:
            continue
        head = cols[cm.name][:k]
        for j in range(k, n):
            cols[cm.name][j] = rng.choice(head)


def _plant_parent_without_child(schema, instance: dict, spec: dict, rng) -> None:
    """At least one parent row with no child (by construction: point a child at an unused parent)."""
    for child_t, child_c in list(schema.fks):
        pt, pc = schema.fks[(child_t, child_c)]
        if pt not in spec.get('parent_without_child', []):
            continue
        if child_t not in instance or child_c not in instance[child_t]:
            continue
        vals = instance[child_t][child_c]
        if not vals:
            continue
        parent_vals = instance.get(pt, {}).get(pc) or []
        if not parent_vals:
            continue
        used = {v for v in vals if v is not None}
        unused = [v for v in parent_vals if v not in used]
        if unused:
            vals[0] = unused[0]


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            info = spec_for(spec, t, cm.name)
            dup_cap = None
            if info.get('duplicate_target'):
                dup_cap = max(1, int(rng.uniform(0.5, 0.8) * 30))
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key),
                int_range=info.get('int_range'), real_range=info.get('real_range'),
                enum=info.get('enum'), boundaries=info.get('boundaries'), dup_cap=dup_cap)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.pk_pos > 0 and len(tm.primary_key) == 1:
                cols[cm.name] = _next_pk(schema, t, cm.name, n)
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        cols = inst.get(t, {})
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        _plant_group_sizes(schema, t, cols, n, rng, spec)
        _plant_aggregate_boundary(schema, t, cols, n, rng, spec)
        _plant_ties(schema, t, cols, n, rng, spec)
        _plant_different_values(schema, t, cols, n, rng, spec)
        _plant_duplicates(schema, t, cols, n, rng, spec)
        _plant_nulls(schema, t, cols, n, rng, spec)
    _plant_parent_without_child(schema, inst, spec, rng)
    return {t: inst[t] for t in schema.tables}
