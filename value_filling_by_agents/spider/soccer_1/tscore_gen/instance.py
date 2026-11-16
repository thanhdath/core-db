"""Random instance construction (fuzz/fuzz.py:83-196)."""
import random

from . import specification as spec
from .values import _init_sampler, NumberSampler, StringSampler


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
    """Drop rows repeating any single non-key unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns and not spec.is_unique_sequential(table_meta.name, cm.name):
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_values(instance: dict, schema, table: str, col: str, compact: dict) -> list:
    """Parent key values from generated rows plus compact rows (kept in memory)."""
    vals = list(instance.get(table, {}).get(col) or [])
    vals += [v for v in compact.get((table, col), []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, compact: dict) -> dict:
    """FK child columns draw from the parent's values (generated + compact) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc, compact)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _fresh_pk_start(table_meta, compact: dict, rng) -> int:
    """Start of fresh auto-increment keys above the compact maximum."""
    vals = [v for v in compact.get((table_meta.name, table_meta.primary_key[0]), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _apply_range(sampler, table: str, column: str):
    """Clamp a numeric sampler to the formula range."""
    rng_ = spec.range_formula(table, column)
    if rng_ and isinstance(sampler, NumberSampler):
        sampler.min = max(sampler.min, rng_[0])
        sampler.max = min(sampler.max, rng_[1])
        sampler.list_min = max(sampler.list_min, rng_[0])
        sampler.list_max = min(sampler.list_max, rng_[1])


def _apply_boundary_pool(sampler, table: str, column: str):
    """Pin comparison-boundary values verbatim (no random perturbation)."""
    bv = spec.boundary_values(table, column)
    if bv and isinstance(sampler, NumberSampler):
        sampler.pin_values = [float(v) for v in bv]


def _apply_enum_pool(sampler, table: str, column: str):
    """Restrict a text sampler to the enum domain (verbatim)."""
    ev = spec.enum_values(table, column)
    if ev and isinstance(sampler, StringSampler):
        sampler.pin_values = list(ev)


def _apply_free_text_pool(sampler, table: str, column: str):
    """Pin the observed free-text values verbatim (not an enum, but keep an exact known pool)."""
    fv = spec.free_text_values(table, column)
    if fv and isinstance(sampler, StringSampler):
        sampler.pin_values = list(fv)


def _apply_tie_pool(sampler, table: str, column: str, compact: dict):
    """Pin a small set of exact values so ties occur at the target rank."""
    if spec.is_tie_column(table, column):
        obs = [str(v) for v in compact.get((table, column), []) if v is not None]
        pool = sorted(set(obs))[:3] or sorted({str(e) for e in sampler.elements})[:3]
        if isinstance(sampler, StringSampler) and pool:
            sampler.pin_values = list(pool)


def _inject_nulls(values: list, share: float, rng) -> list:
    """Replace a share of values with NULL; guarantee at least one NULL when share > 0."""
    if share <= 0 or not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    idx = rng.sample(range(n), min(k, n))
    for i in idx:
        values[i] = None
    return values


def build_random_instance(schema, literal_pool: dict, size, rng, compact: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification domains applied."""
    compact = compact or schema.original_values
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                              compact.get((t, cm.name), []), p, rng, len(tm.primary_key))
            _apply_range(s, t, cm.name)
            _apply_boundary_pool(s, t, cm.name)
            _apply_enum_pool(s, t, cm.name)
            _apply_free_text_pool(s, t, cm.name)
            _apply_tie_pool(s, t, cm.name, compact)
            samplers[(t, cm.name)] = s
    if size is None:
        size = {t: spec.table_size(t) for t in schema.tables}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
            elif not spec.is_unique_sequential(t, cm.name):
                if (t, cm.name) not in schema.fks:
                    cols[cm.name] = [None] * n
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                start = _fresh_pk_start(tm, compact, rng)
                cols[pk] = list(range(start, start + n))
        for cm in tm.columns:
            if spec.is_unique_sequential(t, cm.name):
                vals = [v for v in compact.get((t, cm.name), []) if isinstance(v, int)]
                start = (max(vals) + 1) if vals else 1
                if cm.pk_pos > 0 and cm.name in cols:
                    continue
                cols[cm.name] = list(range(start, start + n))
        for cm in tm.columns:
            prefix = spec.unique_text_prefix(t, cm.name)
            if prefix is not None:
                vals = [v for v in compact.get((t, cm.name), []) if isinstance(v, str)]
                start = 1
                for v in vals:
                    if v.startswith(prefix):
                        try:
                            start = max(start, int(v[len(prefix):]) + 1)
                        except ValueError:
                            pass
                cols[cm.name] = [prefix + str(start + i) for i in range(n)]
        fk_cols = fill_foreign_keys_consistently({**inst, t: cols}, schema, t, n, rng, compact)
        for cm in tm.columns:
            if cm.name in fk_cols:
                cols[cm.name] = fk_cols[cm.name]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            share = spec.null_share(t, cm.name, compact.get((t, cm.name), []))
            if share > 0 and cm.name in cols:
                cols[cm.name] = _inject_nulls(list(cols[cm.name]), share, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
