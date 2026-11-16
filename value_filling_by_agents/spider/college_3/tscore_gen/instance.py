"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from .values import (CIDSampler, CodeSampler, EnumSampler, NullWrapper, RangeSampler,
                     _init_sampler, make_column_sampler)


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


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Per-instance table sizes."""
    base = (spec or {}).get('table_sizes', {}) if spec else {}
    if base:
        return {t: max(0, int(base.get(t, 0))) for lvl in schema.table_order for t in lvl}
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = rng.randint(0, 230)
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = max(0, min(2500, int(s)))
            s *= 4
    return sizes


def _is_key_or_fk(schema, table, column) -> bool:
    """True for primary-key, unique-key and foreign-key columns (never reshaped)."""
    tm = schema.tables.get(table)
    if tm is None:
        return False
    if column in tm.primary_key:
        return True
    if (table, column) in schema.fks:
        return True
    for cm in tm.columns:
        if cm.name == column and cm.unique:
            return True
    return False


def _domain_sampler(spec, table, column, cm, rng, p, max_l0, original_values, literal_pool):
    """Build a domain-aware sampler for a column, or None to fall back to the generic one."""
    if not spec:
        return None
    key = '%s.%s' % (table, column)
    domains = spec.get('domains', {})
    ranges = spec.get('ranges', {})
    enums = spec.get('enums', {})
    codes = spec.get('codes', {})
    if key in enums:
        return EnumSampler(enums[key], p, max_l0, rng)
    if key in ranges:
        lo, hi = ranges[key]
        boundary = spec.get('boundary', {}).get(key, [])
        return RangeSampler(lo, hi, p, max_l0, rng, is_int=('int' in (cm.type_str or '').lower()),
                            boundary=boundary)
    if key in codes:
        return CodeSampler(int(codes[key]), p, max_l0, rng, literals=original_values)
    if key == 'Course.CID':
        return CIDSampler(spec.get('cid_prefixes', ['050', '520', '550', '600']), p, max_l0, rng,
                          literals=original_values)
    if key in domains:
        return EnumSampler(domains[key], p, max_l0, rng)
    return None


def _null_share(spec, table, column, original_values):
    """NULL share for a column: compact database share, or the spec default."""
    if not spec:
        return 0.0
    targets = set(spec.get('null_targets', []))
    key = '%s.%s' % (table, column)
    if key not in targets:
        return 0.0
    n = len(original_values)
    if n:
        nulls = sum(1 for v in original_values if v is None)
        share = nulls / n
        if share > 0:
            return share
    return float(spec.get('null_share', 0.10))


def _build_samplers(schema, spec, literal_pool, rng, p):
    """Per-column samplers (domain-aware where the spec says so, generic otherwise)."""
    samplers = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            lp = literal_pool.get((t, cm.name), [])
            dom = _domain_sampler(spec, t, cm.name, cm, rng, p, float('inf'), ov, lp)
            if dom is None:
                dom = _init_sampler(cm, lp, ov, p, rng, len(tm.primary_key))
            share = _null_share(spec, t, cm.name, ov)
            nullable = not cm.notnull and cm.pk_pos == 0
            samplers[(t, cm.name)] = NullWrapper(dom, nullable, share, rng, force_null_at=0)
    return samplers


def _parent_pool(instance, schema, table, column):
    """Parent values held in memory (compact + generated)."""
    return instance.get(table, {}).get(column) or []


def _fk_values(schema, spec, instance, table, column, n, rng, null_share):
    """FK column: draw from the parent's rows (compact or generated) or NULL by the NULL rule."""
    pt, pc = schema.fks[(table, column)]
    pv = _parent_pool(instance, schema, pt, pc)
    out = []
    for i in range(n):
        if i == 0:
            out.append(None)
            continue
        if pv and rng.random() >= null_share:
            out.append(rng.choice(pv))
        else:
            out.append(None)
    return out


def _apply_group_sizes(spec, table, column, values, rng):
    """Ensure group sizes of 1, 2 and >= 3 occur on GROUP columns (by construction)."""
    if not spec or '%s.%s' % (table, column) not in set(spec.get('group_size_columns', [])):
        return values
    if len(values) < 6:
        return values
    pool = list(dict.fromkeys([v for v in values if v is not None]))
    if len(pool) < 3:
        return values
    a, b, c = rng.sample(pool, 3)
    out = list(values)
    idx_a = [i for i, v in enumerate(out) if v == a]
    for i in idx_a[1:]:
        out[i] = b
    idx_b = [i for i, v in enumerate(out) if v == b]
    for i in idx_b[2:]:
        out[i] = c
    idx_c = [i for i, v in enumerate(out) if v == c]
    for i in idx_c[3:]:
        out[i] = a
    return out


def _apply_aggregate_boundary(spec, table, column, values, rng):
    """Ensure counts straddle the HAVING literals (one below, one at, one above)."""
    if not spec:
        return values
    ab = spec.get('aggregate_boundary', {})
    if '%s.%s' % (table, column) not in set(ab.get('columns', [])):
        return values
    vals = ab.get('values', [4, 5, 6])
    if len(values) < sum(vals):
        return values
    pool = list(dict.fromkeys([v for v in values if v is not None]))
    if len(pool) < 3:
        return values
    a, b, c = rng.sample(pool, 3)
    out = list(values)
    sizes = [max(1, vals[0] - 1), vals[1], vals[2] + 1]
    targets = [a, b, c]
    pos = 0
    for tgt, sz in zip(targets, sizes):
        for _ in range(sz):
            if pos < len(out):
                out[pos] = tgt
                pos += 1
    return out


def _apply_distinct_share(spec, table, column, values, rng):
    """Ensure the duplicate share on DISTINCT columns is 20-50% by repeating values from a small pool."""
    if not spec or '%s.%s' % (table, column) not in set(spec.get('distinct_columns', [])):
        return values
    if len(values) < 4:
        return values
    lo, hi = spec.get('duplicate_share', [0.20, 0.50])
    share = rng.uniform(lo, hi)
    n_dup = int(len(values) * share)
    pool = list(dict.fromkeys([v for v in values if v is not None]))
    if not pool:
        return values
    out = list(values)
    for i in rng.sample(range(len(out)), min(n_dup, len(out))):
        out[i] = rng.choice(pool)
    return out


def _apply_order_ties(spec, table, column, values, rng):
    """Ensure at least two rows tie at the listed LIMIT rank on ORDER columns."""
    if not spec or '%s.%s' % (table, column) not in set(spec.get('order_tie_columns', [])):
        return values
    if len(values) < 2:
        return values
    pool = list(dict.fromkeys([v for v in values if v is not None]))
    if not pool:
        return values
    v = rng.choice(pool)
    out = list(values)
    i, j = rng.sample(range(len(out)), 2)
    out[i] = v
    out[j] = v
    return out


def _apply_comparison_boundary(spec, table, column, values, rng):
    """Include boundary probes at listed literals (and one step on each side)."""
    if not spec:
        return values
    cb = spec.get('comparison_boundary', {})
    key = '%s.%s' % (table, column)
    if key not in cb:
        return values
    probes = list(cb[key])
    if not probes:
        return values
    out = list(values)
    for i in range(min(len(probes), len(out))):
        out[i] = probes[i]
    return out


def _postprocess(spec, schema, table, column, values, rng):
    """Apply specification patterns to a non-key, non-FK column's values (by construction)."""
    if _is_key_or_fk(schema, table, column):
        return values
    values = _apply_comparison_boundary(spec, table, column, values, rng)
    values = _apply_group_sizes(spec, table, column, values, rng)
    values = _apply_aggregate_boundary(spec, table, column, values, rng)
    values = _apply_distinct_share(spec, table, column, values, rng)
    values = _apply_order_ties(spec, table, column, values, rng)
    return values


def build_random_instance(schema, literal_pool: dict, spec: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = _build_samplers(schema, spec, literal_pool, rng, p)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t, tm in schema.tables.items():
        inst[t] = {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = samplers[(t, cm.name)]
            vals = [s.sample() for _ in range(n)]
            vals = _postprocess(spec, schema, t, cm.name, vals, rng)
            cols[cm.name] = vals
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            share = _null_share(spec, t, cm.name, schema.original_values.get((t, cm.name), []))
            cols[cm.name] = _fk_values(schema, spec, inst, t, cm.name, n, rng, share)
        cols = _dedup_against_compact(schema, t, cols)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            inst[t][cm.name] = list(inst[t].get(cm.name, [])) + list(cols.get(cm.name, []))
    return {t: inst[t] for t in schema.tables}


def _dedup_against_compact(schema, table, cols):
    """Drop generated rows whose PK/unique tuple collides with a compact row."""
    tm = schema.tables[table]
    if not cols:
        return cols
    n = len(next(iter(cols.values())))
    compact_pk = set()
    if tm.primary_key:
        ov = [schema.original_values.get((table, c), []) for c in tm.primary_key]
        if ov and all(ov):
            for i in range(len(ov[0])):
                compact_pk.add(tuple(ov[j][i] for j in range(len(ov))))
    compact_uniq = {}
    for cm in tm.columns:
        if cm.unique:
            compact_uniq[cm.name] = set(schema.original_values.get((table, cm.name), []))
    keep = []
    for i in range(n):
        if tm.primary_key:
            k = tuple(cols[c][i] for c in tm.primary_key)
            if k in compact_pk:
                continue
        ok = True
        for c, seen in compact_uniq.items():
            if c in cols and cols[c][i] in seen:
                ok = False
                break
        if ok:
            keep.append(i)
    return _filter(cols, keep)
