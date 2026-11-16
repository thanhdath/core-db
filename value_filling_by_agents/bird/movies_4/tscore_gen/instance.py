"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import (column_exceptions, enum_values, numeric_ranges, null_targets, pk_boundary_values,
                   table_sizes)
from .values import _init_sampler, make_spec_sampler


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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent values held in memory: compact rows plus generated rows."""
    vals = list(schema.original_values.get((pt, pc), []) or [])
    vals += list(instance.get(pt, {}).get(pc, []) or [])
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, null_share: float,
                                   null_cols: set) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        if not cm.notnull and (table.lower(), cm.name) in null_cols:
            k = max(1, int(round(n * null_share)))
            k = min(k, n)
            idx = rng.sample(range(n), k) if n > 0 else []
            for i in idx:
                vals[i] = None
        out[cm.name] = vals
    return out


def apply_null_rule(columns: dict, table_meta, schema, table: str, n: int, rng, null_share: float) -> dict:
    """NULL injection for nullable non-FK columns: at least one NULL row per column."""
    for cm in table_meta.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        if (table, cm.name) in schema.fks:
            continue
        if cm.name not in columns or n <= 0:
            continue
        orig = schema.original_values.get((table, cm.name), []) or []
        if orig:
            share = sum(1 for v in orig if v is None) / float(len(orig))
        else:
            share = null_share
        k = max(1, int(round(n * share)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            columns[cm.name][i] = None
    return columns


def choose_table_sizes(schema, rng, spec_sizes: dict) -> dict:
    """Specification sizes per instance, jittered per instance (0-230 rows per table)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = spec_sizes.get(t.lower())
            if base is None:
                base = rng.randint(0, 230)
            jitter = rng.randint(-max(1, base // 5), max(1, base // 5))
            sizes[t] = max(0, min(2500, base + jitter))
    return sizes


def _fresh_pk_values(table_meta, n: int, rng, existing: set, reserved: list = None) -> list:
    """Sequential integers starting at 1, unique against compact rows and generated rows."""
    pk = table_meta.primary_key
    if len(pk) != 1:
        return None
    col = next(c for c in table_meta.columns if c.name == pk[0])
    if 'int' not in (col.type_str or '').lower():
        return None
    start = 1
    if existing:
        try:
            start = max(int(v) for v in existing if v is not None) + 1
        except (TypeError, ValueError):
            start = 1
    reserved = sorted(set(int(v) for v in (reserved or []) if v is not None))
    out = []
    cur = start
    ri = 0
    while len(out) < n:
        if ri < len(reserved) and reserved[ri] < cur:
            ri += 1
            continue
        if ri < len(reserved) and reserved[ri] == cur:
            out.append(cur)
            ri += 1
            cur += 1
            continue
        out.append(cur)
        cur += 1
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    exc = column_exceptions(spec)
    enums = enum_values(spec)
    ranges = numeric_ranges(spec)
    nulls = null_targets(spec)
    pk_bounds = pk_boundary_values(spec, schema)
    spec_sizes = table_sizes(spec)
    null_share = rng.uniform(0.05, 0.30)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t.lower(), cm.name)
            base = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                 schema.original_values.get((t, cm.name), []), p, rng,
                                 len(tm.primary_key))
            samplers[(t, cm.name)] = make_spec_sampler(
                cm, base, rng, exc.get(key, []),
                enum=enums.get(key), num_range=ranges.get(key))

    if size is None:
        size = choose_table_sizes(schema, rng, spec_sizes)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        existing = set(v for v in schema.original_values.get((t, tm.primary_key[0]), []) if v is not None) \
            if len(tm.primary_key) == 1 else set()
        reserved = pk_bounds.get((t, tm.primary_key[0]), []) if len(tm.primary_key) == 1 else []
        pk_vals = _fresh_pk_values(tm, n, rng, existing, reserved)
        if pk_vals is not None:
            cols[tm.primary_key[0]] = pk_vals
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, null_share, nulls))
        cols = apply_null_rule(cols, tm, schema, t, n, rng, null_share)
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
    return {t: inst[t] for t in schema.tables}
