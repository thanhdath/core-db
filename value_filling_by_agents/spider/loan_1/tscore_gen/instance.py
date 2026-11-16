"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set = None) -> dict:
    """Drop rows whose PK tuple repeats (first occurrence kept) or collides with a compact key."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen = set(existing_keys or ())
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing_unique: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    existing_unique = existing_unique or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing_unique.get(cm.name, ()))
            keep = []
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
        is_null_target = spec.null_target(table, cm.name)
        if not pv:
            out[cm.name] = [None] * n
            continue
        if is_null_target:
            ov = schema.original_values.get(key, [])
            share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.1
            share = max(share, 1.0 / max(n, 1))
            vals = []
            n_null = 0
            for _ in range(n):
                if rng.random() < share:
                    vals.append(None)
                    n_null += 1
                else:
                    vals.append(rng.choice(pv))
            if n_null == 0:
                vals[rng.randrange(n)] = None
            if n_null == n:
                vals[rng.randrange(n)] = rng.choice(pv)
            out[cm.name] = vals
        else:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (fallback: upstream rand_lin / level sizes)."""
    sizes = {}
    for t in schema.tables:
        if t in spec.TABLE_SIZES:
            sizes[t] = int(spec.TABLE_SIZES[t])
    if len(sizes) == len(schema.tables):
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                if t in sizes:
                    continue
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _apply_null_rule(table: str, columns: dict, schema, rng) -> dict:
    """For every nullable column (incl. nullable FKs) ensure NULL and non-NULL rows."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        if cm.name not in columns:
            continue
        ov = schema.original_values.get((table, cm.name), [])
        share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.05
        share = max(share, 1.0 / n)
        vals = list(columns[cm.name])
        n_null = sum(1 for v in vals if v is None)
        if n_null == 0:
            vals[rng.randrange(n)] = None
            n_null = 1
        if n_null == n:
            idx = rng.randrange(n)
            pool = [v for v in ov if v is not None]
            vals[idx] = rng.choice(pool) if pool else 0
        columns[cm.name] = vals
    return columns


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
                                                       len(tm.primary_key), table=t)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    compact_parent = {k: list(v) for k, v in schema.original_values.items()}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_parent))
        existing_pk = set()
        if tm.primary_key:
            pk_vals = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            if pk_vals and all(pk_vals):
                existing_pk = set(zip(*pk_vals))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing_pk)
        existing_unique = {}
        for cm in tm.columns:
            if cm.unique:
                existing_unique[cm.name] = set(schema.original_values.get((t, cm.name), []))
        cols = drop_unique_duplicates(tm, cols, existing_unique)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(t, cols, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
