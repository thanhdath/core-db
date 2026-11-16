"""Random instance construction (fuzz/fuzz.py:83-196)."""
import re

from .values import _init_sampler

_INT_RANGES = {
    ('Student', 'Age'): (16, 26),
}
_ENUMS = {
    ('Student', 'Sex'): ['F', 'M'],
    ('Student', 'Major'): [50, 100, 520, 540, 550, 600],
}
_POSITIVE = {('Student', 'StuID'), ('Club', 'ClubID')}

_DEFAULT_NULL_SHARE = 0.08


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_tuples(schema, table: str, cols: list) -> set:
    """Tuples of compact values for the given columns (for PK / UNIQUE dedup)."""
    if not cols:
        return set()
    lists = [schema.original_values.get((table, c), []) for c in cols]
    n = min((len(x) for x in lists), default=0)
    return {tuple(l[i] for l in lists) for i in range(n)}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    taken = taken or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_parent: dict = None) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    compact_parent = compact_parent or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_parent.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        vals = []
        for _ in range(n):
            if not pv or rng.random() < _DEFAULT_NULL_SHARE:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        out[cm.name] = vals
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


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs: at least one row, overall share ~ share (NULL is a value to generate)."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _apply_semantic_rules(table: str, cm, values: list, rng) -> list:
    """Enforce the specification's ranges / enumerations / positivity by construction."""
    key = (table, cm.name)
    out = []
    if key in _ENUMS:
        pool = _ENUMS[key]
        for v in values:
            if v is None:
                out.append(None)
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                iv = None
            if iv in pool:
                out.append(iv)
            else:
                out.append(rng.choice(pool))
        return out
    if key in _INT_RANGES:
        lo, hi = _INT_RANGES[key]
        for v in values:
            if v is None:
                out.append(None)
                continue
            try:
                iv = int(round(float(v)))
            except (TypeError, ValueError):
                iv = rng.randint(lo, hi)
            out.append(min(hi, max(lo, iv)))
        return out
    if key in _POSITIVE:
        for v in values:
            if v is None:
                out.append(None)
                continue
            try:
                iv = int(round(float(v)))
            except (TypeError, ValueError):
                iv = 1
            out.append(iv if iv > 0 else 1)
        return out
    return values


def _fresh_pk_values(table: str, cm, n: int, rng, taken: set) -> list:
    """Sequential integers starting at 1, unique against compact + generated keys."""
    start = 1
    if taken:
        try:
            start = max(int(x) for x in taken if x is not None) + 1
        except (TypeError, ValueError):
            start = 1
    out = []
    v = start
    while len(out) < n:
        if v not in taken:
            out.append(v)
        v += 1
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) to be appended to the compact database."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, schema.original_values))
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_semantic_rules(t, cm, cols[cm.name], rng)
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            taken = _compact_tuples(schema, t, [pk])
            taken |= {tuple([v])[0] for v in cols.get(pk, []) if v is not None}
            cols[pk] = _fresh_pk_values(t, next(c for c in tm.columns if c.name == pk), n, rng, taken)
        for cm in tm.columns:
            if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
                continue
            share = _DEFAULT_NULL_SHARE
            ov = schema.original_values.get((t, cm.name), [])
            if ov:
                share = max(share, sum(1 for x in ov if x is None) / max(1, len(ov)))
            cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
        taken_pk = _compact_tuples(schema, t, tm.primary_key)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken_pk)
        taken_uq = {cm.name: _compact_tuples(schema, t, [cm.name]) for cm in tm.columns if cm.unique}
        cols = drop_unique_duplicates(tm, cols, taken_uq)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
