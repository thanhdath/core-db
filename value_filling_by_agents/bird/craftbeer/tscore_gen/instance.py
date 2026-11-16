"""Random instance construction (fuzz/fuzz.py:83-196) + patch-64 specification-driven samplers."""
import random

from .values import _init_sampler


SPEC_LITERALS = {
    ('breweries', 'name'): ['Stevens Point Brewery', 'Boston Beer Company'],
    ('breweries', 'state'): ['WI', 'wi'],
    ('beers', 'style'): ['American Adjunct Lager', 'american adjunct lager',
                         'American Adjunct Lage', 'American Adjunct Lager '],
    ('beers', 'ounces'): [12.0],
}

SPEC_RANGES = {
    ('beers', 'abv'): (0.0, 0.2),
    ('beers', 'ibu'): (0.0, 200.0),
    ('beers', 'ounces'): (0.1, 40.0),
}

SPEC_NULL_RATE = {
    ('beers', 'abv'): 0.026,
    ('beers', 'ibu'): 0.417,
    ('beers', 'style'): 0.002,
    ('breweries', 'name'): 0.0,
    ('breweries', 'city'): 0.0,
    ('breweries', 'state'): 0.0,
}

SPEC_TABLE_SIZES = {'breweries': 60, 'beers': 240}

STATE_LEN = 2
_STATE_POOL = ['MN', 'KY', 'MA', 'CA', 'SC', 'CO', 'MI', 'IN']


def build_spec(schema) -> dict:
    """Return the spec dict (deterministic; no per-instance randomness)."""
    return {'literals': SPEC_LITERALS, 'ranges': SPEC_RANGES,
            'null_rate': SPEC_NULL_RATE, 'sizes': SPEC_TABLE_SIZES}


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


def choose_table_sizes(schema, rng: random.Random, spec: dict) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                n = spec['sizes'].get(t, 0)
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * n)) if n else int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                n = spec['sizes'].get(t, 0)
                sizes[t] = int(min(s, n) if n else min(s, 2500))
            s *= 4
    return sizes


def _apply_spec_rules(schema, table, col, values, rng):
    """Apply semantic constraints (state length, etc.) to a column of sampled values."""
    if table == 'breweries' and col == 'state':
        out = []
        for v in values:
            if v is None:
                out.append(None)
            elif len(str(v)) == STATE_LEN:
                out.append(v)
            else:
                out.append(rng.choice(_STATE_POOL))
        return out
    return values


def _inject_nulls(table, col, values, rate, rng):
    """NULL rule: at least one NULL per nullable column, share ~= rate; never repair planted NULLs."""
    n = len(values)
    if n == 0:
        return values
    k = int(round(rate * n))
    if k < 1:
        k = 1
    if k > n:
        k = n
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _clamp_numeric(table, col, values, spec, rng):
    """Enforce numeric domains and semantic formulas by construction (non-NULL only)."""
    key = (table, col)
    rng_range = spec['ranges'].get(key)
    literals = spec['literals'].get(key, [])
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if rng_range is not None:
            lo, hi = rng_range
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = rng.uniform(lo, hi)
            if f < lo or f > hi:
                f = rng.uniform(lo, hi)
            out.append(f)
        elif literals:
            out.append(v)
        else:
            out.append(v)
    if literals and out:
        pos = rng.randrange(len(out))
        out[pos] = rng.choice(literals)
    return out


def build_random_instance(schema, literal_pool: dict, size, rng: random.Random, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196)."""
    if spec is None:
        spec = build_spec(schema)
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                pool = (literal_pool.get((t, cm.name), []) +
                        spec['literals'].get((t, cm.name), []))
                samplers[(t, cm.name)] = _init_sampler(cm, pool, schema.original_values.get((t, cm.name), []),
                                                       p, rng, len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                vals = [samplers[(t, cm.name)].sample() for _ in range(n)]
                vals = _clamp_numeric(t, cm.name, vals, spec, rng)
                vals = _apply_spec_rules(schema, t, cm.name, vals, rng)
                if (t, cm.name) in spec['null_rate']:
                    vals = _inject_nulls(t, cm.name, vals, spec['null_rate'][(t, cm.name)], rng)
                cols[cm.name] = vals
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
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def build_instance(schema, literal_pool: dict, spec: dict, rng: random.Random) -> dict:
    """Build one instance for the spec (append-only)."""
    return build_random_instance(schema, literal_pool, None, rng, spec)
