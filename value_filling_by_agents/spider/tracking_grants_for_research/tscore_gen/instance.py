"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification rules."""
import datetime as dt

from .spec import formula_holds, parse_dt, fmt_dt
from .values import make_spec_sampler, _init_sampler


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
    """Specification sizes when given; else uniform rand_lin w.p."""
    if spec is not None and spec.sizes:
        return {t: int(spec.sizes.get(t, 0)) for t in schema.tables}
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


def _compact_rows(schema, table):
    """Compact rows of a table as a list of dicts (in memory, never modified)."""
    tm = schema.tables[table]
    cols = [c.name for c in tm.columns]
    n = len(schema.original_values.get((table, cols[0]), [])) if cols else 0
    rows = []
    for i in range(n):
        rows.append({c: schema.original_values[(table, c)][i] for c in cols})
    return rows


def _next_int_pk(schema, table, existing):
    """Next sequential integer primary key above the compact maximum."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    vals = [r.get(pk) for r in existing if isinstance(r.get(pk), int)]
    return (max(vals) + 1) if vals else 1


def _next_double_pk(schema, table, existing):
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    vals = [r.get(pk) for r in existing if isinstance(r.get(pk), (int, float))]
    return (float(max(vals)) + 1.0) if vals else 0.0


def _is_double_type(type_str):
    return 'double' in (type_str or '').lower() or 'real' in (type_str or '').lower()


def _null_share(schema, table, column):
    """NULL share following the compact database's share for that column."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.05
    return sum(1 for v in vals if v is None) / len(vals)


def _apply_null_rule(schema, spec, table, cols, rng):
    """Plant NULLs in nullable columns: compact share, at least one NULL row per column."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.notnull or cm.pk_pos > 0:
            continue
        share = _null_share(schema, table, cm.name)
        if spec is not None and spec.is_null_target(table, cm.name):
            share = max(share, 0.05)
        k = int(round(share * n))
        k = max(1, min(n, k))
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _coerce_datetime(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, str):
        return parse_dt(v)
    return None


def _apply_formulas(schema, spec, table, cols, rng):
    """Enforce semantic formulas by construction (Python, in memory)."""
    if spec is None or not cols:
        return cols
    n = len(next(iter(cols.values())))
    for f in spec.formulas:
        if f.table != table or f.kind != 'ge':
            continue
        a, b = f.left, f.right
        if a not in cols or b not in cols:
            continue
        for i in range(n):
            va, vb = cols[a][i], cols[b][i]
            if va is None or vb is None:
                continue
            da, db = _coerce_datetime(va), _coerce_datetime(vb)
            if da is not None and db is not None:
                if da < db:
                    gap = dt.timedelta(seconds=rng.randint(1, 86400 * 365))
                    cols[a][i] = fmt_dt(db + gap)
                continue
            try:
                if va < vb:
                    cols[a][i] = vb + abs(vb) * 0.01 + 0.0001
            except TypeError:
                pass
    return cols


def _apply_comparison_boundaries(schema, spec, table, cols, samplers, rng):
    """Ensure boundary literals appear among the generated values of boundary columns."""
    if spec is None or not cols:
        return cols
    n = len(next(iter(cols.values())))
    for cm in schema.tables[table].columns:
        if cm.name not in cols:
            continue
        s = samplers.get((table, cm.name))
        boundary = getattr(s, 'boundary', None) if s is not None else None
        if not boundary or n == 0:
            continue
        k = min(len(boundary), n)
        idx = rng.sample(range(n), k)
        for j, i in enumerate(idx):
            cols[cm.name][i] = boundary[j]
    return cols


def _apply_duplicate_share(schema, spec, table, cols, rng):
    """duplicates_for_distinct: 20-50% duplicate share in the target column."""
    if spec is None or not cols:
        return cols
    n = len(next(iter(cols.values())))
    for cm in schema.tables[table].columns:
        if cm.name not in cols:
            continue
        cs = spec.exc(table, cm.name)
        if cs is None or cs.pattern != 'duplicates_for_distinct':
            continue
        if n < 2:
            continue
        share = rng.uniform(0.2, 0.5)
        k = max(1, int(round(share * n)))
        src = rng.sample(range(n), min(k, n))
        for i in src:
            j = rng.randrange(n)
            if j != i:
                cols[cm.name][i] = cols[cm.name][j]
    return cols


def _apply_unmatched_join_rows(schema, spec, table, cols, rng):
    """unmatched_join_rows: leave some parent rows without children."""
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = make_spec_sampler(
                    cm, spec, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng, len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    pools: dict = {}
    for t in order:
        pools[t] = _compact_rows(schema, t)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = [r.get(pc) for r in pools.get(pt, []) if r.get(pc) is not None]
            cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            pk_col = next((c for c in tm.columns if c.name == pk), None)
            if pk_col is not None and (t, pk) not in schema.fks:
                if _is_double_type(pk_col.type_str):
                    start = _next_double_pk(schema, t, pools[t])
                    cols[pk] = [start + i for i in range(n)]
                else:
                    start = _next_int_pk(schema, t, pools[t])
                    cols[pk] = [start + i for i in range(n)]
        cols = _apply_comparison_boundaries(schema, spec, t, cols, samplers, rng)
        cols = _apply_duplicate_share(schema, spec, t, cols, rng)
        cols = _apply_formulas(schema, spec, t, cols, rng)
        cols = _apply_null_rule(schema, spec, t, cols, rng)
        cols = _dedupe_against_compact(schema, t, cols, pools[t])
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        names = [c.name for c in tm.columns]
        m = len(cols.get(names[0], [])) if names else 0
        for i in range(m):
            pools[t].append({c: cols[c][i] for c in names if c in cols})
    return {t: inst[t] for t in schema.tables}


def _dedupe_against_compact(schema, table, cols, compact_rows):
    """Drop generated rows whose PK/UNIQUE tuple already exists in the compact rows."""
    tm = schema.tables[table]
    if not cols:
        return cols
    n = len(next(iter(cols.values())))
    keep = list(range(n))
    if tm.primary_key:
        seen = {tuple(r.get(c) for c in tm.primary_key) for r in compact_rows}
        keep = [i for i in keep if tuple(cols[c][i] for c in tm.primary_key) not in seen]
    for cm in tm.columns:
        if cm.unique and cm.name in cols:
            seen = {r.get(cm.name) for r in compact_rows}
            keep = [i for i in keep if cols[cm.name][i] not in seen]
    return _filter(cols, keep)
