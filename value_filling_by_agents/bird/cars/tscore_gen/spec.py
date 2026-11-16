"""Specification implemented by construction (round 1)."""
import math
import re

TABLE_SIZES = {'country': 3, 'price': 40, 'data': 40, 'production': 60}
NULL_TARGETS = ['production.country', 'data.car_name']
NULL_SHARE = 0.08
DUP_SHARE = 0.30
TIE_SHARE = 0.15

ENUMS = {
    ('country', 'origin'): [1, 2, 3],
    ('country', 'country'): ['USA', 'Europe', 'Japan'],
    ('data', 'cylinders'): [3, 4, 5, 6, 8],
}
RANGES = {
    ('price', 'price'): (0.0, 50000.0),
    ('data', 'mpg'): (1.0, 60.0),
    ('data', 'displacement'): (60.0, 500.0),
    ('data', 'horsepower'): (40, 250),
    ('data', 'weight'): (1500, 5200),
    ('data', 'acceleration'): (5.0, 30.0),
    ('data', 'model'): (70, 82),
    ('production', 'model_year'): (1970, 1982),
}
BOUNDARIES = {
    ('data', 'ID'): [14, 15, 16],
    ('production', 'ID'): [14, 15, 16, 380, 381, 382, 383],
    ('price', 'ID'): [14, 15, 16],
    ('country', 'country'): ['USA', 'usa', 'Japan', 'japan'],
    ('production', 'model_year'): [1969, 1970, 1971],
    ('price', 'price'): [19999.9999, 20000, 20000.0001, 29999.9999, 30000, 30000.0001],
    ('data', 'car_name'): ['chevy c20', 'CHEVY C20', 'ford maverick', 'FORD MAVERICK'],
    ('data', 'mpg'): [29999.9, 30000, 30000.1],
    ('country', 'origin'): [0, 1, 2],
    ('production', 'country'): [0, 1, 2],
    ('data', 'cylinders'): [7, 8, 9],
    ('data', 'displacement'): [29, 30, 31],
}
DISTINCT_COLS = [('data', 'ID'), ('production', 'ID'), ('country', 'country'),
                 ('production', 'model_year'), ('data', 'car_name'), ('data', 'model')]
TIE_COLS = [('country', 'country'), ('production', 'model_year'), ('price', 'price'),
            ('data', 'mpg'), ('data', 'acceleration')]
DIFF_VALUE_COLS = [('data', 'mpg'), ('data', 'weight'), ('data', 'horsepower')]

CAR_NAMES = ['chevrolet chevelle malibu', 'buick skylark 320', 'plymouth satellite',
             'amc rebel sst', 'ford torino', 'ford galaxie 500', 'chevrolet impala',
             'plymouth fury iii', 'dodge challenger se', 'toyota corolla 1200',
             'honda civic', 'datsun 1200', 'volkswagen super beetle', 'peugeot 504',
             'audi 100 ls', 'volvo 145e', 'bmw 2002', 'mercury capri 2000',
             'pontiac catalina', 'oldsmobile delta 88', 'chevy c20', 'ford maverick']


def _is_int_type(t: str) -> bool:
    t = (t or '').lower()
    return 'int' in t


def _is_real_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number'))


def _step(v):
    """One step for a numeric literal (integers by 1, reals by 0.0001/0.1)."""
    if isinstance(v, int):
        return 1
    s = repr(float(v))
    if '.' in s:
        dec = len(s.split('.')[1].rstrip('0'))
        return 10 ** (-max(dec, 1))
    return 1


def _near_variants(v: str) -> list:
    """Case changes and one-character edits of a text literal."""
    out = [v, v.upper(), v.lower(), v.title()]
    if v:
        out.append(v[:-1])
        out.append(v[1:])
        out.append(v + 'x')
        out.append('x' + v)
    return [x for x in dict.fromkeys(out) if x]


def _boundary_pool(values: list) -> list:
    """Literal, one step below, one step above (numbers) / near-variants (text)."""
    out = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            st = _step(v)
            out += [v, v - st, v + st]
        else:
            out += _near_variants(str(v))
    return list(dict.fromkeys(out))


def build_spec(schema, pool: dict) -> dict:
    """Per-column plans + table sizes + FK dependency order."""
    plans: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            plan = {
                'type': cm.type_str,
                'is_int': _is_int_type(cm.type_str),
                'is_real': _is_real_type(cm.type_str),
                'notnull': cm.notnull or cm.pk_pos > 0,
                'pk': cm.pk_pos > 0,
                'unique': cm.unique,
                'enum': ENUMS.get(key),
                'range': RANGES.get(key),
                'boundaries': _boundary_pool(BOUNDARIES.get(key, [])),
                'pool': [str(x) for x in pool.get(key, [])],
                'observed': [v for v in schema.original_values.get(key, []) if v is not None],
                'null_share': NULL_SHARE if ('%s.%s' % key) in NULL_TARGETS else 0.0,
                'dup_share': DUP_SHARE if key in DISTINCT_COLS else 0.0,
                'tie': key in TIE_COLS,
                'diff_values': key in DIFF_VALUE_COLS,
                'car_name': key == ('data', 'car_name'),
            }
            plans[key] = plan
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 20)
        sizes[t] = base
    return {'plans': plans, 'sizes': sizes, 'fks': dict(schema.fks),
            'order': [t for lvl in schema.table_order for t in lvl]}


def _round_real(v: float) -> float:
    return round(float(v), 2)


def _sample_scalar(plan: dict, rng, force_boundary: bool = False):
    """One non-NULL value for a column plan."""
    if plan['enum']:
        return rng.choice(plan['enum'])
    if plan['car_name']:
        if plan['boundaries'] and rng.random() < 0.25:
            return rng.choice(plan['boundaries'])
        return rng.choice(CAR_NAMES)
    if plan['boundaries'] and (force_boundary or rng.random() < 0.20):
        return rng.choice(plan['boundaries'])
    if plan['pool'] and rng.random() < 0.15:
        v = rng.choice(plan['pool'])
        if plan['is_int']:
            try:
                return int(float(v))
            except ValueError:
                return v
        if plan['is_real']:
            try:
                return _round_real(float(v))
            except ValueError:
                return v
        return v
    if plan['range']:
        lo, hi = plan['range']
        if plan['is_int']:
            return rng.randint(int(lo), int(hi))
        return _round_real(rng.uniform(lo, hi))
    if plan['observed'] and rng.random() < 0.5:
        v = rng.choice(plan['observed'])
        if plan['is_int']:
            try:
                return int(v)
            except (TypeError, ValueError):
                return v
        if plan['is_real']:
            try:
                return _round_real(float(v))
            except (TypeError, ValueError):
                return v
        return v
    if plan['is_int']:
        return rng.randint(0, 100)
    if plan['is_real']:
        return _round_real(rng.uniform(0, 100))
    return 'v%d' % rng.randint(0, 999)


def _sample_column(plan: dict, n: int, rng, pk_start: int = None) -> list:
    """n values honouring NULL share, duplicates, ties and boundary literals."""
    if plan['pk'] and pk_start is not None:
        return list(range(pk_start, pk_start + n))
    vals = []
    tie_val = None
    if plan['tie']:
        tie_val = _sample_scalar(plan, rng, force_boundary=True)
    for i in range(n):
        if plan['tie'] and tie_val is not None and rng.random() < TIE_SHARE:
            vals.append(tie_val)
        else:
            vals.append(_sample_scalar(plan, rng))
    if plan['dup_share'] > 0 and n > 1:
        k = int(round(n * plan['dup_share']))
        for _ in range(k):
            j = rng.randrange(n)
            src = rng.randrange(n)
            vals[j] = vals[src]
    if not plan['notnull'] and plan['null_share'] > 0 and n > 0:
        k = max(1, int(round(n * plan['null_share'])))
        idx = rng.sample(range(n), min(k, n))
        for j in idx:
            vals[j] = None
    return vals


def _fk_values(schema, spec, table: str, col: str, n: int, rng, parent_rows: dict, plan: dict) -> list:
    """FK column draws from the parent's rows (compact or generated) or is NULL."""
    pt, pc = spec['fks'][(table, col)]
    pv = list(parent_rows.get(pt, {}).get(pc, []))
    pv = [v for v in pv if v is not None]
    out = []
    for _ in range(n):
        if not pv:
            out.append(None)
        elif not plan['notnull'] and rng.random() < plan['null_share']:
            out.append(None)
        else:
            out.append(rng.choice(pv))
    if not plan['notnull'] and pv and n > 0 and all(v is not None for v in out):
        out[rng.randrange(n)] = None
    return out


def _dedupe_pk(schema, table: str, cols: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated); first occurrence kept."""
    tm = schema.tables[table]
    if not tm.primary_key or not cols:
        return cols
    n = len(next(iter(cols.values())))
    seen = set(existing)
    keep = []
    for i in range(n):
        k = tuple(cols[c][i] for c in tm.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return {c: [v[i] for i in keep] for c, v in cols.items()}


def _dedupe_unique(schema, table: str, cols: dict) -> dict:
    """Drop rows repeating a single-column UNIQUE value."""
    for cm in schema.tables[table].columns:
        if cm.unique and cm.name in cols:
            seen, keep = set(), []
            for i, v in enumerate(cols[cm.name]):
                if v is None or v not in seen:
                    seen.add(v)
                    keep.append(i)
            cols = {c: [v[i] for i in keep] for c, v in cols.items()}
    return cols


def generate_rows(schema, spec: dict, pool: dict, rng) -> dict:
    """Sample appended rows in FK order; parent rows kept in memory for lookups."""
    plans = spec['plans']
    parent_rows: dict = {}
    out: dict = {}
    for t in spec['order']:
        tm = schema.tables[t]
        n = int(spec['sizes'].get(t, 0))
        if n <= 0:
            out[t] = {}
            continue
        cols: dict = {}
        pk_cols = tm.primary_key
        pk_start = None
        if len(pk_cols) == 1:
            pc = pk_cols[0]
            pcm = next(c for c in tm.columns if c.name == pc)
            if _is_int_type(pcm.type_str):
                existing = [v for v in schema.original_values.get((t, pc), []) if isinstance(v, int)]
                pk_start = (max(existing) + 1) if existing else 1
        for cm in tm.columns:
            key = (t, cm.name)
            plan = plans[key]
            if key in spec['fks']:
                cols[cm.name] = _fk_values(schema, spec, t, cm.name, n, rng, parent_rows, plan)
            elif cm.pk_pos > 0 and pk_start is not None and len(pk_cols) == 1:
                cols[cm.name] = list(range(pk_start, pk_start + n))
            else:
                cols[cm.name] = _sample_column(plan, n, rng)
        existing = set()
        if tm.primary_key:
            ov = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            m = min((len(x) for x in ov), default=0)
            existing = {tuple(ov[j][i] for j in range(len(tm.primary_key))) for i in range(m)}
        cols = _dedupe_pk(schema, t, cols, existing)
        cols = _dedupe_unique(schema, t, cols)
        out[t] = cols
        merged = {}
        for cm in tm.columns:
            merged[cm.name] = list(schema.original_values.get((t, cm.name), [])) + list(cols.get(cm.name, []))
        parent_rows[t] = merged
    return out
