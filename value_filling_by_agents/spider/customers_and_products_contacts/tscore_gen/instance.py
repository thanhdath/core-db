"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_keys: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_keys.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (spec.table_sizes_per_instance)."""
    return {t: int(spec.TABLE_SIZES.get(t, 0)) for t in schema.tables}


def _compact_keys(schema) -> dict:
    """Primary-key pools of the compact database, per (table, column)."""
    out = {}
    for t, tm in schema.tables.items():
        for c in tm.primary_key:
            out[(t, c)] = [v for v in schema.original_values.get((t, c), []) if v is not None]
    return out


def _next_pk_start(schema, table: str, col: str) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _apply_null_rule(table: str, cols: dict, schema, rng) -> None:
    """Each nullable column gets at least one NULL row; share follows the compact database."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        key = (table, cm.name)
        if key not in spec.NULL_TARGETS:
            continue
        ov = schema.original_values.get(key, [])
        null_share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.0
        k = max(1, int(round(null_share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None


def _apply_group_sizes(table: str, cols: dict, rng) -> None:
    """Group sizes 1, 2 and >= 3 for the listed columns (by construction)."""
    for col in list(cols):
        if (table, col) not in spec.GROUP_SIZE_COLUMNS:
            continue
        n = len(cols[col])
        if n < 6:
            continue
        vals = list(cols[col])
        uniq = list(dict.fromkeys(vals))
        if len(uniq) < 3:
            continue
        a, b, c = uniq[0], uniq[1], uniq[2]
        pattern = [a, b, b, c, c, c]
        for i in range(n):
            vals[i] = pattern[i % len(pattern)]
        cols[col] = vals


def _apply_duplicate_share(table: str, cols: dict, rng) -> None:
    """20-50 % duplicate share on DISTINCT columns."""
    for col in list(cols):
        if (table, col) not in spec.DISTINCT_DUP_COLUMNS:
            continue
        n = len(cols[col])
        if n < 4:
            continue
        vals = list(cols[col])
        uniq = list(dict.fromkeys(vals))
        if len(uniq) < 2:
            continue
        target_dup = max(1, int(n * rng.uniform(0.2, 0.5)))
        for i in range(target_dup):
            j = rng.randrange(n)
            vals[j] = rng.choice(uniq)
        cols[col] = vals


def _apply_ties(table: str, cols: dict, rng) -> None:
    """Ties at rank 1 on ORDER columns: force at least two equal values."""
    for col in list(cols):
        if (table, col) not in spec.TIE_COLUMNS:
            continue
        n = len(cols[col])
        if n < 2:
            continue
        vals = list(cols[col])
        vals[1] = vals[0]
        cols[col] = vals


def _apply_different_values(table: str, cols: dict, rng) -> None:
    """>= 2 per group with different values (order_quantity)."""
    for col in list(cols):
        if (table, col) not in spec.DIFFERENT_VALUE_COLUMNS:
            continue
        n = len(cols[col])
        if n < 2:
            continue
        vals = list(cols[col])
        for i in range(1, n):
            if vals[i] == vals[i - 1]:
                vals[i] = str(rng.randint(1, 20))
        cols[col] = vals


def _apply_date_order(table: str, cols: dict, rng) -> None:
    """date_to >= date_from (Customer_Address_History)."""
    t, c_from, c_to = spec.DATE_ORDER
    if table != t or c_from not in cols or c_to not in cols:
        return
    n = len(cols[c_from])
    for i in range(n):
        a, b = cols[c_from][i], cols[c_to][i]
        if a is None or b is None:
            continue
        if str(b) < str(a):
            cols[c_to][i] = a


def _apply_unmatched_parents(table: str, cols: dict, schema, rng) -> None:
    """Parent rows without children: leave at least one parent key unused by children."""
    return


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact_keys = _compact_keys(schema)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), table=t)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for c in tm.primary_key:
            if c in cols:
                start = _next_pk_start(schema, t, c)
                cols[c] = list(range(start, start + n))
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_keys))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _apply_null_rule(t, cols, schema, rng)
        _apply_group_sizes(t, cols, rng)
        _apply_duplicate_share(t, cols, rng)
        _apply_ties(t, cols, rng)
        _apply_different_values(t, cols, rng)
        _apply_date_order(t, cols, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
