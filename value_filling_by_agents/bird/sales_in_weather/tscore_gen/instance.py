"""Random instance construction (fuzz/fuzz.py:83-196), specialised by the specification."""
import re
from .values import _init_sampler

_TABLE_SIZES = {'relation': 45, 'sales_in_weather': 230, 'weather': 230}

_DEFAULT_NULL = {
    'relation.station_nbr': 0.0,
    'sales_in_weather.units': 0.0,
    'weather.tmax': 0.05, 'weather.tmin': 0.05, 'weather.tavg': 0.07,
    'weather.depart': 0.56, 'weather.dewpoint': 0.03, 'weather.wetbulb': 0.06,
    'weather.heat': 0.07, 'weather.cool': 0.07,
    'weather.sunrise': 0.47, 'weather.sunset': 0.47,
    'weather.snowfall': 0.35, 'weather.preciptotal': 0.04,
    'weather.stnpressure': 0.045, 'weather.sealevel': 0.08,
    'weather.resultspeed': 0.03, 'weather.resultdir': 0.03, 'weather.avgspeed': 0.04,
}

_RANGES = {
    'weather.tmax': (-50, 120), 'weather.tmin': (-60, 100), 'weather.tavg': (-50, 110),
    'weather.dewpoint': (-40, 90), 'weather.wetbulb': (-40, 100),
    'weather.heat': (0, 60), 'weather.cool': (0, 60),
    'weather.snowfall': (0.0, 5.0), 'weather.preciptotal': (0.0, 3.0),
    'weather.stnpressure': (25.0, 35.0), 'weather.sealevel': (25.0, 35.0),
    'weather.resultspeed': (0.0, 40.0), 'weather.resultdir': (0, 360),
    'weather.avgspeed': (0.0, 20.0), 'sales_in_weather.units': (0, 200),
}

_BOUNDARY_LITS = {
    'weather.date': ['2011-12-31', '2012-01-01', '2012-01-02', '2012-01-03', '2012-12-31', '2013-01-01',
                     '2014-02-21', '2012-10-01', '2012-01'],
    'sales_in_weather.date': ['2011-12-31', '2012-01-01', '2012-12-31', '2013-01-01',
                              '2012-10-01', '2014-02-01', '2013-06-01'],
    'sales_in_weather.item_nbr': [4, 5, 6, 8, 9, 10],
    'sales_in_weather.store_nbr': [0, 1, 2, 3, 4],
    'relation.store_nbr': [0, 1, 2, 3, 4],
    'relation.station_nbr': [0, 1, 2, 3],
    'weather.station_nbr': [0, 1, 2, 16, 17, 18],
}

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_TIME_RE = re.compile(r'^\d{2}:\d{2}:\d{2}$')


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


def choose_table_sizes(schema, rng) -> dict:
    """Sizes per instance: spec targets with +/-jitter; leafs capped at 230 (tables may be 0)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = _TABLE_SIZES.get(t, 30)
            j = rng.uniform(0.6, 1.2)
            n = int(base * j)
            if rng.random() < 0.06:
                n = 0
            sizes[t] = max(0, min(n, 2500))
    return sizes


def _null_share(schema, t: str, c: str) -> float:
    key = '%s.%s' % (t, c)
    if key in _DEFAULT_NULL:
        return _DEFAULT_NULL[key]
    ov = schema.original_values.get((t, c), [])
    if not ov:
        return 0.0
    return sum(1 for v in ov if v is None) / float(len(ov))


def _column_is_nullable(schema, t: str, c: str) -> bool:
    for cm in schema.tables[t].columns:
        if cm.name == c:
            if cm.notnull or cm.pk_pos > 0:
                return False
            return True
    return False


def _plant_nulls(values: list, share: float, nullable: bool, rng) -> list:
    """Plant NULLs with the given share; guarantee at least one NULL row for nullable columns."""
    n = len(values)
    if not nullable or n == 0:
        return values
    k = int(round(n * share))
    if share > 0 and k == 0:
        k = 1
    if k == 0:
        k = 1
    k = min(k, n)
    positions = set()
    step = max(1, n // max(1, k))
    i = 0
    while len(positions) < k and i < n:
        positions.add(i)
        i += step
    out = list(values)
    for p in sorted(positions):
        out[p] = None
    return out


def _clamp_int(v, lo, hi):
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        x = lo
    return max(lo, min(hi, x))


def _clamp_real(v, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = lo
    x = max(lo, min(hi, x))
    return round(x, 2)


def _adjust_weather_row(vals: dict, rng) -> dict:
    """Apply the semantic formulas of one weather row to non-NULL operands (three-valued logic)."""
    tmin = vals.get('tmin')
    tmax = vals.get('tmax')
    tavg = vals.get('tavg')
    for c, (lo, hi) in _RANGES.items():
        short = c.split('.', 1)[1]
        if short not in vals or vals[short] is None:
            continue
        v = vals[short]
        if short in ('snowfall', 'preciptotal', 'stnpressure', 'sealevel',
                     'resultspeed', 'avgspeed'):
            vals[short] = _clamp_real(v, lo, hi)
        else:
            vals[short] = _clamp_int(v, lo, hi)
    tmin, tmax, tavg = vals.get('tmin'), vals.get('tmax'), vals.get('tavg')
    if tmax is not None and tmin is not None and tmax < tmin:
        tmax, tmin = tmin, tmax
        vals['tmax'], vals['tmin'] = tmax, tmin
    if tavg is not None and tmax is not None and tmin is not None:
        if not (tmin <= tavg <= tmax):
            vals['tavg'] = (tmin + tmax) // 2
    for tc in ('sunrise', 'sunset'):
        v = vals.get(tc)
        if v is None:
            continue
        if not (isinstance(v, str) and _TIME_RE.match(v)):
            vals[tc] = '%02d:%02d:%02d' % (rng.randrange(24), rng.randrange(60), rng.randrange(60))
    dp = vals.get('dewpoint')
    if dp is not None:
        vals['dewpoint'] = _clamp_int(dp, -40, 90)
    wb = vals.get('wetbulb')
    if wb is not None:
        vals['wetbulb'] = _clamp_int(wb, -40, 100)
    return vals


def _inject_boundary_floats(values: list, lo: float, hi: float, rng) -> list:
    """Comparison boundary values -1/0/+1 around the observed literal (sum CASE delta)."""
    if not values:
        return values
    n = len(values)
    for frac in (0.1, 0.5, 0.9):
        i = int(n * frac)
        if i < n and values[i] is not None:
            values[i] = round(lo + 0.01 * (i % 3), 2)
    return values


def _tie_top(values: list, key_name: str, rng, count: int = 2) -> list:
    """Force top-`count` rows to the same maximum value so ORDER BY x DESC LIMIT 1 has a tie."""
    if not values:
        return values
    nonnull = [(i, v) for i, v in enumerate(values) if v is not None]
    if not nonnull:
        return values
    top = max(nonnull, key=lambda t: t[1])[1]
    aligned = 0
    for i, v in nonnull:
        if aligned >= count:
            break
        if v != top:
            values[i] = top
            aligned += 1
    return values


def _unique_units_per_group(store: list, units: list, rng) -> list:
    """Ensure >= 2 distinct units per store group where possible."""
    groups: dict = {}
    for i, s in enumerate(store):
        groups.setdefault(s, []).append(i)
    for s, idxs in groups.items():
        vals = [units[i] for i in idxs if units[i] is not None]
        if len(idxs) >= 2 and len(set(vals)) < 2:
            for j in idxs:
                units[j] = rng.randint(0, 200)
    return units


def _fill_relation(schema, inst: dict, n: int, samplers: dict, rng) -> dict:
    """relation: store_nbr PK sequential; station_nbr nullable FK to weather."""
    stores = [i + 1 for i in range(n)]
    if n >= 4:
        stores[0] = 0
        stores = sorted(set(stores))
    station_pool = _parent_pool(schema, inst, 'weather', 'station_nbr', n * 2, rng,
                                fallback=[0, 1, 2, 3, 16, 17, 18])
    station = [rng.choice(station_pool) if station_pool else None for _ in stores]
    if station and any(v is not None for v in station):
        station[0] = None
    for i in range(len(station)):
        if rng.random() < 0.15:
            station[i] = rng.choice([0, 1, 2, 3, 16, 17, 18])
    return {'store_nbr': stores, 'station_nbr': station}


def _parent_pool(schema, inst: dict, pt: str, pc: str, want: int, rng, fallback=None) -> list:
    """Parent key pool = generated parent keys + compact originals (deduped)."""
    vals = list(inst.get(pt, {}).get(pc, []) or [])
    vals += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals = list(dict.fromkeys(vals))
    if not vals and fallback:
        vals = list(fallback)
    if len(vals) < 2 and fallback:
        vals = list(dict.fromkeys(vals + list(fallback)))
    return vals


def _fill_sales(schema, inst: dict, n: int, samplers: dict, rng, compact_keys: set) -> dict:
    """sales_in_weather: (store_nbr,date,item_nbr) PK; store_nbr FK to relation (unmatched allowed -> wider)."""
    rel_stores = list(inst.get('relation', {}).get('store_nbr', []) or [])
    stores_pool = _parent_pool(schema, inst, 'relation', 'store_nbr', n, rng,
                               fallback=[0, 1, 2, 3, 4])
    dates = [samplers['date'].sample() for _ in range(n)]
    for d in _BOUNDARY_LITS['sales_in_weather.date']:
        if rng.random() < 0.3:
            dates.append(d)
    while len(dates) < n:
        dates.append(samplers['date'].sample())
    dates = dates[:n]
    item_pool = list(_BOUNDARY_LITS['sales_in_weather.item_nbr']) + [i + 1 for i in range(37)]
    items = [rng.choice(item_pool) for _ in range(n)]
    stores = []
    for i in range(n):
        if rng.random() < 0.06:
            stores.append(rng.choice([0, 500, 501, 999]))
        else:
            stores.append(rng.choice(stores_pool) if stores_pool else rng.randint(1, 45))
    units = [samplers['units'].sample() for _ in range(n)]
    units = [None if u is None else max(0, int(u)) for u in units]
    units = _unique_units_per_group(stores, units, rng)
    units = _plant_nulls(units, _null_share(schema, 'sales_in_weather', 'units'),
                         _column_is_nullable(schema, 'sales_in_weather', 'units'), rng)
    return {'date': dates, 'store_nbr': stores, 'item_nbr': items, 'units': units}


def _fill_weather(schema, inst: dict, n: int, samplers: dict, rng, compact_keys: set) -> dict:
    """weather: (station_nbr,date) PK; station pool includes childless parent keys 0,16..18,19."""
    station_pool = list(range(0, 21))
    dates = [samplers['date'].sample() for _ in range(n)]
    for d in _BOUNDARY_LITS['weather.date']:
        if rng.random() < 0.35:
            dates.append(d)
    while len(dates) < n:
        dates.append(samplers['date'].sample())
    dates = dates[:n]
    station = [rng.choice(station_pool) for _ in range(n)]
    if station and rng.random() < 0.5:
        station[0] = 17

    cols: dict = {}
    for c in ('tmax', 'tmin', 'tavg', 'depart', 'dewpoint', 'wetbulb', 'heat', 'cool',
              'snowfall', 'preciptotal', 'stnpressure', 'sealevel', 'resultspeed',
              'resultdir', 'avgspeed'):
        vals = [samplers[c].sample() for _ in range(n)]
        if c in _RANGES:
            lo, hi = _RANGES[c]
            if isinstance(lo, float):
                vals = [None if v is None else _clamp_real(v, lo, hi) for v in vals]
            else:
                vals = [None if v is None else _clamp_int(v, lo, hi) for v in vals]
        cols[c] = vals
    sunrise = [samplers['sunrise'].sample() for _ in range(n)]
    sunset = [samplers['sunset'].sample() for _ in range(n)]
    codesum = [samplers['codesum'].sample() for _ in range(n)]

    for c in list(cols.keys()) + ['sunrise', 'sunset', 'codesum']:
        share = _null_share(schema, 'weather', c)
        nullable = _column_is_nullable(schema, 'weather', c)
        if c in cols:
            cols[c] = _plant_nulls(cols[c], share, nullable, rng)
    sunrise = _plant_nulls(sunrise, _null_share(schema, 'weather', 'sunrise'),
                           _column_is_nullable(schema, 'weather', 'sunrise'), rng)
    sunset = _plant_nulls(sunset, _null_share(schema, 'weather', 'sunset'),
                          _column_is_nullable(schema, 'weather', 'sunset'), rng)
    codesum = _plant_nulls(codesum, _null_share(schema, 'weather', 'codesum'),
                           _column_is_nullable(schema, 'weather', 'codesum'), rng)

    cols['tmax'] = _tie_top(cols['tmax'], 'tmax', rng, 2)
    cols['tmin'] = _tie_top(cols['tmin'], 'tmin', rng, 2)
    cols['stnpressure'] = _tie_top(cols['stnpressure'], 'stnpressure', rng, 2)
    cols['avgspeed'] = _inject_boundary_floats(cols['avgspeed'], 0.0, 20.0, rng)
    if n > 0:
        cols['avgspeed'][0] = round(rng.uniform(0, 1), 2)

    out_rows = []
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        row['sunrise'] = sunrise[i]
        row['sunset'] = sunset[i]
        row['codesum'] = codesum[i]
        row = _adjust_weather_row(row, rng)
        out_rows.append(row)
    result = {c: [r[c] for r in out_rows] for c in ('tmax', 'tmin', 'tavg', 'depart', 'dewpoint',
                                                    'wetbulb', 'heat', 'cool', 'sunrise', 'sunset',
                                                    'codesum', 'snowfall', 'preciptotal', 'stnpressure',
                                                    'sealevel', 'resultspeed', 'resultdir', 'avgspeed')}
    result['station_nbr'] = station
    result['date'] = dates
    return result


def _compact_keys(schema, rng) -> dict:
    """Set of PK tuples per table from compact originals, so generated keys stay fresh."""
    out = {}
    for t, tm in schema.tables.items():
        if not tm.primary_key:
            out[t] = set()
            continue
        cols = [schema.original_values.get((t, c), []) for c in tm.primary_key]
        if not cols or not all(cols):
            out[t] = set()
            continue
        n = min(len(c) for c in cols)
        out[t] = {tuple(cols[j][i] for j in range(len(cols))) for i in range(n)}
    return out


def _dedup_against_compact(schema, t: str, columns: dict, compact_keys: set) -> dict:
    """Remove rows whose PK tuple equals a compact row's PK (keys stay fresh)."""
    tm = schema.tables[t]
    if not tm.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in tm.primary_key)
        if k in compact_keys:
            continue
        keep.append(i)
    return _filter(columns, keep)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            lit = list(literal_pool.get((t, cm.name), []))
            for src_t, src_c in ((t, cm.name),):
                key = '%s.%s' % (src_t, src_c)
                if key in _BOUNDARY_LITS:
                    lit += [str(v) for v in _BOUNDARY_LITS[key]]
            samplers[(t, cm.name)] = _init_sampler(cm, lit,
                                                   schema.original_values.get((t, cm.name), []), p, rng,
                                                   len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    compact_keys = _compact_keys(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if t == 'relation':
            cols = _fill_relation(schema, inst, n, samplers, rng)
        elif t == 'sales_in_weather':
            cols = _fill_sales(schema, inst, n, {c: samplers[(t, c)] for c in
                                ('date', 'item_nbr', 'units')}, rng, compact_keys.get(t, set()))
        elif t == 'weather':
            cols = _fill_weather(schema, inst, n, {c: samplers[(t, c)] for c in
                                ('date', 'tmax', 'tmin', 'tavg', 'depart', 'dewpoint', 'wetbulb',
                                 'heat', 'cool', 'sunrise', 'sunset', 'codesum', 'snowfall',
                                 'preciptotal', 'stnpressure', 'sealevel', 'resultspeed',
                                 'resultdir', 'avgspeed')}, rng, compact_keys.get(t, set()))
        else:
            cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                    for cm in tm.columns if (t, cm.name) in samplers}
            fk_cols = _fill_generic_fks(schema, inst, t, n, rng)
            cols.update(fk_cols)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        cols = _dedup_against_compact(schema, t, cols, compact_keys.get(t, set()))
        inst[t] = cols
    return {t: inst.get(t, {}) for t in schema.tables}


def _fill_generic_fks(schema, inst: dict, t: str, n: int, rng) -> dict:
    """Generic FK fill: draw from parent pool; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[t].columns:
        key = (t, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(schema, inst, pt, pc, n, rng)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out
