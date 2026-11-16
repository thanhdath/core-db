"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224)."""
import datetime as dt
import re
import string

from . import spec

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


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


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class NumberSampler(ColumnSampler):
    """fuzz/number.py; keeps the list_max overwrite quirk (number.py:60,67)."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        if lo is not None and hi is not None:
            self.min, self.max = int(lo), int(hi)
        else:
            h = min(10 ** scale, _MAX)
            self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-h, h)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
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


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class DateSampler(ColumnSampler):
    """fuzz/date.py + utils/data_parser.py."""

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


class EnumSampler(ColumnSampler):
    def __init__(self, values, p, max_l0, rng):
        super().__init__(values, p, max_l0, rng)
        self.values = list(values)

    def sample(self):
        return self.rng.choice(self.values)


class CurrencySampler(ColumnSampler):
    """Format 'US$<integer>,<3-digit>.00'; integer part in [lo, hi]."""

    def __init__(self, lo, hi, p, max_l0, rng, elements=(), boundary=True):
        super().__init__(list(elements), p, max_l0, rng)
        self.lo, self.hi = int(lo), int(hi)
        self.boundary = boundary

    @staticmethod
    def _fmt(n):
        n = max(0, int(n))
        return 'US$%s,%03d.00' % (format(n // 1000, ','), n % 1000)

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        n = r.randint(self.lo, self.hi)
        if self.boundary and r.random() < 0.15:
            cand = [b for b in spec.SALARY_BOUNDARY if self.lo <= b <= self.hi]
            if cand:
                n = r.choice(cand)
        return self._fmt(n)

    @classmethod
    def format_value(cls, n):
        return cls._fmt(n)


class FormattedDateSampler(ColumnSampler):
    def __init__(self, fmt, lo, hi, p, max_l0, rng, elements=()):
        super().__init__(list(elements), p, max_l0, rng)
        self.fmt = fmt
        self.lo = dt.datetime(*lo)
        self.hi = dt.datetime(*hi)

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        span = int((self.hi - self.lo).total_seconds())
        d = self.lo + dt.timedelta(seconds=r.randint(0, span))
        s = d.strftime(self.fmt)
        return re.sub(r'(^|[-/ :])0(\d)', r'\1\2', s)


class SsnSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        return '%03d-%02d-%04d' % (r.randint(0, 999), r.randint(0, 99), r.randint(0, 9999))


class PhoneSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        return '(%03d)%03d-%04d' % (r.randint(200, 999), r.randint(0, 999), r.randint(0, 9999))


class NameSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        k = r.randint(3, 9)
        return ''.join(r.choice(string.ascii_uppercase) if i == 0 else r.choice(string.ascii_lowercase)
                       for i in range(k))


class BoundarySampler(ColumnSampler):
    def __init__(self, values, rng):
        super().__init__(list(values), 0.0, float('inf'), rng)
        self.values = list(values)

    def sample(self):
        return self.rng.choice(self.values)


class IntGroupSampler(ColumnSampler):
    """Integer column whose GROUP BY must show group sizes 1, 2 and >= 3. Returns small distinct integers so groups
    are naturally formed by FK/join aggregation."""
    def __init__(self, lo, hi, p, max_l0, rng):
        super().__init__([], p, max_l0, rng)
        self.lo, self.hi = int(lo), int(hi)

    def sample(self):
        return self.rng.randint(self.lo, self.hi)


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
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]


def spec_sampler(table: str, column: str, column_meta, literal_pool: list, original_values,
                 p: float, max_l0: float, rng) -> ColumnSampler:
    """Return a sampler that implements the specification for (table, column)."""
    key = (table, column)
    ov = [v for v in original_values if v is not None]
    pool = sorted({str(v) for v in literal_pool})
    if key in spec.ENUMS:
        vals = list(spec.ENUMS[key])
        vals += [v for v in spec.BOUNDARY_VALUES.get(key, []) if v not in vals]
        vals += [v for v in spec.LIKE_VARIANTS.get(key, []) if v not in vals]
        return EnumSampler(vals, p, max_l0, rng)
    if key == ('employee', 'salary'):
        return CurrencySampler(spec.SALARY_RANGE[0], spec.SALARY_RANGE[1], p, max_l0, rng, elements=ov,
                               boundary=True)
    if key == ('position', 'minsalary'):
        return CurrencySampler(spec.MINSALARY_RANGE[0], spec.MINSALARY_RANGE[1], p, max_l0, rng, elements=ov,
                               boundary=False)
    if key == ('position', 'maxsalary'):
        return CurrencySampler(spec.MAXSALARY_RANGE[0], spec.MAXSALARY_RANGE[1], p, max_l0, rng, elements=ov,
                               boundary=False)
    if key == ('employee', 'hiredate'):
        return FormattedDateSampler(spec.DATE_FORMAT, spec.DATE_RANGE[0], spec.DATE_RANGE[1],
                                    p, max_l0, rng, elements=ov)
    if key == ('employee', 'ssn'):
        return SsnSampler([], p, max_l0, rng)
    if key == ('location', 'officephone'):
        return PhoneSampler([], p, max_l0, rng)
    if key in (('employee', 'firstname'), ('employee', 'lastname')):
        return NameSampler([], p, max_l0, rng)
    if key == ('location', 'zipcode'):
        return IntGroupSampler(1000, 99999, p, max_l0, rng)
    if key in (('location', 'locationID'), ('position', 'positionID')):
        return NumberSampler([], 1.0, float('inf'), rng, is_int=True, lo=1, hi=10 ** 6)
    if key in spec.BOUNDARY_VALUES or key in spec.LIKE_VARIANTS:
        vals = list(spec.BOUNDARY_VALUES.get(key, [])) + list(spec.LIKE_VARIANTS.get(key, []))
        vals += ov
        return BoundarySampler(vals, rng)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + pool
    if column_meta.checked:
        p = 0.0
    return make_column_sampler(column_meta, els, p, max_l0, rng)
