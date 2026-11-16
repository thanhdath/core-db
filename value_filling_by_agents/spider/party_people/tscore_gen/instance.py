"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact database."""
import random

from .spec import (enum_for, formulas_for, null_share_for, range_for)
from .values import _init_sampler, make_column_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _is_nullable(cm) -> bool:
    return (not cm.notnull) and cm.pk_pos == 0


def _plant_nulls(columns: dict, table_meta, spec, rng) -> dict:
    """NULL rule: at least one NULL per nullable column; share follows the compact share (>= 8%)."""
    n = _n_rows(columns)
    if n == 0:
        return columns
    for cm in table_meta.columns:
        if cm.name not in columns or not _is_nullable(cm):
            continue
        share = null_share_for(spec, table_meta.name, cm.name, 0.0)
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            columns[cm.name][i] = None
    return columns


def _apply_formulas(columns: dict, table_meta, spec, rng) -> dict:
    """Enforce semantic formulas in Python on non-NULL operands (SQL three-valued logic)."""
    n = _n_rows(columns)
    for cm in table_meta.columns:
        if cm.name not in columns:
            continue
        for f in formulas_for(spec, table_meta.name, cm.name):
            kind = f.get('kind')
            if kind == 'gt0':
                for i in range(n):
                    v = columns[cm.name][i]
                    if v is None:
                        continue
                    try:
                        if int(v) <= 0:
                            columns[cm.name][i] = rng.randint(1, 10)
                    except (TypeError, ValueError):
                        columns[cm.name][i] = rng.randint(1, 10)
            elif kind == 'int_range':
                lo, hi = int(f['lo']), int(f['hi'])
                for i in range(n):
                    v = columns[cm.name][i]
                    if v is None:
                        continue
                    try:
                        iv = int(v)
                    except (TypeError, ValueError):
                        iv = rng.randint(lo, hi)
                    if iv < lo or iv > hi:
                        iv = rng.randint(lo, hi)
                    columns[cm.name][i] = iv
            elif kind == 'gt_column':
                other = f.get('other')
                if other not in columns:
                    continue
                for i in range(n):
                    a, b = columns[cm.name][i], columns[other][i]
                    if a is None or b is None:
                        continue
                    try:
                        ai, bi = int(a), int(b)
                    except (TypeError, ValueError):
                        continue
                    if ai <= bi:
                        columns[cm.name][i] = bi + rng.randint(1, 3)
            elif kind == 'enum':
                vals = f.get('values') or enum_for(spec, table_meta.name, cm.name) or []
                if not vals:
                    continue
                for i in range(n):
                    v = columns[cm.name][i]
                    if v is None:
                        continue
                    if v not in vals:
                        columns[cm.name][i] = rng.choice(vals)
    return columns


def _plant_duplicates(columns: dict, table_meta, spec, rng) -> dict:
    """duplicates_for_distinct: 20-50% duplicate share on the listed text columns."""
    n = _n_rows(columns)
    if n < 3:
        return columns
    for cm in table_meta.columns:
        key = '%s.%s' % (table_meta.name, cm.name)
        if key not in spec.get('duplicate_share', {}) or cm.name not in columns:
            continue
        lo, hi = spec['duplicate_share'][key]
        share = rng.uniform(lo, hi)
        k = max(1, int(round(share * n)))
        k = min(k, n - 1)
        if k <= 0:
            continue
        src = list(range(n - k))
        dst = rng.sample(range(n), k)
        for i in dst:
            j = rng.choice(src)
            columns[cm.name][i] = columns[cm.name][j]
    return columns


def _plant_group_sizes(columns: dict, table_meta, spec, rng) -> dict:
    """group_sizes: ensure groups of size 1, 2 and >= 3 on the listed columns (best effort)."""
    n = _n_rows(columns)
    if n < 6:
        return columns
    for cm in table_meta.columns:
        key = '%s.%s' % (table_meta.name, cm.name)
        if key not in spec.get('group_sizes', {}) or cm.name not in columns:
            continue
        vals = [v for v in columns[cm.name] if v is not None]
        if not vals:
            continue
        uniq = list(dict.fromkeys(vals))
        if len(uniq) < 3:
            continue
        picks = rng.sample(uniq, 3)
        counts = [1, 2, 3]
        rng.shuffle(counts)
        target = []
        for v, c in zip(picks, counts):
            target += [v] * c
        rng.shuffle(target)
        for i in range(min(len(target), n)):
            columns[cm.name][i] = target[i]
    return columns


def _plant_ties(columns: dict, table_meta, spec, rng) -> dict:
    """ties_for_order_limit: plant a tie at rank 1 on the listed columns (best effort)."""
    n = _n_rows(columns)
    if n < 2:
        return columns
    for cm in table_meta.columns:
        key = '%s.%s' % (table_meta.name, cm.name)
        if key not in spec.get('ties', {}) or cm.name not in columns:
            continue
        vals = [v for v in columns[cm.name] if v is not None]
        if not vals:
            continue
        v = rng.choice(vals)
        columns[cm.name][0] = v
        columns[cm.name][1] = v
    return columns


def _plant_comparison_boundary(columns: dict, table_meta, spec, rng) -> dict:
    """comparison_boundary: plant the listed literal and a case/whitespace near-variant."""
    n = _n_rows(columns)
    if n == 0:
        return columns
    for cm in table_meta.columns:
        key = '%s.%s' % (table_meta.name, cm.name)
        if key not in spec.get('comparison_boundary', {}) or cm.name not in columns:
            continue
        vals = spec['comparison_boundary'][key]
        if not vals:
            continue
        columns[cm.name][0] = vals[0]
        if n > 1 and len(vals) > 1:
            columns[cm.name][1] = vals[1]
        nv = spec.get('near_variants', {}).get(key) or []
        for j, v in enumerate(nv):
            if 2 + j < n:
                columns[cm.name][2 + j] = v
    return columns


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (also against compact rows)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing.get(cm.name, ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact: dict) -> dict:
    """FK child columns draw from the parent's rows (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or []) + list(compact.get((pt, pc), ()))
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec) -> dict:
    """Specification sizes per instance, with small per-instance jitter (0-230 rows)."""
    base = spec.get('table_sizes_per_instance') or {}
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            b = int(base.get(t, 0))
            if b <= 0:
                sizes[t] = 0
                continue
            jitter = rng.randint(-1, 1)
            sizes[t] = max(0, min(230, b + jitter))
    return sizes


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact = schema.original_values
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = '%s.%s' % (t, cm.name)
            pool = list(literal_pool.get((t, cm.name), []))
            enum = enum_for(spec, t, cm.name)
            if enum:
                pool = list(enum) + pool
            rng_ = range_for(spec, t, cm.name)
            if rng_:
                pool = pool + [str(rng_[0]), str(rng_[1])]
            samplers[(t, cm.name)] = _init_sampler(cm, pool, compact.get((t, cm.name), []), p, rng,
                                                   len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact))
        cols = _plant_comparison_boundary(cols, tm, spec, rng)
        cols = _plant_group_sizes(cols, tm, spec, rng)
        cols = _plant_duplicates(cols, tm, spec, rng)
        cols = _plant_ties(cols, tm, spec, rng)
        cols = _plant_nulls(cols, tm, spec, rng)
        cols = _apply_formulas(cols, tm, spec, rng)
        existing_pk = set()
        if tm.primary_key:
            for i in range(len(compact.get((t, tm.primary_key[0]), []))):
                existing_pk.add(tuple(compact.get((t, c), [None] * (i + 1))[i] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing_pk)
        existing_uniq = {cm.name: set(compact.get((t, cm.name), ())) for cm in tm.columns if cm.unique}
        cols = drop_unique_duplicates(tm, cols, existing_uniq)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
