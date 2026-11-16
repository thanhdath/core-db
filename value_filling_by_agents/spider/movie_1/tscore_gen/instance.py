"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt
import re

from .spec import (exceptions_for, formula_for, has_pattern, is_null_target, parse_int_range,
                   pattern_targets)
from .values import _init_sampler, _near_variants


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, reserved: set = None) -> dict:
    """Drop rows whose PK tuple repeats or collides with a compact key (first occurrence kept)."""
    if not table_meta.primary_key or not columns:
        return columns
    reserved = reserved or set()
    n = len(next(iter(columns.values())))
    seen, keep = set(reserved), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, reserved: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    reserved = reserved or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(reserved.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_keys(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _compact_unique(schema, table: str) -> dict:
    out = {}
    for cm in schema.tables[table].columns:
        if cm.unique:
            out[cm.name] = set(v for v in schema.original_values.get((table, cm.name), []) if v is not None)
    return out


def _null_share(schema, table: str, column: str, spec: dict) -> float:
    """NULL share: compact share for the column, clamped to [0.05, 0.30] for declared NULL targets."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    share = sum(1 for v in vals if v is None) / float(len(vals))
    if is_null_target(spec, table, column):
        share = max(0.05, min(0.30, share if share > 0 else 0.10))
    return share


def _fk_null_share(schema, table: str, column: str, spec: dict) -> float:
    """NULL share for a nullable FK column."""
    share = _null_share(schema, table, column, spec)
    if has_pattern(spec, table, column, 'unmatched_join_rows'):
        share = max(0.10, share)
    return share


def _boundary_values(schema, table: str, column: str, spec: dict, cm) -> list:
    """Literal-boundary values for a column (comparison_boundary targets), clamped to the formula range."""
    tg = pattern_targets(spec, table, column, 'comparison_boundary')
    vals = list(tg.get('values') or [])
    out = []
    t = (cm.type_str or '').lower()
    is_int = 'int' in t or 'year' in t
    for v in vals:
        if v is None:
            continue
        if is_int:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                pass
        elif 'date' in t:
            out.append(str(v))
        else:
            out.append(str(v))
    if is_int:
        for v in list(out):
            if isinstance(v, int):
                out += [v - 1, v + 1]
    rng = _int_range(schema, table, column, spec)
    if is_int and rng:
        lo, hi = rng
        out = [v for v in out if (lo is None or v >= lo) and (hi is None or v <= hi)]
    seen, res = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            res.append(v)
    return res


def _like_literals(spec: dict, table: str, column: str) -> list:
    tg = pattern_targets(spec, table, column, 'like_near_variant')
    lits = list(tg.get('literals') or [])
    variants = list(tg.get('variants') or [])
    out = list(lits)
    for v in variants:
        out.append('%' + str(v) + '%')
    return out


def _int_range(schema, table: str, column: str, spec: dict):
    """Integer range from the semantic formula, else from the compact min/max."""
    f = formula_for(spec, table, column)
    r = parse_int_range(f)
    if r:
        return r
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    if vals:
        return min(vals), max(vals)
    return None


def _group_cap(spec: dict, table: str, column: str, n: int) -> float:
    """Cap on distinct fresh values to realise group_sizes / duplicates_for_distinct."""
    if has_pattern(spec, table, column, 'group_sizes') or has_pattern(spec, table, column, 'duplicates_for_distinct'):
        return max(2.0, n * 0.4)
    return float('inf')


def _fk_draw(parent_vals: list, n: int, rng, *, null_share: float, unmatched: bool) -> list:
    """Draw n FK values from parent_vals with a distribution realising group sizes 1, 2, >=3."""
    if not parent_vals:
        return [None] * n
    out = []
    pool = list(parent_vals)
    if unmatched and len(pool) > 1:
        rng.shuffle(pool)
        pool = pool[:-1]
    sizes = [1, 2, 3, 3, 2, 1, 3]
    i = 0
    while len(out) < n:
        pv = pool[i % len(pool)]
        k = sizes[i % len(sizes)]
        for _ in range(k):
            if len(out) >= n:
                break
            out.append(pv)
        i += 1
    rng.shuffle(out)
    if null_share > 0:
        for j in range(len(out)):
            if rng.random() < null_share:
                out[j] = None
    if unmatched and out and all(v is not None for v in out):
        out[rng.randrange(len(out))] = None
    return out


def choose_table_sizes(schema, rng, spec: dict = None) -> dict:
    """Sizes: spec table_sizes_per_instance when present, else the upstream rand_lin / level rule."""
    sizes = {}
    spec_sizes = (spec or {}).get('sizes') or {}
    if spec_sizes:
        for t in schema.tables:
            sizes[t] = int(spec_sizes.get(t, schema.original_sizes.get(t, 0)))
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


def _build_samplers(schema, literal_pool: dict, spec: dict, rng, p: float) -> dict:
    samplers = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            ns = _null_share(schema, t, cm.name, spec) if not cm.notnull and cm.pk_pos == 0 else 0.0
            bnd = _boundary_values(schema, t, cm.name, spec, cm)
            likes = _like_literals(spec, t, cm.name)
            irange = _int_range(schema, t, cm.name, spec)
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), null_share=ns, boundary=bnd, like_literals=likes,
                int_range=irange)
    return samplers


def _apply_group_cap(sampler, cap: float) -> None:
    if cap != float('inf'):
        sampler.max_l0 = min(sampler.max_l0, cap)


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) as compact rows + appended generated rows."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = _build_samplers(schema, literal_pool, spec, rng, p)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        compact = {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}
        n_compact = len(next(iter(compact.values()))) if compact else 0
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                _apply_group_cap(samplers[(t, cm.name)], _group_cap(spec, t, cm.name, n))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = list(inst.get(pt, {}).get(pc) or [])
            if not parent_vals:
                parent_vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
            ns = _fk_null_share(schema, t, cm.name, spec) if not cm.notnull and cm.pk_pos == 0 else 0.0
            unmatched = has_pattern(spec, t, cm.name, 'unmatched_join_rows')
            cols[cm.name] = _fk_draw(parent_vals, n, rng, null_share=ns, unmatched=unmatched)
        reserved_pk = _compact_keys(schema, t)
        reserved_uq = _compact_unique(schema, t)
        cols = sample_fresh_primary_keys(tm, cols, reserved_pk)
        cols = drop_unique_duplicates(tm, cols, reserved_uq)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        merged = {}
        for cm in tm.columns:
            gen = cols.get(cm.name, [])
            comp = compact.get(cm.name, [])
            merged[cm.name] = list(comp) + list(gen)
        inst[t] = merged
    return {t: inst[t] for t in schema.tables}
