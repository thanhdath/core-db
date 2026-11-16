"""Specification implemented by construction (round 1, revised)."""
import datetime as dt
import re

from .values import _init_sampler

TABLE_SIZES = {'Air Carriers': 40, 'Airports': 60, 'Airlines': 200}

INT_RANGES = {
    ('Airlines', 'CRS_DEP_TIME'): (0, 2359),
    ('Airlines', 'DEP_TIME'): (0, 2359),
    ('Airlines', 'ARR_TIME'): (0, 2359),
    ('Airlines', 'DEP_DELAY'): (-60, 1500),
    ('Airlines', 'ARR_DELAY'): (-60, 1500),
    ('Airlines', 'CRS_ELAPSED_TIME'): (1, 1500),
    ('Airlines', 'ACTUAL_ELAPSED_TIME'): (1, 1500),
    ('Airlines', 'OP_CARRIER_FL_NUM'): (1, 9999),
    ('Airlines', 'CANCELLED'): (0, 1),
    ('Airlines', 'CARRIER_DELAY'): (0, 1500),
    ('Airlines', 'WEATHER_DELAY'): (0, 1500),
    ('Airlines', 'NAS_DELAY'): (0, 1500),
    ('Airlines', 'SECURITY_DELAY'): (0, 1500),
    ('Airlines', 'LATE_AIRCRAFT_DELAY'): (0, 1500),
    ('Airlines', 'ORIGIN_AIRPORT_ID'): (10000, 16000),
    ('Airlines', 'ORIGIN_AIRPORT_SEQ_ID'): (1000000, 1600000),
    ('Airlines', 'ORIGIN_CITY_MARKET_ID'): (30000, 36000),
    ('Airlines', 'DEST_AIRPORT_ID'): (10000, 16000),
    ('Airlines', 'DEST_AIRPORT_SEQ_ID'): (1000000, 1600000),
    ('Airlines', 'DEST_CITY_MARKET_ID'): (30000, 36000),
    ('Air Carriers', 'Code'): (1, 2 ** 31 - 1),
}

TEXT_DOMAINS = {
    ('Airports', 'Code'): (2, 4, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'),
    ('Airlines', 'ORIGIN'): (2, 4, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
    ('Airlines', 'DEST'): (2, 4, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
    ('Airlines', 'TAIL_NUM'): (3, 8, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'),
    ('Airlines', 'CANCELLATION_CODE'): (1, 1, 'ABC'),
}

DATE_DOMAIN = ('%Y/%m/%d', dt.datetime(2018, 8, 1), dt.datetime(2018, 9, 30), True)

BOUNDARY_TEXT = {
    ('Airports', 'Code'): ['OKC', 'okc', 'DFW', 'dfw', 'SNA', 'sna'],
    ('Airlines', 'ORIGIN'): ['OKC', 'okc', 'DFW', 'dfw', 'CLT', 'clt'],
    ('Airlines', 'DEST'): ['JFK', 'jfk', 'MDW', 'mdw', 'BOS', 'bos'],
    ('Airlines', 'CANCELLATION_CODE'): ['A', 'a'],
}
BOUNDARY_INT = {
    ('Airlines', 'CANCELLED'): [0, 1],
    ('Airlines', 'ARR_DELAY'): [-1, 0, 1],
    ('Airlines', 'DEP_DELAY'): [-1, 0, 1],
}
BOUNDARY_DATE = ['2018/8/25', '2018/8/26', '2018/8/27', '2018/8/28']
LIKE_DATE = ['2018/8/1', '2018/8/2', '2018/9/1', '2018/9/2']

AIRPORT_DESCRIPTIONS = [
    'Chicago, IL: Chicago Midway International',
    'Dallas/Fort Worth, TX: Dallas/Fort Worth International',
    'Oklahoma City, OK: Will Rogers World',
    'Oakland, CA: Metropolitan Oakland International',
    'Fort Lauderdale, FL: Fort Lauderdale-Hollywood International',
    'New York, NY: John F. Kennedy International',
    'Los Angeles, CA: Los Angeles International',
    'San Diego, CA: San Diego International',
    'Austin, TX: Austin - Bergstrom International',
    'Miami, FL: Miami International',
    'Boston, MA: Logan International',
    'Lake Charles, LA: Lake Charles Regional',
    'Bakersfield, CA: Meadows Field',
    'Phoenix, AZ: Phoenix Sky Harbor International',
    'Cleveland, OH: Cleveland-Hopkins International',
    'Detroit, MI: Detroit Metro Wayne County',
    'San Juan, PR: Luis Munoz Marin International',
    'Newark, NJ: Newark Liberty International',
    'Charlotte, NC: Charlotte Douglas International',
    'Philadelphia, PA: Philadelphia International',
]

NULL_SHARE = {
    ('Airlines', 'TAIL_NUM'): 0.003,
    ('Airlines', 'DEP_TIME'): 0.10,
    ('Airlines', 'DEP_DELAY'): 0.10,
    ('Airlines', 'DEP_DELAY_NEW'): 0.10,
    ('Airlines', 'ARR_TIME'): 0.10,
    ('Airlines', 'ARR_DELAY'): 0.10,
    ('Airlines', 'ARR_DELAY_NEW'): 0.10,
    ('Airlines', 'CANCELLATION_CODE'): 0.98,
    ('Airlines', 'ACTUAL_ELAPSED_TIME'): 0.10,
    ('Airlines', 'CARRIER_DELAY'): 0.775,
    ('Airlines', 'WEATHER_DELAY'): 0.775,
    ('Airlines', 'NAS_DELAY'): 0.775,
    ('Airlines', 'SECURITY_DELAY'): 0.775,
    ('Airlines', 'LATE_AIRCRAFT_DELAY'): 0.775,
}

DUPLICATE_COLUMNS = {('Airlines', 'TAIL_NUM'), ('Airlines', 'ORIGIN_AIRPORT_ID')}


def _is_int_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('int', 'number', 'real', 'float', 'double', 'decimal', 'numeric'))


def _is_date_type(t: str) -> bool:
    t = (t or '').lower()
    return 'date' in t or 'timestamp' in t


def build_spec(schema, pool: dict) -> dict:
    """Compile the specification into per-column domains, NULL shares and planted values."""
    cols = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            d = {'type': cm.type_str, 'notnull': cm.notnull, 'pk': cm.pk_pos > 0,
                 'unique': cm.unique, 'domain': None, 'null_share': 0.0,
                 'boundary': [], 'like': [], 'duplicate': False}
            if _is_int_type(cm.type_str):
                d['domain'] = INT_RANGES.get(key)
            elif _is_date_type(cm.type_str):
                d['domain'] = DATE_DOMAIN
            else:
                d['domain'] = TEXT_DOMAINS.get(key)
            if not cm.notnull and cm.pk_pos == 0:
                d['null_share'] = NULL_SHARE.get(key, 0.0)
            d['boundary'] = list(BOUNDARY_TEXT.get(key, [])) + list(BOUNDARY_INT.get(key, []))
            if key == ('Airlines', 'FL_DATE'):
                d['boundary'] = list(BOUNDARY_DATE)
                d['like'] = list(LIKE_DATE)
            if key == ('Airports', 'Description'):
                d['boundary'] = list(AIRPORT_DESCRIPTIONS)
            d['duplicate'] = key in DUPLICATE_COLUMNS
            cols[key] = d
    return {'columns': cols, 'sizes': dict(TABLE_SIZES), 'fks': dict(schema.fks)}


def _planted_values(spec, key, n, rng):
    """Boundary / LIKE-variant / duplicate values planted across distinct rows."""
    d = spec['columns'][key]
    out = []
    for v in d['boundary']:
        out.append(v)
        if isinstance(v, str):
            out.append(v.lower())
            out.append(v.upper())
            out.append(v + ' x')
    for v in d['like']:
        out.append(v)
        out.append(v.lower())
        out.append(v + ' x')
    if d['duplicate'] and n >= 4:
        k = max(1, int(n * rng.uniform(0.2, 0.5)))
        out.extend(out[:k] if out else [])
    return out


def _apply_nulls(values, share, rng, protected=frozenset(), force_one=True):
    """NULL rule: NULL is a value; at least one NULL row per nullable column."""
    n = len(values)
    if n == 0:
        return values
    k = int(round(n * share))
    if force_one and share > 0:
        k = max(1, k)
    k = min(k, n)
    candidates = [i for i in range(n) if i not in protected]
    if not candidates:
        return values
    k = min(k, len(candidates))
    idx = set(rng.sample(candidates, k)) if k else set()
    return [None if i in idx else v for i, v in enumerate(values)]


def _fresh_pk(schema, table, col, n, rng, taken):
    """Sequential/random unique integers (or short codes) fresh against compact rows."""
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == col)
    out = []
    if _is_int_type(cm.type_str):
        lo, hi = INT_RANGES.get((table, col), (1, 2 ** 31 - 1))
        start = rng.randrange(lo, hi + 1)
        step = rng.choice([1, 1, 2, 3])
        v = start
        while len(out) < n:
            if v not in taken:
                out.append(v)
                taken.add(v)
            v += step
            if v > hi:
                v = lo
    else:
        lo, hi, cs = TEXT_DOMAINS.get((table, col), (2, 4, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        while len(out) < n:
            v = ''.join(rng.choice(cs) for _ in range(rng.randint(lo, hi)))
            if v not in taken:
                out.append(v)
                taken.add(v)
    return out


def _derived_delay_new(delay):
    """DEP_DELAY_NEW / ARR_DELAY_NEW: max(delay, 0) (hard constraint)."""
    if delay is None:
        return None
    return delay if delay >= 0 else 0


def generate_rows(schema, spec, pool: dict, rng) -> dict:
    """Sample appended rows for every table in FK order; returns {table: {column: [values]}}."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = {}
    for t in order:
        base = spec['sizes'].get(t, 0)
        sizes[t] = max(0, base + rng.randint(-base // 4, base // 4)) if base else 0

    parent_vals = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            parent_vals[(t, cm.name)] = list(schema.original_values.get((t, cm.name), []))

    out = {}
    for t in order:
        tm = schema.tables[t]
        n = sizes[t]
        cols = {}
        protected = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            d = spec['columns'][key]
            if cm.pk_pos > 0:
                taken = set(parent_vals.get(key, []))
                cols[cm.name] = _fresh_pk(schema, t, cm.name, n, rng, taken)
                continue
            if n == 0:
                cols[cm.name] = []
                continue
            lit = list(pool.get(key, []))
            sampler = _init_sampler(cm, lit, schema.original_values.get(key, []), 0.2, rng,
                                    0, domain=d['domain'])
            vals = [sampler.sample() for _ in range(n)]
            planted = _planted_values(spec, key, n, rng)
            prot = set()
            for i, v in enumerate(planted[:n]):
                vals[i] = v
                if v is not None:
                    prot.add(i)
            if d['null_share'] > 0:
                vals = _apply_nulls(vals, d['null_share'], rng, protected=prot)
            cols[cm.name] = vals
            protected[cm.name] = prot

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = [v for v in parent_vals.get((pt, pc), []) if v is not None]
            if not pv:
                cols[cm.name] = [None] * n
                continue
            vals = [rng.choice(pv) for _ in range(n)]
            if not cm.notnull and cm.pk_pos == 0:
                share = spec['columns'][key]['null_share']
                if share <= 0:
                    share = 0.05
                vals = _apply_nulls(vals, share, rng)
            cols[cm.name] = vals

        _derive(t, cols, protected, rng)

        cols = _dedup(tm, cols)
        out[t] = cols
        for cm in tm.columns:
            parent_vals[(t, cm.name)] = parent_vals.get((t, cm.name), []) + list(cols.get(cm.name, []))
    return out


def _derive(t, cols, protected, rng):
    """Derived / dependent columns computed from the sampled values held in memory."""
    if t != 'Airlines':
        return
    n = len(cols.get('FL_DATE', []))
    if n == 0:
        return
    if 'DEP_DELAY' in cols:
        cols['DEP_DELAY_NEW'] = [_derived_delay_new(v) for v in cols['DEP_DELAY']]
    if 'ARR_DELAY' in cols:
        cols['ARR_DELAY_NEW'] = [_derived_delay_new(v) for v in cols['ARR_DELAY']]

    crs, act = [], []
    prot_act = set()
    for i in range(n):
        a = rng.randint(30, 400)
        u = rng.random()
        if u < 0.2:
            b = a
            prot_act.add(i)
        elif u < 0.4:
            b = max(1, a - 1)
            prot_act.add(i)
        elif u < 0.6:
            b = a + 1
            prot_act.add(i)
        else:
            b = max(1, a + rng.randint(-40, 40))
        crs.append(a)
        act.append(b)
    cols['CRS_ELAPSED_TIME'] = crs
    act = _apply_nulls(act, NULL_SHARE.get(('Airlines', 'ACTUAL_ELAPSED_TIME'), 0.0), rng,
                       protected=prot_act)
    cols['ACTUAL_ELAPSED_TIME'] = act

    cancelled = [1 if rng.random() < 0.02 else 0 for _ in range(n)]
    if n >= 2:
        cancelled[0] = 0
        cancelled[1] = 1
    cols['CANCELLED'] = cancelled

    if 'CANCELLATION_CODE' in cols:
        codes = []
        for c in cancelled:
            if c == 1:
                codes.append(rng.choice(['A', 'B', 'C']))
            else:
                codes.append(None)
        cancelled_idx = [i for i, c in enumerate(cancelled) if c == 1]
        if len(cancelled_idx) >= 1:
            codes[cancelled_idx[0]] = 'A'
        if len(cancelled_idx) >= 2:
            codes[cancelled_idx[1]] = 'a'
        cols['CANCELLATION_CODE'] = codes

    for c in ('CARRIER_DELAY', 'WEATHER_DELAY', 'NAS_DELAY', 'SECURITY_DELAY', 'LATE_AIRCRAFT_DELAY'):
        if c not in cols:
            continue
        vals = []
        for _ in range(n):
            if rng.random() < NULL_SHARE.get(('Airlines', c), 0.775):
                vals.append(None)
            else:
                vals.append(rng.randint(0, 300))
        cols[c] = vals
    if n >= 2 and 'WEATHER_DELAY' in cols:
        cols['WEATHER_DELAY'][0] = 0
        cols['WEATHER_DELAY'][1] = 1


def _dedup(tm, cols):
    """Drop rows repeating the PK tuple or a single unique column value (first kept)."""
    n = len(next(iter(cols.values()))) if cols else 0
    keep = list(range(n))
    if tm.primary_key and all(c in cols for c in tm.primary_key):
        seen, k2 = set(), []
        for i in keep:
            key = tuple(cols[c][i] for c in tm.primary_key)
            if key not in seen:
                seen.add(key)
                k2.append(i)
        keep = k2
    for cm in tm.columns:
        if cm.unique and cm.name in cols:
            seen, k2 = set(), []
            for i in keep:
                v = cols[cm.name][i]
                if v not in seen:
                    seen.add(v)
                    k2.append(i)
            keep = k2
    return {c: [v[i] for i in keep] for c, v in cols.items()}
