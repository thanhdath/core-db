"""Random instance construction (fuzz/fuzz.py:83-196)."""
import re

from . import specification as specmod
from .values import _init_sampler, EnumSampler


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
                                   null_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        vals = []
        for _ in range(n):
            if pv and rng.random() >= null_share:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec_sizes: dict = None) -> dict:
    """Specification sizes when given; else uniform rand_lin w.p."""
    if spec_sizes:
        return {t: int(spec_sizes.get(t.lower(), 0)) for t in schema.tables}
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


def _fresh_pk_values(table_meta, n: int, rng, existing: set) -> list:
    """Sequential integers starting at 1, skipping values already present in the compact table."""
    out = []
    v = 1
    while len(out) < n:
        if v not in existing:
            out.append(v)
        v += 1
    return out


def _null_share_for(schema, t: str, c: str, rule: dict, rng) -> float:
    """NULL share: specification target if any, else the compact database's share for that column."""
    if rule and rule.get('null_share'):
        m = re.findall(r'\d+', str(rule['null_share']))
        if m:
            lo = int(m[0]) / 100.0
            hi = int(m[1]) / 100.0 if len(m) > 1 else lo
            return rng.uniform(lo, hi)
    vals = schema.original_values.get((t, c), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _apply_enum(columns: dict, t: str, c: str, enum: list, rng) -> None:
    """Replace a column's values with draws from a closed enumeration."""
    if c in columns and enum:
        s = EnumSampler(enum, rng)
        columns[c] = [s.sample() for _ in columns[c]]


def _apply_high_low(columns: dict, t: str, c_high: str, c_low: str) -> None:
    """High_Estimate >= Low_Estimate by construction (non-NULL operands only)."""
    if c_high in columns and c_low in columns:
        hi, lo = columns[c_high], columns[c_low]
        for i in range(min(len(hi), len(lo))):
            if hi[i] is not None and lo[i] is not None and hi[i] < lo[i]:
                hi[i] = lo[i]


def _apply_year_range(columns: dict, c: str, lo: int = 1900, hi: int = 2030) -> None:
    if c in columns:
        columns[c] = [None if v is None else min(max(int(v), lo), hi) for v in columns[c]]


def _apply_nonneg(columns: dict, c: str) -> None:
    if c in columns:
        columns[c] = [None if v is None else max(0, v) for v in columns[c]]


def _apply_positive(columns: dict, c: str) -> None:
    if c in columns:
        columns[c] = [None if v is None else (v if v > 0 else 1) for v in columns[c]]


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied by construction."""
    spec = spec if spec is not None else specmod.load_specification()
    rules = specmod.column_rules(spec)
    enums = specmod.enum_values(spec)
    nulls = specmod.null_targets(spec)
    spec_sizes = specmod.table_sizes(spec)
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                k = '%s.%s' % (t.lower(), cm.name.lower())
                rule = rules.get(k, {})
                kw = {}
                if rule.get('values'):
                    kw['boundary'] = rule['values']
                if rule.get('bounds'):
                    kw['bounds'] = rule['bounds']
                if rule.get('values') and not any(isinstance(v, (int, float)) for v in rule['values']):
                    kw['near_variants'] = rule['values']
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), **kw)
    if size is None:
        size = choose_table_sizes(schema, rng, spec_sizes)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for c in tm.primary_key:
            if c in cols:
                existing = {v for v in schema.original_values.get((t, c), []) if v is not None}
                cols[c] = _fresh_pk_values(tm, n, rng, existing)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for c, vals in fk_cols.items():
            k = '%s.%s' % (t.lower(), c.lower())
            share = _null_share_for(schema, t, c, rules.get(k, {}), rng)
            if k in nulls and share <= 0.0:
                share = 0.1
            if share > 0.0:
                vals = [None if rng.random() < share else v for v in vals]
            cols[c] = vals
        for c in list(cols):
            k = '%s.%s' % (t.lower(), c.lower())
            if k in enums:
                _apply_enum(cols, t, c, enums[k], rng)
        if t.lower() == 'film_market_estimation':
            _apply_high_low(cols, t, 'High_Estimate', 'Low_Estimate')
            _apply_year_range(cols, 'Year')
            _apply_positive(cols, 'Low_Estimate')
            _apply_positive(cols, 'High_Estimate')
        if t.lower() == 'film':
            _apply_nonneg(cols, 'Gross_in_dollar')
        if t.lower() == 'market':
            _apply_positive(cols, 'Number_cities')
        for c in list(cols):
            k = '%s.%s' % (t.lower(), c.lower())
            if k in nulls and cols[c] and all(v is not None for v in cols[c]):
                cols[c][rng.randrange(len(cols[c]))] = None
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
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
