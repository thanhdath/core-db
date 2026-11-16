"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

from . import spec

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_int_type(t: str) -> bool:
    return 'int' in t


def _is_real_type(t: str) -> bool:
    return any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number'))


def _is_date_type(t: str) -> bool:
    return 'date' in t or 'timestamp' in t


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


def _iso(d: dt.date) -> str:
    return d.strftime('%Y-%m-%d')


def _rand_str(rng, k: int) -> str:
    return ''.join(rng.choice(CHARSET) for _ in range(k))


def _rand_words(rng, lo: int, hi: int) -> str:
    """Random lowercase words joined by spaces, length in [lo, hi]."""
    words = ['slyly', 'regular', 'accounts', 'cajole', 'furiously', 'pending', 'deposits',
             'blithely', 'final', 'requests', 'sleep', 'quickly', 'ironic', 'packages',
             'theodolites', 'express', 'ideas', 'haggle', 'carefully', 'even', 'pinto', 'beans']
    out = []
    n = 0
    while n < lo:
        w = rng.choice(words)
        out.append(w)
        n += len(w) + 1
    s = ' '.join(out)
    return s[:hi] if len(s) > hi else s


def _near_variant(rng, s: str) -> str:
    """One near-variant (prefix/suffix change) of a text literal."""
    u = rng.random()
    if u < 0.25:
        return s + _rand_str(rng, 2)
    if u < 0.5:
        return _rand_str(rng, 2) + s
    if u < 0.75 and len(s) > 1:
        return s[:-1]
    if len(s) > 1:
        return s[1:]
    return s + 'x'


def _text_variants(rng, lit: str) -> list:
    """literal, upper-case, lower-case and one near-variant (equal probability)."""
    return [lit, lit.upper(), lit.lower(), _near_variant(rng, lit)]


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
        if lo is not None and hi is not None:
            self.min, self.max = lo, hi
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
        if self.is_int:
            v = int(min(max(v, int(self.min)), int(self.max)))
        else:
            v = min(max(v, self.min), self.max)
        return self._cast(v)


class NarrowRangeSampler(ColumnSampler):
    """Sample directly from a narrow integer range (e.g. l_linenumber 1..7)."""

    def __init__(self, lo: int, hi: int, rng):
        super().__init__([], 1.0, float('inf'), rng)
        self.lo, self.hi = int(lo), int(hi)

    def sample(self):
        return self.rng.randint(self.lo, self.hi)


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
        return _rand_str(self.rng, k)

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


class CommentSampler(ColumnSampler):
    """Random lowercase words joined by spaces, length 20-120."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: _rand_words(r, *spec.TEXT_COMMENT_LEN))


class EnumSampler(ColumnSampler):
    """Uniform choice from the per-column enum list."""

    def __init__(self, values, rng):
        super().__init__(list(values), 1.0, float('inf'), rng)

    def sample(self):
        return self.rng.choice(self.elements)


class BoundaryTextSampler(ColumnSampler):
    """Emit the literal, its upper/lower-case variants and one near-variant."""

    def __init__(self, literals, rng):
        super().__init__(list(literals), 1.0, float('inf'), rng)

    def sample(self):
        lit = self.rng.choice(self.elements)
        return self.rng.choice(_text_variants(self.rng, lit))


class NameSampler(ColumnSampler):
    """Formatted names (Customer#..., Supplier#..., Clerk#..., Brand#..., Manufacturer#...)."""

    def __init__(self, fmt, rng, lo=1, hi=100000):
        super().__init__([], 1.0, float('inf'), rng)
        self.fmt, self.lo, self.hi = fmt, lo, hi

    def sample(self):
        return self.fmt % self.rng.randint(self.lo, self.hi)


class DateSampler(ColumnSampler):
    """fuzz/date.py + utils/data_parser.py (an ELEMENT is returned w.p. p)."""

    def __init__(self, elements, p, max_l0, rng, lo=None, hi=None):
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
        if lo is not None and hi is not None:
            self.full = (dt.datetime.strptime(lo, '%Y-%m-%d'), dt.datetime.strptime(hi, '%Y-%m-%d'))
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


class BoundaryDateSampler(ColumnSampler):
    """For each listed literal D emit D, D-1 day, D+1 day in %Y-%m-%d."""

    def __init__(self, literals, rng):
        super().__init__([], 1.0, float('inf'), rng)
        self.dates = []
        for s in literals:
            d = dt.datetime.strptime(s, '%Y-%m-%d').date()
            self.dates += [d - dt.timedelta(days=1), d, d + dt.timedelta(days=1)]

    def sample(self):
        return _iso(self.rng.choice(self.dates))


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


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng)
    if _is_date_type(t):
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


def spec_sampler(table: str, column, rng, literal_pool: list, original_values: list,
                 pk_pool: list = None) -> ColumnSampler:
    """Build the sampler for one column *by construction* from the specification."""
    key = (table, column.name)
    t = (column.type_str or '').lower().strip()
    if key in spec.NARROW_RANGES:
        lo, hi = spec.NARROW_RANGES[key]
        return NarrowRangeSampler(lo, hi, rng)
    if key in spec.ENUMS:
        return EnumSampler(spec.ENUMS[key], rng)
    if key in spec.BOUNDARY_TEXT:
        return BoundaryTextSampler(spec.BOUNDARY_TEXT[key], rng)
    if key in spec.BOUNDARY_NUMERIC:
        vals = spec.BOUNDARY_NUMERIC[key]
        is_int = _is_int_type(t)
        step = 1 if is_int else 0.01
        els = []
        for v in vals:
            els += [v - step, v, v + step]
        if key == ('customer', 'c_acctbal'):
            lo, hi = spec.REAL_BALANCE
        elif key == ('partsupp', 'ps_supplycost'):
            lo, hi = spec.REAL_AMOUNT
        elif is_int:
            lo, hi = spec.INT_RANGE
        else:
            lo, hi = spec.REAL_AMOUNT
        return NumberSampler(els, 0.0, float('inf'), rng, is_int=is_int,
                             precision=0 if is_int else 2, lo=lo, hi=hi)
    if key in spec.BOUNDARY_DATE:
        return BoundaryDateSampler(spec.BOUNDARY_DATE[key], rng)
    if key in spec.NAME_FORMATS:
        return NameSampler(spec.NAME_FORMATS[key], rng)
    if column.name.endswith('_comment'):
        return CommentSampler(list(original_values), 0.2, float('inf'), rng)
    if _is_int_type(t):
        lo, hi = spec.INT_RANGE
        if column.pk_pos > 0 and pk_pool is not None:
            return NumberSampler([], 1.0, float('inf'), rng, is_int=True, lo=lo, hi=hi)
        return NumberSampler(list(original_values), 0.2, float('inf'), rng, is_int=True, lo=lo, hi=hi)
    if _is_real_type(t):
        if 'bal' in column.name:
            lo, hi = spec.REAL_BALANCE
        elif any(k in column.name for k in ('discount', 'tax')):
            lo, hi = spec.REAL_RATE
        else:
            lo, hi = spec.REAL_AMOUNT
        return NumberSampler(list(original_values), 0.2, float('inf'), rng, is_int=False, precision=2, lo=lo, hi=hi)
    if _is_date_type(t):
        lo, hi = spec.DATE_RANGE
        return DateSampler(list(original_values), 0.2, float('inf'), rng, lo=lo, hi=hi)
    if column.name in ('c_address', 's_address', 'c_phone', 's_phone'):
        return StringSampler(list(original_values), 0.2, float('inf'), rng, length=spec.TEXT_SHORT_LEN[1])
    return StringSampler(list(original_values), 0.2, float('inf'), rng, length=spec.TEXT_SHORT_LEN[1])
