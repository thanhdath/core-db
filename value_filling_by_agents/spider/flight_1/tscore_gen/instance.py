"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
import datetime as dt
import re

from .spec import exceptions_for
from .values import _init_sampler, _parse_date


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t or 'number' in t or 'year' in t


def _is_num_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))


def _is_date_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _is_str_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'varchar'))


def _to_datetime(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    if v is None:
        return None
    _, d = _parse_date(str(v))
    return d


def _near_duplicate(v: str, rng) -> str:
    """Case / whitespace variant of an existing string value."""
    u = rng.random()
    if u < 0.4:
        return v.lower()
    if u < 0.7:
        return v.upper()
    if u < 0.85:
        return ' ' + v
    return v + ' '


def _spec_range(spec: dict, table: str, column: str, type_str: str):
    """Value range for a numeric column from the specification (or None)."""
    t = (type_str or '').lower()
    if 'salary' in column.lower() or 'salary' in t:
        return spec.get('ranges', {}).get('decimal_salary')
    if 'price' in column.lower():
        return spec.get('ranges', {}).get('decimal_price')
    if 'distance' in column.lower():
        return spec.get('ranges', {}).get('integer_distance')
    return None


def _boundary_values(spec: dict, table: str, column: str) -> list:
    """Numeric boundary values from comparison_boundary exceptions."""
    out = []
    for e in exceptions_for(spec, table, column):
        if e.get('pattern') != 'comparison_boundary':
            continue
        for t in e.get('targets', []):
            try:
                out.append(float(t))
            except (TypeError, ValueError):
                pass
    return out


def _literal_pool_values(spec: dict, table: str, column: str) -> list:
    """Literal-pool values from literal_pool exceptions."""
    out = []
    for e in exceptions_for(spec, table, column):
        if e.get('pattern') != 'literal_pool':
            continue
        out.extend(str(t) for t in e.get('targets', []))
    return out


def _string_pool(spec: dict, table: str, column: str) -> list:
    """Fixed string pool for a column (city / aircraft name / person name)."""
    pools = spec.get('pools', {})
    c = column.lower()
    if 'origin' in c or 'destination' in c or 'city' in c:
        return list(pools.get('city', []))
    if 'aircraft' in table.lower() and 'name' in c:
        return list(pools.get('aircraft_name', []))
    if 'name' in c:
        first = pools.get('first_name', [])
        last = pools.get('last_name', [])
        if first and last:
            return ['%s %s' % (f, l) for f in first for l in last]
    return []


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(existing_keys), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing_unique: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict,
                                   compact_keys: dict) -> dict:
    """FK child columns draw from the parent's compact + generated key pool."""
    out = {}
    null_share = float(spec.get('null_share', 0.05))
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_keys.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        nullable = not cm.notnull and cm.pk_pos == 0
        vals = []
        for _ in range(n):
            if nullable and rng.random() < null_share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if nullable and n > 0 and None not in vals:
            vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def _apply_distinct_share(values: list, rng, share=(0.20, 0.50)) -> list:
    """Repeat values from a small pool so the duplicate share lands in [lo, hi]."""
    n = len(values)
    if n < 3:
        return values
    lo, hi = share
    target = int(round(n * rng.uniform(lo, hi)))
    target = max(1, min(n - 1, target))
    pool = list(values)
    rng.shuffle(pool)
    pool = pool[:max(1, n - target)]
    out = list(values)
    for i in range(target):
        out[rng.randrange(n)] = rng.choice(pool)
    return out


def _apply_group_sizes(values: list, rng, is_numeric: bool = False) -> list:
    """Ensure groups of size 1, 2 and >= 3 exist (values are group keys)."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    cand = [v for v in out if v is not None]
    if not cand:
        cand = [0 if is_numeric else 'g']
    a, b, c = rng.sample(range(n), 3)
    k1 = rng.choice(cand)
    k2 = rng.choice(cand)
    k3 = rng.choice(cand)
    out[a] = k1
    out[b] = k2
    out[(b + 1) % n] = k2
    for k in range(3):
        out[(c + k) % n] = k3
    return out


def _apply_order_ties(values: list, rng) -> list:
    """Plant a tie at rank 1 (two rows with equal value)."""
    n = len(values)
    if n < 2:
        return values
    out = list(values)
    i, j = rng.sample(range(n), 2)
    out[j] = out[i]
    return out


def _apply_near_duplicates(values: list, rng, share=0.05) -> list:
    """5 % near-duplicate variants (case / whitespace) of existing values."""
    out = list(values)
    n = len(out)
    if n == 0:
        return out
    k = max(1, int(round(n * share)))
    for _ in range(k):
        i = rng.randrange(n)
        if isinstance(out[i], str) and out[i]:
            out[i] = _near_duplicate(out[i], rng)
    return out


def _apply_null_share(values: list, rng, share=0.05) -> list:
    """At least one NULL row; share follows the specification."""
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    k = max(1, int(round(n * share)))
    for i in rng.sample(range(n), min(k, n)):
        out[i] = None
    return out


def _reinject_boundary_values(values: list, boundary: list, rng) -> list:
    """Re-inject comparison-boundary targets after near-duplicate clobbering."""
    if not boundary or not values:
        return values
    out = list(values)
    n = len(out)
    for t in boundary:
        out[rng.randrange(n)] = t
    return out


def _enforce_formulas(table: str, columns: dict, schema, spec: dict, rng) -> dict:
    """Enforce the specification's semantic formulas on sampled values."""
    n = _n_rows(columns)
    for f in spec.get('formulas', []):
        if f.get('table') != table:
            continue
        col = f.get('column')
        if col not in columns:
            continue
        kind = f.get('kind')
        vals = columns[col]
        if kind in ('gt', 'ge'):
            bound = f.get('value', 0)
            for i in range(n):
                v = vals[i]
                if v is None:
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if kind == 'gt' and fv <= bound:
                    vals[i] = bound + 1
                elif kind == 'ge' and fv < bound:
                    vals[i] = bound
        elif kind == 'ge_column':
            other = f.get('other')
            if other not in columns:
                continue
            ov = columns[other]
            for i in range(n):
                a, b = vals[i], ov[i]
                if a is None or b is None:
                    continue
                da, db = _to_datetime(a), _to_datetime(b)
                if da is None or db is None:
                    continue
                if da < db:
                    vals[i] = b
    return columns


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes with per-instance jitter (0-230 rows per table)."""
    base = spec.get('table_sizes', {})
    sizes = {}
    for t in schema.tables:
        b = int(base.get(t, 0))
        if b <= 0:
            sizes[t] = rng.randint(0, 20)
        else:
            jitter = rng.randint(-max(1, b // 4), max(1, b // 4))
            sizes[t] = max(0, min(230, b + jitter))
    return sizes


def _compact_keys(schema) -> dict:
    """Compact key pools per (table, column) for FK drawing."""
    out = {}
    for t, tm in schema.tables.items():
        for c in tm.columns:
            out[(t, c.name)] = [v for v in schema.original_values.get((t, c.name), []) if v is not None]
    return out


def _compact_unique(schema) -> dict:
    """Compact unique values per (table, column)."""
    out = {}
    for t, tm in schema.tables.items():
        for c in tm.columns:
            if c.unique:
                out[(t, c.name)] = {v for v in schema.original_values.get((t, c.name), []) if v is not None}
    return out


def _compact_pk(schema) -> dict:
    """Compact primary-key tuples per table."""
    out = {}
    for t, tm in schema.tables.items():
        if not tm.primary_key:
            out[t] = set()
            continue
        cols = [schema.original_values.get((t, c), []) for c in tm.primary_key]
        n = min((len(c) for c in cols), default=0)
        out[t] = {tuple(c[i] for c in cols) for i in range(n)}
    return out


def _column_sampler(schema, table, cm, literal_pool, spec, rng, p, n_pk):
    """Build a sampler for one non-FK column, injecting the specification."""
    t = table
    c = cm.name
    ov = list(schema.original_values.get((t, c), []))
    pool = list(literal_pool.get((t, c), []))
    sp = _string_pool(spec, t, c)
    if sp and _is_str_type(cm.type_str):
        pool = pool + sp
    pool = pool + _literal_pool_values(spec, t, c)
    bvals = _boundary_values(spec, t, c)
    if bvals:
        pool = pool + [str(v) for v in bvals]
    vrange = _spec_range(spec, t, c, cm.type_str)
    date_range = spec.get('date_range') if _is_date_type(cm.type_str) else None
    date_format = spec.get('date_format') if _is_date_type(cm.type_str) else None
    return _init_sampler(cm, pool, ov, p, rng, n_pk, value_range=vrange,
                         date_range=date_range, date_format=date_format)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    if spec is None:
        from .spec import default_specification
        spec = default_specification()
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _column_sampler(schema, t, cm, literal_pool, spec, rng, p,
                                                         len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    compact_keys = _compact_keys(schema)
    compact_unique = _compact_unique(schema)
    compact_pk = _compact_pk(schema)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec, compact_keys))
        for cm in tm.columns:
            if (t, cm.name) in schema.fks or cm.name not in cols:
                continue
            ex = exceptions_for(spec, t, cm.name)
            pats = {e.get('pattern') for e in ex}
            vals = cols[cm.name]
            if 'duplicates_for_distinct' in pats:
                vals = _apply_distinct_share(vals, rng, tuple(spec.get('distinct_share', (0.2, 0.5))))
            if 'group_sizes' in pats:
                vals = _apply_group_sizes(vals, rng, is_numeric=_is_num_type(cm.type_str))
            if 'ties_for_order_limit' in pats:
                vals = _apply_order_ties(vals, rng)
            if _is_str_type(cm.type_str):
                vals = _apply_near_duplicates(vals, rng)
            bvals = _boundary_values(spec, t, cm.name)
            if bvals and _is_str_type(cm.type_str):
                vals = _reinject_boundary_values(vals, [str(v) for v in bvals], rng)
            cols[cm.name] = vals
        for cm in tm.columns:
            if (t, cm.name) in schema.fks or cm.name not in cols:
                continue
            if not cm.notnull and cm.pk_pos == 0:
                cols[cm.name] = _apply_null_share(cols[cm.name], rng, float(spec.get('null_share', 0.05)))
        cols = _enforce_formulas(t, cols, schema, spec, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols},
                                         compact_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols, {c: compact_unique.get((t, c), set()) for c in cols})
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
