"""Random instance construction (fuzz/fuzz.py:83-196)."""
import random

from .spec import (boundary_values, duplicate_columns, enum_domains, null_shares,
                   null_targets, numeric_is_int, numeric_ranges, tie_columns)
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   reserved: dict = None) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if reserved and pt in reserved:
            pv = [v for v in pv if v not in reserved[pt]]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes (table_sizes_per_instance) used exactly (no per-instance variation)."""
    base = spec.get('table_sizes_per_instance', {})
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = int(base.get(t, 0))
    return sizes


def _next_pk_start(schema, table: str) -> int:
    """First integer above the compact rows' max PK (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 0
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 0


def _apply_null_rule(cols: dict, table: str, tm, spec: dict, rng, shares: dict) -> None:
    """NULL rule: only columns with a share (null_targets or compact share > 0) get NULLs."""
    for cm in tm.columns:
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if cm.name not in cols:
            continue
        share = shares.get((table, cm.name.upper()))
        if share is None:
            continue
        n = len(cols[cm.name])
        if n == 0:
            continue
        k = max(1, int(round(n * share)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None


def _plant_duplicates(cols: dict, table: str, tm, spec: dict, rng) -> None:
    """duplicates_for_distinct: 20-50% of values repeat an earlier value (PK columns skipped)."""
    dups = duplicate_columns(spec, None)
    for cm in tm.columns:
        if cm.pk_pos > 0:
            continue
        if (table, cm.name.upper()) not in dups or cm.name not in cols:
            continue
        vals = cols[cm.name]
        n = len(vals)
        if n < 2:
            continue
        share = rng.uniform(0.20, 0.50)
        k = int(n * share)
        for i in rng.sample(range(1, n), min(k, n - 1)):
            vals[i] = vals[rng.randrange(0, i)]


def _plant_ties(cols: dict, table: str, tm, spec: dict, rng) -> None:
    """ties_for_order_limit: plant ties at the listed rank (rank 1 for DESC); PK columns skipped."""
    ties = tie_columns(spec, None)
    for cm in tm.columns:
        if cm.pk_pos > 0:
            continue
        if (table, cm.name.upper()) not in ties or cm.name not in cols:
            continue
        vals = cols[cm.name]
        nonnull = [v for v in vals if v is not None]
        if len(nonnull) < 2:
            continue
        direction = ties[(table, cm.name.upper())]
        if direction.upper() == 'UNORDERED':
            top = max(nonnull)
            idx = [i for i, v in enumerate(vals) if v is not None]
            rng.shuffle(idx)
            for i in idx[:2]:
                vals[i] = top
            continue
        top = max(nonnull) if direction.upper() == 'DESC' else min(nonnull)
        idx = [i for i, v in enumerate(vals) if v is not None]
        rng.shuffle(idx)
        for i in idx[:2]:
            vals[i] = top


def _reserve_parent_keys(inst: dict, schema, rng) -> dict:
    """Reserve at least one parent key per parent table, excluded from the child FK pool."""
    reserved: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if pt == ct:
            continue
        pv = inst.get(pt, {}).get(pc) or []
        if not pv:
            continue
        reserved.setdefault(pt, set())
        if len(reserved[pt]) < 1:
            reserved[pt].add(rng.choice(pv))
    return reserved


def _plant_boundaries(cols: dict, table: str, tm, samplers: dict, rng) -> None:
    """Guarantee every listed boundary literal appears in the generated rows."""
    for cm in tm.columns:
        s = samplers.get((table, cm.name))
        if s is None or cm.name not in cols:
            continue
        vals = cols[cm.name]
        n = len(vals)
        if n == 0:
            continue
        planted = s.plant_boundaries(n)
        if not planted:
            continue
        slots = [i for i, v in enumerate(vals) if v is not None]
        if not slots:
            continue
        rng.shuffle(slots)
        for j, v in enumerate(planted):
            if j >= len(slots):
                break
            vals[slots[j]] = v


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    if spec is None:
        from .spec import default_specification
        spec = default_specification()
    spec = dict(spec)
    spec['_orig_values'] = schema.original_values
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    enums = enum_domains(spec)
    ranges = numeric_ranges(spec)
    is_int = numeric_is_int(spec)
    bounds = boundary_values(spec)
    shares = null_shares(spec, schema)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t, cm.name.upper())
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key),
                enum=enums.get(key), domain=ranges.get(key), boundaries=bounds.get(key),
                near=bounds.get(key) if cm.type_str and 'char' in cm.type_str.lower() else None)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        cols = drop_unique_duplicates(tm, cols)
        n = len(next(iter(cols.values()))) if cols else 0
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            start = _next_pk_start(schema, t)
            cols[pk] = list(range(start, start + n))
        inst[t] = cols
        reserved = _reserve_parent_keys(inst, schema, rng)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, reserved))
        for cm in tm.columns:
            fk = schema.fks.get((t, cm.name))
            if fk is None:
                continue
            pt, pc = fk
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _apply_null_rule(cols, t, tm, spec, rng, shares)
        _plant_duplicates(cols, t, tm, spec, rng)
        _plant_ties(cols, t, tm, spec, rng)
        _plant_boundaries(cols, t, tm, samplers, rng)
        cols = sample_fresh_primary_keys(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
