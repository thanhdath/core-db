"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 spec rules by construction."""
from . import spec
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


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes per instance (spec: table_sizes_per_instance)."""
    return {t: int(spec.TABLE_SIZES.get(t, 0)) for t in schema.tables}


def _is_key_column(schema, table: str, col: str) -> bool:
    """True for primary-key columns and NOT NULL foreign-key columns (never duplicate/tie)."""
    tm = schema.tables.get(table)
    if tm is not None and col in tm.primary_key:
        return True
    if (table, col) in schema.fks:
        cm = next((c for c in tm.columns if c.name == col), None) if tm is not None else None
        if cm is not None and cm.notnull:
            return True
    return False


def _plant_ties_and_dups(table: str, columns: dict, rng, schema=None) -> dict:
    """Plant duplicate values so the duplicate share falls in 20-50 % for DUP_COLUMNS."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n < 2:
        return columns
    for cm_name in list(columns.keys()):
        key = (table, cm_name)
        if key not in spec.DUP_COLUMNS and key not in spec.TIE_COLUMNS:
            continue
        if schema is not None and _is_key_column(schema, table, cm_name):
            continue
        vals = columns[cm_name]
        if not vals:
            continue
        k = max(2, int(round(n * 0.3)))
        idxs = rng.sample(range(n), min(k, n))
        src = rng.choice(vals)
        for i in idxs:
            vals[i] = src
        if key in spec.TIE_COLUMNS:
            top = max(set(vals), key=vals.count)
            if vals.count(top) < 2:
                for i in range(n):
                    if vals[i] != top:
                        vals[i] = top
                        break
    return columns


def _apply_null_rule(table: str, columns: dict, rng) -> dict:
    """NULL rule: at least one NULL row per nullable target; share follows the compact share."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for (t, c), share in spec.NULL_TARGETS.items():
        if t != table or c not in columns:
            continue
        k = max(1, int(round(n * share)))
        idxs = rng.sample(range(n), min(k, n))
        for i in idxs:
            columns[c][i] = None
    return columns


def _fix_full_name(table: str, columns: dict) -> dict:
    """Keep full_name consistent with last_name/first_name (spec: text_name)."""
    if 'full_name' not in columns:
        return columns
    last = columns.get('last_name')
    first = columns.get('first_name')
    if last is None:
        return columns
    out = []
    for i, ln in enumerate(last):
        fn = first[i] if first is not None else None
        out.append('%s, %s' % (ln, fn) if fn else '%s' % ln)
    columns['full_name'] = out
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with spec rules by construction."""
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
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _plant_ties_and_dups(t, cols, rng, schema)
        cols = _apply_null_rule(t, cols, rng)
        cols = _fix_full_name(t, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
