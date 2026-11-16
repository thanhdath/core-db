"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven samplers."""
import datetime as dt

from .values import _init_sampler

TABLE_SIZES = {'station': 70, 'status': 2000, 'trip': 2000, 'weather': 366}

CITY_ENUM = ['San Jose', 'Redwood City', 'Mountain View', 'Palo Alto', 'San Francisco', 'Mountain']
SUBSCRIPTION_ENUM = ['Subscriber', 'Customer']
EVENTS_ENUM = ['', 'Fog', 'Rain', 'Fog-Rain', 'rain', 'Rain-Thunderstorm']
WEATHER_ZIP_ENUM = ['94106', '94107', '94108', '94063', '94301', '94041', '95113']

BOUNDARY_STR = {
    ('station', 'name'): ['Adobe on Almaden', 'adobe on almaden', 'Santa Clara at Almaden',
                          'santa clara at almaden', 'Ryland Park', 'ryland park'],
    ('trip', 'start_station_name'): ['Market at 4th', 'market at 4th', 'Adobe on Almaden',
                                     'adobe on almaden', 'Santa Clara at Almaden', 'santa clara at almaden'],
    ('trip', 'end_station_name'): ['Ryland Park', 'ryland park', '2nd at South Park', '2nd at south park',
                                   'California Ave Caltrain Station', 'california ave caltrain station'],
    ('station', 'city'): ['San Francisco', 'san francisco', 'Mountain View', 'mountain view', 'Mountain', 'mountain'],
    ('trip', 'subscription_type'): ['Subscriber', 'subscriber', 'Customer', 'customer'],
}
BOUNDARY_DATE = {
    ('station', 'installation_date'): ['12/31/2013', '12/31/2014'],
    ('weather', 'date'): ['8/29/2013', '8/29/2014'],
}
BOUNDARY_NUM = {
    ('weather', 'max_temperature_f'): [79, 80, 81],
}
BOUNDARY_TEXT_NUM = {
    ('weather', 'zip_code'): ['94106', '94107', '94108'],
}
LIKE_VARIANTS = {
    ('station', 'installation_date'): ['%2014%', '%2014', '2014', '2015', '2014 x', 'x 2014'],
    ('trip', 'start_date'): ['8/29/2013%', '%2006%', '%2013%', '8%', '8/%/2013%', '%/%/2013%',
                             '8/29/2013', '8/29/2014', '8/29/2013 x', '2006', '2007', '2006 x'],
    ('trip', 'end_date'): ['8/29/2013%', '8/2%', '%2006%', '2006%', '8/29/2013', '8/29/2014',
                           '8/29/2013 x', '8/2', '8/3', '8/2 x'],
    ('weather', 'date'): ['%2013%', '%/2013%', '2013', '2014', '2013 x', '/2013', '/2014', '/2013 x'],
}
NULL_TARGETS = {
    ('trip', 'subscription_type'), ('trip', 'duration'), ('trip', 'start_station_id'),
    ('trip', 'end_station_id'), ('trip', 'zip_code'),
    ('weather', 'max_temperature_f'), ('weather', 'mean_temperature_f'), ('weather', 'min_temperature_f'),
    ('weather', 'max_dew_point_f'), ('weather', 'mean_dew_point_f'), ('weather', 'min_dew_point_f'),
    ('weather', 'max_humidity'), ('weather', 'mean_humidity'), ('weather', 'min_humidity'),
    ('weather', 'max_visibility_miles'), ('weather', 'mean_visibility_miles'), ('weather', 'min_visibility_miles'),
    ('weather', 'max_gust_speed_mph'),
}
TIE_TARGETS = {
    ('station', 'name'), ('trip', 'start_station_name'), ('station', 'id'), ('trip', 'start_station_id'),
    ('station', 'city'), ('station', 'installation_date'), ('weather', 'max_temperature_f'),
}
DUP_TARGETS = {('station', 'name'), ('trip', 'start_station_name'), ('station', 'city'),
               ('station', 'installation_date')}

NUM_RANGE = {
    ('station', 'dock_count'): (0, 40),
    ('station', 'lat'): (37.0, 38.0),
    ('station', 'long'): (-122.5, -121.5),
    ('trip', 'duration'): (1, 3600),
    ('weather', 'max_temperature_f'): (-10, 110),
    ('weather', 'mean_temperature_f'): (-10, 110),
    ('weather', 'min_temperature_f'): (-10, 110),
    ('weather', 'max_humidity'): (0, 100),
    ('weather', 'mean_humidity'): (0, 100),
    ('weather', 'min_humidity'): (0, 100),
    ('weather', 'cloud_cover'): (0, 8),
    ('weather', 'wind_dir_degrees'): (0, 360),
}
DATE_RANGE = {
    ('station', 'installation_date'): (dt.date(2013, 8, 1), dt.date(2014, 12, 31)),
    ('weather', 'date'): (dt.date(2013, 8, 29), dt.date(2015, 9, 5)),
    ('trip', 'start_date'): (dt.date(2013, 8, 29), dt.date(2015, 9, 5)),
    ('trip', 'end_date'): (dt.date(2013, 8, 29), dt.date(2015, 9, 5)),
}
DATE_FMT = {
    ('station', 'installation_date'): '%m/%d/%Y',
    ('weather', 'date'): '%m/%d/%Y',
    ('trip', 'start_date'): '%m/%d/%Y %H:%M',
    ('trip', 'end_date'): '%m/%d/%Y %H:%M',
}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _case_variant(rng, s: str) -> str:
    u = rng.random()
    if u < 0.5:
        return s.lower()
    if u < 0.8:
        return s.upper()
    return s.title()


def _near_variant(rng, s: str) -> str:
    u = rng.random()
    if u < 0.4:
        return s + ' '
    if u < 0.7:
        return ' ' + s
    return _case_variant(rng, s)


def _parse_dt(s: str, fmt: str):
    try:
        return dt.datetime.strptime(str(s).strip(), fmt)
    except (ValueError, TypeError):
        return None


def _fmt_dt(d: dt.datetime, fmt: str) -> str:
    return d.strftime(fmt)


def _rand_date(rng, lo: dt.date, hi: dt.date) -> dt.date:
    span = (hi - lo).days
    return lo + dt.timedelta(days=rng.randint(0, max(0, span)))


def _rand_datetime(rng, lo: dt.date, hi: dt.date) -> dt.datetime:
    d = _rand_date(rng, lo, hi)
    return dt.datetime(d.year, d.month, d.day, rng.randrange(24), rng.randrange(60))


def _is_date_col(key) -> bool:
    return key in DATE_FMT


def _is_num_col(key) -> bool:
    return key in NUM_RANGE


def _declared_is_int(column) -> bool:
    t = (column.type_str or '').lower()
    return 'int' in t


def _column_pool(schema, literal_pool: dict, key) -> list:
    """Observed values + pool literals + boundary/like literals for a column."""
    vals = []
    seen = set()

    def add(v):
        if v is None:
            return
        sv = str(v)
        if sv not in seen:
            seen.add(sv)
            vals.append(v)

    for v in schema.original_values.get(key, []):
        add(v)
    for v in literal_pool.get(key, []):
        add(v)
    for v in BOUNDARY_STR.get(key, []):
        add(v)
    for v in BOUNDARY_DATE.get(key, []):
        add(v)
    for v in BOUNDARY_NUM.get(key, []):
        add(v)
    for v in BOUNDARY_TEXT_NUM.get(key, []):
        add(v)
    for v in LIKE_VARIANTS.get(key, []):
        if '%' not in v:
            add(v)
    return vals


class SpecSampler:
    """A sampler that implements the specification for one column by construction."""

    def __init__(self, schema, table, column, literal_pool, rng, n_pk):
        self.schema = schema
        self.table = table
        self.column = column
        self.key = (table, column.name)
        self.rng = rng
        self.n_pk = n_pk
        self.pool = _column_pool(schema, literal_pool, self.key)
        self.base = _init_sampler(column, literal_pool.get(self.key, []),
                                  schema.original_values.get(self.key, []), 0.2, rng, n_pk)
        self.is_date = _is_date_col(self.key)
        self.is_num = _is_num_col(self.key)
        self.is_int = _declared_is_int(column)
        self.fmt = DATE_FMT.get(self.key)
        self.range = NUM_RANGE.get(self.key)
        self.date_range = DATE_RANGE.get(self.key)
        self.enum = None
        if self.key == ('station', 'city'):
            self.enum = CITY_ENUM
        elif self.key == ('trip', 'subscription_type'):
            self.enum = SUBSCRIPTION_ENUM
        elif self.key == ('weather', 'events'):
            self.enum = EVENTS_ENUM
        elif self.key == ('weather', 'zip_code'):
            self.enum = WEATHER_ZIP_ENUM
        self.boundary = (BOUNDARY_STR.get(self.key) or BOUNDARY_DATE.get(self.key)
                         or BOUNDARY_NUM.get(self.key) or BOUNDARY_TEXT_NUM.get(self.key) or [])
        self.like_variants = LIKE_VARIANTS.get(self.key, [])
        self._boundary_idx = 0
        self._like_idx = 0

    def _draw_enum(self):
        r = self.rng
        v = r.choice(self.enum)
        if r.random() < 0.1:
            v = _case_variant(r, v)
        return v

    def _draw_num(self):
        r = self.rng
        lo, hi = self.range
        if isinstance(lo, int) and isinstance(hi, int):
            return r.randint(lo, hi)
        return round(r.uniform(lo, hi), 2)

    def _draw_date(self):
        r = self.rng
        lo, hi = self.date_range
        if self.fmt and '%H' in self.fmt:
            d = _rand_datetime(r, lo, hi)
        else:
            d = dt.datetime.combine(_rand_date(r, lo, hi), dt.time())
        s = _fmt_dt(d, self.fmt)
        if r.random() < 0.1:
            try:
                d2 = d.replace(year=d.year + r.choice([-1, 1]))
                s = _fmt_dt(d2, self.fmt)
            except ValueError:
                pass
        return s

    def _draw_pool(self):
        r = self.rng
        if self.pool and r.random() < 0.6:
            v = r.choice(self.pool)
            if isinstance(v, str) and r.random() < 0.15:
                v = _case_variant(r, v)
            return v
        return None

    def _draw_base(self):
        return self.base.sample()

    def sample(self):
        if self.enum is not None:
            return self._draw_enum()
        if self.is_num:
            return self._draw_num()
        if self.is_date:
            return self._draw_date()
        v = self._draw_pool()
        if v is not None:
            return v
        return self._draw_base()

    def sample_boundary(self):
        """Cycle through boundary literals (literal, one step below, one step above)."""
        if not self.boundary:
            return self.sample()
        r = self.rng
        lit = self.boundary[self._boundary_idx % len(self.boundary)]
        self._boundary_idx += 1
        step = self._boundary_idx % 3
        if self.is_num and self.is_int:
            try:
                n = int(lit)
            except (TypeError, ValueError):
                return self._draw_num()
            return int(n + (step - 1))
        if self.is_num:
            try:
                f = float(lit)
            except (TypeError, ValueError):
                return self._draw_num()
            return round(f + (step - 1), 2)
        if self.is_date:
            d = _parse_dt(lit, self.fmt)
            if d is None:
                return lit
            d2 = d + dt.timedelta(days=(step - 1))
            return _fmt_dt(d2, self.fmt)
        if step == 0:
            return lit
        return _case_variant(r, lit)

    def sample_like_variant(self):
        if not self.like_variants:
            return self.sample()
        lit = self.like_variants[self._like_idx % len(self.like_variants)]
        self._like_idx += 1
        if '%' in lit:
            return lit.replace('%', '')
        return lit


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes with modest per-instance variation; never 0 rows."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 30)
        factor = rng.choice([1, 1, 1, 2])
        sizes[t] = max(1, base * factor)
    return sizes


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values; nullable FKs get NULL w.p."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        nullable = (not cm.notnull) and cm.pk_pos == 0
        vals = []
        for _ in range(n):
            if nullable and rng.random() < 0.05:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if n > 0:
            if nullable:
                vals[rng.randrange(n)] = None
            else:
                nums = [v for v in pv if isinstance(v, int)]
                if nums:
                    vals[rng.randrange(n)] = max(nums) + 1
        out[cm.name] = vals
    return out


def _compact_null_share(schema, key) -> float:
    vals = schema.original_values.get(key, [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / len(vals)


def _apply_null_rule(columns: dict, table: str, schema, rng) -> dict:
    """For every nullable column, plant NULLs following the compact share (>=1 NULL row)."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.name not in columns:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        key = (table, cm.name)
        share = _compact_null_share(schema, key)
        if key in NULL_TARGETS:
            share = max(share, 0.05)
        if share <= 0.0 and key not in NULL_TARGETS:
            continue
        k = max(1, int(n * share))
        idxs = rng.sample(range(n), min(k, n))
        for i in idxs:
            columns[cm.name][i] = None
    return columns


def _plant_boundary(columns: dict, table: str, samplers: dict, rng) -> None:
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return
    for (t, c), sampler in samplers.items():
        if t != table:
            continue
        if not sampler.boundary and not sampler.like_variants:
            continue
        if c not in columns:
            continue
        k = min(n, max(3, len(sampler.boundary) * 3 if sampler.boundary else 3))
        idxs = rng.sample(range(n), k)
        for i in idxs:
            if sampler.boundary:
                columns[c][i] = sampler.sample_boundary()
            else:
                columns[c][i] = sampler.sample_like_variant()


def _plant_ties(columns: dict, table: str, rng) -> None:
    n = len(next(iter(columns.values()))) if columns else 0
    if n < 2:
        return
    for (t, c) in TIE_TARGETS:
        if t != table or c not in columns:
            continue
        i, j = rng.sample(range(n), 2)
        columns[c][j] = columns[c][i]


def _plant_duplicates(columns: dict, table: str, rng) -> None:
    n = len(next(iter(columns.values()))) if columns else 0
    if n < 2:
        return
    for (t, c) in DUP_TARGETS:
        if t != table or c not in columns:
            continue
        i, j = rng.sample(range(n), 2)
        columns[c][j] = columns[c][i]


def _apply_derived(instance: dict, table: str, columns: dict, schema, rng) -> None:
    """Compute dependent columns in Python from sampled values held in memory."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return
    if table == 'trip':
        station = instance.get('station', {})
        sids = station.get('id', [])
        snames = station.get('name', [])
        id2name = {sid: snames[i] for i, sid in enumerate(sids) if i < len(snames)}
        for fk_col, name_col in (('start_station_id', 'start_station_name'),
                                 ('end_station_id', 'end_station_name')):
            if fk_col not in columns or name_col not in columns:
                continue
            for i in range(n):
                sid = columns[fk_col][i]
                if sid is None:
                    columns[name_col][i] = None
                    continue
                nm = id2name.get(sid)
                if nm is not None:
                    columns[name_col][i] = nm
        if 'start_date' in columns and 'end_date' in columns:
            fmt = DATE_FMT[('trip', 'start_date')]
            for i in range(n):
                sd = columns['start_date'][i]
                ed = columns['end_date'][i]
                if sd is None or ed is None:
                    continue
                sdt = _parse_dt(sd, fmt)
                edt = _parse_dt(ed, fmt)
                if sdt is None or edt is None:
                    continue
                if edt < sdt:
                    delta = dt.timedelta(minutes=rng.randint(1, 120))
                    columns['end_date'][i] = _fmt_dt(sdt + delta, fmt)
        if 'duration' in columns:
            for i in range(n):
                v = columns['duration'][i]
                if v is None:
                    continue
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    iv = 1
                if iv <= 0:
                    columns['duration'][i] = rng.randint(1, 3600)
    if table == 'weather':
        for i in range(n):
            mx = columns.get('max_temperature_f', [None] * n)[i]
            mn = columns.get('min_temperature_f', [None] * n)[i]
            me = columns.get('mean_temperature_f', [None] * n)[i]
            if mx is not None and mn is not None and mx < mn:
                columns['max_temperature_f'][i], columns['min_temperature_f'][i] = mn, mx
                mx, mn = mn, mx
            if me is not None and mx is not None and mn is not None:
                if me > mx:
                    columns['mean_temperature_f'][i] = mx
                elif me < mn:
                    columns['mean_temperature_f'][i] = mn
        for i in range(n):
            mx = columns.get('max_humidity', [None] * n)[i]
            mn = columns.get('min_humidity', [None] * n)[i]
            me = columns.get('mean_humidity', [None] * n)[i]
            if mx is not None and mn is not None and mx < mn:
                columns['max_humidity'][i], columns['min_humidity'][i] = mn, mx
                mx, mn = mn, mx
            if me is not None and mx is not None and mn is not None:
                if me > mx:
                    columns['mean_humidity'][i] = mx
                elif me < mn:
                    columns['mean_humidity'][i] = mn
    if table == 'status':
        station = instance.get('station', {})
        sids = station.get('id', [])
        docks = station.get('dock_count', [])
        id2dock = {sid: docks[i] for i, sid in enumerate(sids) if i < len(docks)}
        for i in range(n):
            sid = columns.get('station_id', [None] * n)[i]
            if sid is None:
                continue
            dc = id2dock.get(sid)
            if dc is None:
                continue
            b = columns.get('bikes_available', [None] * n)[i]
            d = columns.get('docks_available', [None] * n)[i]
            if b is None or d is None:
                continue
            if b + d > dc:
                if b > dc:
                    b = dc
                columns['bikes_available'][i] = b
                columns['docks_available'][i] = max(0, dc - b)


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


def _fresh_pk_start(schema, table: str, column: str) -> int:
    """First PK value above every compact key so generated keys never collide."""
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification-driven samplers."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = SpecSampler(schema, t, cm, literal_pool, rng, len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        _plant_boundary(cols, t, samplers, rng)
        _plant_ties(cols, t, rng)
        _plant_duplicates(cols, t, rng)
        _apply_derived(inst, t, cols, schema, rng)
        _apply_null_rule(cols, t, schema, rng)
        if t == 'trip':
            station = inst.get('station', {})
            sids = station.get('id', [])
            snames = station.get('name', [])
            id2name = {sid: snames[i] for i, sid in enumerate(sids) if i < len(snames)}
            for fk_col, name_col in (('start_station_id', 'start_station_name'),
                                     ('end_station_id', 'end_station_name')):
                if fk_col in cols and name_col in cols:
                    for i in range(n):
                        sid = cols[fk_col][i]
                        if sid is None:
                            cols[name_col][i] = None
                        else:
                            nm = id2name.get(sid)
                            if nm is not None:
                                cols[name_col][i] = nm
        for pk in tm.primary_key:
            if pk in cols and _declared_is_int(next(c for c in tm.columns if c.name == pk)):
                start = _fresh_pk_start(schema, t, pk)
                cols[pk] = [start + i for i in range(n)]
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
