"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
_INT64_MIN = -(2 ** 63)
_INT64_MAX = 2 ** 63 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

INT64_COLUMNS = {
    ('events', 'device_id'), ('events_relevant', 'device_id'),
    ('gender_age', 'device_id'), ('gender_age_train', 'device_id'),
    ('gender_age_test', 'device_id'), ('phone_brand_device_model2', 'device_id'),
    ('sample_submission', 'device_id'),
}

GROUP_ENUM = ['F23-', 'F24-26', 'F27-28', 'F29-32', 'F33-42', 'F43+',
              'M22-', 'M23-26', 'M27-28', 'M29-31', 'M32-38', 'M39+']
GENDER_ENUM = ['M', 'F']
BRAND_POOL = ['小米', 'vivo', '三星', 'OPPO', '金立', '魅族', '酷派', '华为', 'HTC', 'ZUK', '联想', '中兴']
MODEL_POOL = ['红米note', 'Y19T', 'MI 3', 'Galaxy Note 2', 'A31', 'ELIFE E7 Mini', 'MX3', '8730L',
              'Z1', 'M8 Ey', 'One M8 Eye', 'ZenFone 5', 'A51', 'Xplay3S', '中兴', '中兴x']
CATEGORY_POOL = ['game-game type', 'game-Game themes', 'game-Art Style', 'game-Leisure time',
                 'game-Cutting things', 'game-Finding fault', 'game-stress reliever', 'game-pet',
                 'Securities', 'Finance', 'Home Decoration', 'science fiction',
                 '80s Japanese comic', '90s Japanese comic']
PROB_COLS = ['F23-', 'F24-26', 'F27-28', 'F29-32', 'F33-42', 'F43+',
             'M22-', 'M23-26', 'M27-28', 'M29-31', 'M32-38', 'M39+']

BOUNDARY = {
    ('gender_age', 'age'): [19, 20, 21, 22, 23, 24],
    ('gender_age', 'gender'): ['F', 'f', 'M', 'm'],
    ('gender_age', 'group'): ['F23-', 'f23-', 'F27-28', 'f27-28', 'M27-28', 'm27-28'],
    ('gender_age_train', 'age'): [19, 20, 21, 29, 30, 31],
    ('gender_age_train', 'gender'): ['F', 'f', 'M', 'm'],
    ('events', 'event_id'): [1, 2, 3, 5, 6, 7],
    ('events', 'device_id'): [3915082290673129983, 3915082290673129984, 3915082290673129985,
                              4069764298338760191, 4069764298338760192, 4069764298338760193],
    ('events_relevant', 'event_id'): [1, 2, 3, 154, 155, 156],
    ('events_relevant', 'device_id'): [3915082290673129983, 3915082290673129984, 3915082290673129985,
                                       4069764298338760191, 4069764298338760192, 4069764298338760193],
    ('app_events', 'event_id'): [1, 2, 3, 154, 155, 156],
    ('app_events', 'is_active'): [-1, 0, 1, 2],
    ('app_events', 'is_installed'): [0, 1, 2],
    ('app_events_relevant', 'is_active'): [-1, 0, 1],
    ('phone_brand_device_model2', 'device_model'): ['Z1', 'z1', '中兴', '中兴x', 'M8 Ey', 'm8 ey'],
    ('phone_brand_device_model2', 'phone_brand'): ['vivo', 'VIVO', 'HTC', 'htc', 'ZUK', 'zuk'],
    ('label_categories', 'category'): ['Securities', 'securities', 'Finance', 'finance',
                                       'Home Decoration', 'home decoration'],
}
BOUNDARY_DT = {
    ('events', 'timestamp'): ['2015-12-31 00:00:00.0', '2016-01-01 00:00:00.0',
                              '2016-12-31 00:00:00.0', '2017-01-01 00:00:00.0'],
}
NEAR_VARIANTS = {
    ('gender_age', 'group'): ['F24-', 'F23- x', 'f23-'],
    ('events', 'timestamp'): ['2015-12-31 00:00:00.0', '2016-01-01 00:00:00.0', '2016-12-31 00:00:00.0',
                               '2017-01-01 00:00:00.0', '2016-05-03 00:00:00.0', '2016-05-04 00:00:00.0',
                               '2016-05-05 00:00:00.0'],
    ('label_categories', 'category'): ['game', 'gamf', 'game x', 'GAME', '', 'x', ' x'],
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _case_variants(s: str) -> list:
    out = {s, s.lower(), s.upper(), s.capitalize()}
    return [x for x in out if x != s]


def _str_variants(s: str) -> list:
    """prefix / suffix / dropped-character variants (no '%')."""
    out = set()
    if not s:
        return []
    out.add(s + 'x')
    out.add('x' + s)
    out.add(s[:-1])
    out.add(s[1:])
    out.add(s + ' x')
    return [x for x in out if x != s]


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def sample(self):
        raise NotImplementedError


class NumberSampler(ColumnSampler):
    """fuzz/number.py; keeps the list_max overwrite quirk (number.py:60,67)."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi_lim = min(10 ** scale, _MAX)
        if lo is not None or hi is not None:
            self.min = lo if lo is not None else -hi_lim
            self.max = hi if hi is not None else hi_lim
        else:
            self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi_lim, hi_lim)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = max(self.elements) if self.elements else self.max
        if self.list_max > self.max:
            self.list_max = self.max
        if self.list_min < self.min:
            self.list_min = self.min

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            if lo > hi:
                lo, hi = hi, lo
            v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)) if self.is_int else r.uniform(lo, hi))
        else:
            v = r.choice(self.elements)
        d = 1 if self.is_int else 0.01
        if r.random() < 1 / 6:
            v += d
        elif r.random() < 1 / 5:
            v -= d
        elif r.random() < 1 / 4:
            v += 2 * d
        elif r.random() < 1 / 3:
            v -= 2 * d
        return self._cast(v)


class Int64Sampler(ColumnSampler):
    """64-bit integer column: draw from the observed pool + boundary literals, no 32-bit clamp."""

    def __init__(self, elements, boundary, p, max_l0, rng):
        els = [int(e) for e in elements if isinstance(e, (int, float)) and _is_int64(e)]
        els += [int(b) for b in boundary if isinstance(b, (int, float))]
        super().__init__(els, p, max_l0, rng)
        self.boundary = [int(b) for b in boundary if isinstance(b, (int, float))]
        if not self.boundary:
            self.boundary = [0, 1, -1]
        self.lo = min(self.boundary) - 2
        self.hi = max(self.boundary) + 2
        if self.lo < _INT64_MIN:
            self.lo = _INT64_MIN
        if self.hi > _INT64_MAX:
            self.hi = _INT64_MAX

    def _draw(self):
        r = self.rng
        b = r.choice(self.boundary)
        step = r.choice([-2, -1, 0, 1, 2])
        v = b + step
        if v < _INT64_MIN:
            v = _INT64_MIN
        if v > _INT64_MAX:
            v = _INT64_MAX
        return v

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


def _is_int64(v) -> bool:
    try:
        return _INT64_MIN <= int(v) <= _INT64_MAX
    except (TypeError, ValueError):
        return False


class StringSampler(ColumnSampler):
    """fuzz/string.py (allow_none dropped)."""

    def __init__(self, elements, p, max_l0, rng, length=20):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(lambda: self._rand(r.randint(self.lo, self.hi)))
        else:
            v = r.choice(self.elements)
        if r.random() < 0.5:
            u = r.random()
            if u < 0.2:
                v = v + self._rand(5)
            elif u < 0.4:
                v = self._rand(5) + v
            elif u < 0.6:
                v = self._rand(3) + v + self._rand(3)
            elif u < 0.8:
                v = v[:-1]
            else:
                v = v[1:]
        return v


class EnumSampler(ColumnSampler):
    """Explicit enum pool (specification semantic rules); boundary + near variants included."""

    def __init__(self, pool: list, p: float, max_l0: float, rng, boundary: list = (), near: list = ()):
        els = list(dict.fromkeys([str(x) for x in pool]))
        for b in boundary:
            els.append(str(b))
        for n in near:
            els.append(str(n))
        super().__init__(els, p, max_l0, rng)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            return self._fresh_or_reuse(lambda: r.choice(self.elements))
        return r.choice(self.elements)


class BoundaryNumberSampler(NumberSampler):
    """Number sampler whose element pool is the boundary literal set (literal, +-1, +-2)."""

    def __init__(self, boundary: list, p, max_l0, rng, lo=None, hi=None):
        els = []
        for b in boundary:
            els += [b, b - 1, b + 1, b - 2, b + 2]
        super().__init__(els, p, max_l0, rng, is_int=True, lo=lo, hi=hi)


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class DateSampler(ColumnSampler):
    """fuzz/date.py + utils/data_parser.py (an ELEMENT is returned w.p. p)."""

    def __init__(self, elements, p, max_l0, rng):
        super().__init__(elements, p, max_l0, rng)
        self.p = p
        self.as_int = bool(self.elements) and all(isinstance(e, int) for e in self.elements)
        strs = [str(e) for e in self.elements]
        self.template, parsed = None, []
        for s in strs:
            t, d = _parse_date(s)
            if d is not None:
                self.template = self.template or t
                parsed.append(d)
        self.template = self.template or '%Y-%m-%d'
        self.full = (dt.datetime(1800, 1, 1), dt.datetime(2100, 1, 1))
        self.rng_dates = (min(parsed), max(parsed)) if len(set(parsed)) >= 2 else self.full
        self.n_parsed = len(set(parsed))
        self.strip0 = not any(s.startswith('0') or '-0' in s for s in strs)

    def _draw(self):
        r = self.rng
        lo, hi = self.full if (r.random() < self.p or self.n_parsed <= 1) else self.rng_dates
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        s = d.strftime(self.template)
        if self.strip0:
            s = re.sub(r'(^|[-/ :])0(\d)', r'\1\2', s)
        return int(s) if self.as_int and s.isdigit() else s

    def sample(self):
        if self.elements and self.rng.random() < self.p:
            return self.rng.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


class DateTimeSampler(ColumnSampler):
    """Uniform datetime in [2016-01-01, 2016-12-31], format '%Y-%m-%d %H:%M:%S.0' (specification)."""

    def __init__(self, elements, p, max_l0, rng, boundary=(), near=()):
        els = [str(e) for e in elements if e is not None]
        els += [str(b) for b in boundary] + [str(n) for n in near]
        super().__init__(els, p, max_l0, rng)
        self.lo = dt.datetime(2016, 1, 1)
        self.hi = dt.datetime(2016, 12, 31, 23, 59, 59)

    def _draw(self):
        r = self.rng
        d = self.lo + dt.timedelta(seconds=r.randint(0, int((self.hi - self.lo).total_seconds())))
        return d.strftime('%Y-%m-%d %H:%M:%S.0')

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


class TimeSampler(ColumnSampler):
    """fuzz/time.py."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            e = str(r.choice(self.elements))
            parts = e.split(':')
            if len(parts) == 3 and all(x.isdigit() for x in parts) and r.random() < self.p:
                i = r.randrange(3)
                rngs = [list(range(24)), list(range(60)), list(range(60))]
                parts[i] = '%02d' % rngs[i][int(parts[i]) % len(rngs[i]) - 1]
                e = ':'.join(parts)
            return e
        return '%02d:%02d:%02d' % (r.randrange(24), r.randrange(60), r.randrange(60))


class BoolSampler(ColumnSampler):
    """fuzz/bool.py (Bool True/False, Bit 1/0)."""

    def __init__(self, elements, p, max_l0, rng, bit=False):
        super().__init__(elements, p, max_l0, rng)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


class CoordSampler(ColumnSampler):
    """REAL coordinate: longitude uniform 0..180, latitude uniform 0..90 (specification)."""

    def __init__(self, elements, p, max_l0, rng, hi=180.0):
        super().__init__([_num(e) for e in elements if _num(e) is not None], p, max_l0, rng)
        self.hi = hi

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: round(r.uniform(0.0, self.hi), 4))


class ProbSampler(ColumnSampler):
    """REAL probability: uniform 0..1 rounded to 4 decimals (specification)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: round(r.uniform(0.0, 1.0), 4))


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4)
        return DateSampler(els, p, max_l0, rng)
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng)
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec, unsigned='unsigned' in t)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]


def _is_int_col(column) -> bool:
    return 'int' in (column.type_str or '').lower()


def _is_real_col(column) -> bool:
    t = (column.type_str or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'numeric', 'decimal'))


def _is_text_col(column) -> bool:
    t = (column.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob'))


def _is_datetime_col(column) -> bool:
    t = (column.type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _enum_pool_for(table: str, column: str):
    if column == 'gender':
        return GENDER_ENUM
    if column == 'group':
        return GROUP_ENUM
    if column == 'phone_brand':
        return BRAND_POOL
    if column == 'device_model':
        return MODEL_POOL
    if column == 'category':
        return CATEGORY_POOL
    if column in PROB_COLS:
        return None
    return None


def build_spec_sampler(table: str, column, literal_pool: list, original_values, p: float, rng,
                       max_l0: float, null_share: float):
    """Build a sampler implementing the specification for one column."""
    key = (table, column.name)
    ov = [v for v in original_values if v is not None]
    lit = [str(v) for v in literal_pool]
    boundary = BOUNDARY.get(key, [])
    near = NEAR_VARIANTS.get(key, [])
    dt_boundary = BOUNDARY_DT.get(key, [])

    if key in INT64_COLUMNS and _is_int_col(column):
        return Int64Sampler(ov, boundary, p, max_l0, rng), null_share

    enum = _enum_pool_for(table, column.name)
    if enum is not None and _is_text_col(column):
        return EnumSampler(enum, p, max_l0, rng, boundary=boundary, near=near), null_share

    if column.name in PROB_COLS and _is_real_col(column):
        return ProbSampler(ov + [float(x) for x in lit if _num(x) is not None], p, max_l0, rng), null_share

    if column.name == 'longitude' and _is_real_col(column):
        return CoordSampler(ov, p, max_l0, rng, hi=180.0), null_share
    if column.name == 'latitude' and _is_real_col(column):
        return CoordSampler(ov, p, max_l0, rng, hi=90.0), null_share

    if _is_datetime_col(column):
        return DateTimeSampler(ov, p, max_l0, rng, boundary=dt_boundary, near=near), null_share

    if _is_int_col(column) and boundary:
        lo = min(boundary) - 5
        hi = max(boundary) + 5
        if column.name == 'age':
            lo, hi = 0, 100
        return BoundaryNumberSampler(boundary, p, max_l0, rng, lo=lo, hi=hi), null_share

    if _is_int_col(column) and column.name == 'age':
        return NumberSampler(ov + [int(x) for x in lit if _num(x) is not None], p, max_l0, rng,
                             is_int=True, lo=0, hi=100), null_share

    if _is_text_col(column) and (boundary or near):
        els = ov + lit + [str(b) for b in boundary] + [str(n) for n in near]
        for b in list(boundary):
            if isinstance(b, str):
                els += _case_variants(b) + _str_variants(b)
        return StringSampler(els, p, max_l0, rng), null_share

    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted(set(lit))
    if column.checked:
        p = 0.0
    return make_column_sampler(column, els, p, max_l0, rng), null_share
