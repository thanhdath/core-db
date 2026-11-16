"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _compact_keys(schema, table: str) -> set:
    """Set of PK tuples present in the compact database for a table."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = len(cols[0]) if cols else 0
    return {tuple(cols[j][i] for j in range(len(cols))) for i in range(n)}


def _compact_max_int(schema, table: str, col: str) -> int:
    """Max integer value of a compact column (0 if none)."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, (int, float))]
    return int(max(vals)) if vals else 0


def _offset_primary_keys(table: str, cols: dict, tm, schema, rng) -> None:
    """Offset generated integer PKs above max(compact PK) so they never collide."""
    if not tm.primary_key or len(tm.primary_key) != 1:
        return
    pk = tm.primary_key[0]
    if pk not in cols:
        return
    vals = cols[pk]
    if not vals or not all(isinstance(v, (int, float)) for v in vals if v is not None):
        return
    base = _compact_max_int(schema, table, pk)
    for i, v in enumerate(vals):
        if v is not None:
            vals[i] = base + 1 + i


def sample_fresh_primary_keys(table_meta, columns: dict, compact_keys: set = None) -> dict:
    """Drop rows whose PK tuple repeats (compact or batch), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    compact_keys = compact_keys or set()
    n = _nrows(columns)
    seen, keep = set(compact_keys), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, schema=None, table: str = '') -> dict:
    """Drop rows repeating any single unique column value (compact or batch)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            compact = set()
            if schema is not None:
                compact = {v for v in schema.original_values.get((table, cm.name), []) if v is not None}
            seen, keep = set(compact), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(schema, instance: dict, pt: str, pc: str) -> list:
    """Final parent key pool: compact values + generated values, non-NULL, deduped."""
    pv = list(schema.original_values.get((pt, pc), []))
    pv += list(instance.get(pt, {}).get(pc) or [])
    out, seen = [], set()
    for v in pv:
        if v is None:
            continue
        k = (type(v).__name__, v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _reserved_keys(table: str) -> set:
    """PK tuples reserved as unmatched parents for this table (per instance)."""
    return spec.RESERVED_UNMATCHED.get(table, set())


def _fk_pool(schema, instance: dict, pt: str, pc: str) -> list:
    """Parent key pool for FK fill: excludes keys reserved as unmatched parents."""
    pv = _parent_pool(schema, instance, pt, pc)
    reserved = _reserved_keys(pt)
    if not reserved:
        return pv
    out = []
    for v in pv:
        if (v,) in reserved:
            continue
        out.append(v)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's FINAL values (compact + generated), excluding keys reserved as
    unmatched parents."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _fk_pool(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _revalidate_fks(instance: dict, schema, table: str, cols: dict, rng) -> None:
    """After parent finalization, every non-NULL FK value must exist in the parent key set."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in cols:
            continue
        pt, pc = schema.fks[key]
        pv = _fk_pool(schema, instance, pt, pc)
        fs = set(pv)
        vals = cols[cm.name]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in fs:
                vals[i] = rng.choice(pv) if pv else None


def choose_table_sizes(schema, rng) -> dict:
    """Fixed per-instance sizes from the specification (no jitter)."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = int(spec.TABLE_SIZES.get(t, 20))
    return sizes


def _apply_null_rule(table: str, cols: dict, tm, rng) -> None:
    """Every nullable column gets >=1 NULL and a share following the compact share."""
    n = _nrows(cols)
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols or cm.notnull or cm.pk_pos > 0:
            continue
        lo, hi = spec.NULL_SHARE.get((table, cm.name), spec.DEFAULT_NULL_SHARE)
        share = rng.uniform(lo, hi)
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None


def _plant_child_fk_nulls(table: str, cols: dict, schema, rng) -> None:
    """Guarantee at least one NULL in each child FK column listed in NULL_FK_CHILD."""
    n = _nrows(cols)
    if n == 0:
        return
    for (ct, cc) in spec.NULL_FK_CHILD:
        if ct != table or cc not in cols:
            continue
        if (table, cc) not in schema.fks:
            continue
        vals = cols[cc]
        if any(v is None for v in vals):
            continue
        vals[rng.randrange(n)] = None


def _apply_unmatched_parent(table: str, cols: dict, rng) -> None:
    """Reserve at least one parent row with no children."""
    if table not in spec.UNMATCHED_PARENT:
        return
    tm = spec.TABLE_META.get(table)
    if tm is None or not tm.primary_key:
        return
    n = _nrows(cols)
    if n < 2:
        return
    key = tuple(cols[c][n - 1] for c in tm.primary_key)
    spec.RESERVED_UNMATCHED.setdefault(table, set()).add(key)


def _apply_formulas(table: str, cols: dict, tm, rng, schema=None) -> None:
    """Enforce semantic formulas in Python; a violating value is re-drawn (never NULL-replaced)."""
    n = _nrows(cols)
    for cm in tm.columns:
        f = spec.FORMULAS.get((table, cm.name))
        if f is None or cm.name not in cols:
            continue
        is_pk = cm.pk_pos > 0
        for i in range(n):
            row = {c: cols[c][i] for c in cols}
            v = cols[cm.name][i]
            if v is None:
                continue
            try:
                ok = f(v, row) if f.__code__.co_argcount > 1 else f(v)
            except Exception:
                ok = True
            if not ok:
                if is_pk and isinstance(v, (int, float)):
                    cur = [x for x in cols[cm.name] if isinstance(x, (int, float))]
                    cols[cm.name][i] = int(max(cur) if cur else 0) + 1
                else:
                    pool = [x for x in cols[cm.name] if x is not None]
                    if pool:
                        cols[cm.name][i] = rng.choice(pool)


def _apply_group_sizes(table: str, cols: dict, tm, rng) -> None:
    """Ensure the grouping column shows group sizes 1, 2 and >=3 (by construction)."""
    for (gt, gc), sizes in spec.GROUP_SIZES.items():
        if gt != table or gc not in cols:
            continue
        if gc in tm.primary_key:
            continue
        vals = cols[gc]
        if not vals:
            continue
        uniq = list(dict.fromkeys(vals))
        if len(uniq) < 3:
            continue
        a, b, c = uniq[0], uniq[1], uniq[2]
        vals[0] = a
        if len(vals) > 1:
            vals[1] = b
        if len(vals) > 2:
            vals[2] = b
        for i in range(3, min(len(vals), 6)):
            vals[i] = c


def _apply_job_history_multiplicity(table: str, cols: dict, schema, rng) -> None:
    """job_history.EMPLOYEE_ID group sizes (1, 2, >=3) by choosing employee ids with those multiplicities."""
    if table != 'job_history' or 'EMPLOYEE_ID' not in cols:
        return
    n = _nrows(cols)
    if n < 6:
        return
    pool = _parent_pool(schema, {}, 'employees', 'EMPLOYEE_ID')
    if len(pool) < 3:
        return
    picks = rng.sample(pool, 3)
    e1, e2, e3 = picks
    assign = [e1] + [e2, e2] + [e3] * (n - 3)
    rng.shuffle(assign)
    cols['EMPLOYEE_ID'] = assign
    if 'START_DATE' in cols:
        seen = {}
        for i in range(n):
            e = cols['EMPLOYEE_ID'][i]
            s = cols['START_DATE'][i]
            if (e, s) in seen:
                d = dt.datetime.strptime(str(s), '%Y-%m-%d') if s else dt.datetime(2000, 1, 1)
                while (e, d.strftime('%Y-%m-%d')) in seen:
                    d += dt.timedelta(days=1)
                cols['START_DATE'][i] = d.strftime('%Y-%m-%d')
            seen[(e, cols['START_DATE'][i])] = True


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied."""
    spec.RESERVED_UNMATCHED.clear()
    spec.TABLE_META.clear()
    for t, tm in schema.tables.items():
        spec.TABLE_META[t] = tm
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
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        _apply_unmatched_parent(t, cols, rng)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        _apply_formulas(t, cols, tm, rng, schema)
        _offset_primary_keys(t, cols, tm, schema, rng)
        compact_pk = _compact_keys(schema, t)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, compact_pk)
        cols = drop_unique_duplicates(tm, cols, schema, t)
        _revalidate_fks(inst, schema, t, cols, rng)
        _apply_null_rule(t, cols, tm, rng)
        _plant_child_fk_nulls(t, cols, schema, rng)
        _apply_group_sizes(t, cols, tm, rng)
        _apply_job_history_multiplicity(t, cols, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
