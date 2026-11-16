"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import re

from .values import _init_sampler

_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(existing.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values (or NULL)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        if key in spec.get('child_null_fk', set()) and n > 1:
            vals[0] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes when given, else the upstream rand_lin / level sizes."""
    if spec.get('sizes'):
        sizes = {}
        for lvl in schema.table_order:
            for t in lvl:
                base = spec['sizes'].get(t)
                if base is None:
                    base = 30 * rng.random() + int(rng.random() * 200)
                if rng.random() < 0.5:
                    sizes[t] = int(rng.randint(0, max(1, min(230, int(base) + 30))))
                else:
                    sizes[t] = int(min(max(1, int(base) * 4), 2500))
        return sizes
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
    """Plant a NULL share (>= 1 row) on a nullable column; planted NULLs are never replaced."""
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


def _formula_ok(formula: str, value) -> bool:
    """Check a semantic formula by construction (no SQL): NULL always holds (3-valued logic)."""
    if value is None:
        return True
    f = formula or ''
    m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
    if m:
        allowed = {x.strip().strip("'\"") for x in m.group(1).split(',')}
        return str(value) in allowed or str(value).lower() in {a.lower() for a in allowed}
    m = re.search(r"BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)", f, re.I)
    if m:
        try:
            return int(m.group(1)) <= float(value) <= int(m.group(2))
        except (TypeError, ValueError):
            return False
    return True


def _spec_kwargs(spec: dict, key: tuple) -> dict:
    """Sampler keyword arguments derived from the specification for one column."""
    enum = spec.get('boundary_values', {}).get(key, [])
    like = spec.get('like_literals', {}).get(key, [])
    near = spec.get('near_variants', {}).get(key, [])
    boundary = []
    for v in enum:
        if _NUM.fullmatch(str(v)):
            boundary.append(v)
    return {'enum': enum, 'like': like, 'near': near, 'boundary': boundary}


def _null_share(spec: dict, key: tuple, rng) -> float:
    if key in spec.get('null_targets', set()):
        return rng.uniform(0.05, 0.30)
    return 0.0


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) appended to the compact rows."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                kw = _spec_kwargs(spec, (t, cm.name))
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), **kw)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        inst[t] = {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                share = _null_share(spec, (t, cm.name), rng)
                if share > 0:
                    cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
        for cm in tm.columns:
            f = spec.get('formulas', {}).get((t, cm.name))
            if f and cm.name in cols:
                keep = [i for i, v in enumerate(cols[cm.name]) if _formula_ok(f, v)]
                if len(keep) != len(cols[cm.name]):
                    cols = _filter(cols, keep)
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, len(next(iter(cols.values()))) if cols else 0,
                                                 rng, spec)
        cols.update(fk_cols)
        existing_pk = set()
        if tm.primary_key:
            pv = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            for i in range(min((len(x) for x in pv), default=0)):
                existing_pk.add(tuple(x[i] for x in pv))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing_pk)
        existing_uq = {cm.name: set(schema.original_values.get((t, cm.name), []))
                       for cm in tm.columns if cm.unique}
        cols = drop_unique_duplicates(tm, cols, existing_uq)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            base = inst[t].get(cm.name, [])
            inst[t][cm.name] = base + list(cols.get(cm.name, []))
    return {t: inst[t] for t in schema.tables}
