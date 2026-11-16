"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact database."""
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value or composite UNIQUE tuple (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for cols in getattr(table_meta, 'unique_sets', ()) or ():
        if not all(c in columns for c in cols):
            continue
        seen, keep = set(), []
        for i in range(_n_rows(columns)):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact parent values + generated parent values (in memory), non-NULL only."""
    vals = [r[schema.tables[pt].columns.index(next(c for c in schema.tables[pt].columns if c.name == pc))]
            for r in schema.compact_rows.get(pt, [])]
    vals = [v for v in vals if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        if not pv:
            out[cm.name] = [None] * n
            continue
        if cm.notnull or cm.pk_pos > 0:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
            continue
        share = null_share
        if n >= 2:
            share = min(max(share, 1.0 / n), 1.0 - 1.0 / n)
        col = []
        for _ in range(n):
            col.append(None if rng.random() < share else rng.choice(pv))
        if n >= 2 and all(v is None for v in col):
            col[rng.randrange(n)] = rng.choice(pv)
        if n >= 2 and all(v is not None for v in col):
            col[rng.randrange(n)] = None
        out[cm.name] = col
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


def _compact_null_share(schema, t: str, c: str) -> float:
    vals = schema.original_values.get((t, c), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _key_offset(schema, t: str, c: str) -> int:
    """Generated integer keys start above the compact maximum (fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((t, c), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) to be appended to the compact database."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            share = _compact_null_share(schema, t, cm.name) if nullable else 0.0
            samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                   schema.original_values.get((t, cm.name), []), p, rng,
                                                   len(tm.primary_key), nullable=nullable, null_share=share)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if cm.pk_pos > 0 or cm.unique:
                if all(isinstance(v, int) for v in cols[cm.name] if v is not None) and cols[cm.name]:
                    off = _key_offset(schema, t, cm.name)
                    cols[cm.name] = [None if v is None else v + off for v in cols[cm.name]]
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                 null_share=_compact_null_share(schema, t, tm.columns[0].name))
        cols.update(fk_cols)
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
