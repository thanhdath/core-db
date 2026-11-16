"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

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

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
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


def _near_variants(v: str, rng) -> str:
    """5% fresh near-variants: case change, trailing space, one-char edit."""
    u = rng.random()
    if u < 0.25:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.5:
        return v + ' '
    if u < 0.75 and v:
        i = rng.randrange(len(v))
        return v[:i] + rng.choice(string.ascii_letters) + v[i + 1:]
    return v + rng.choice(string.ascii_letters)


class EnumSampler(ColumnSampler):
    """Uniform over the listed enum values; 5% case-variant near-duplicates."""

    def __init__(self, values: list, rng, p: float = 0.0, max_l0: float = float('inf')):
        super().__init__(values, p, max_l0, rng)
        self.values = list(values)

    def sample(self):
        r = self.rng
        v = r.choice(self.values)
        if r.random() < 0.05:
            v = _near_variants(v, r)
        return v


class RangeSampler(ColumnSampler):
    """Uniform in [min, max], rounded to 1 decimal; 5% boundary values at min/max and one step outside."""

    def __init__(self, lo: float, hi: float, rng, is_int: bool = False, boundaries: list = None,
                 p: float = 0.0, max_l0: float = float('inf')):
        super().__init__([], p, max_l0, rng)
        self.lo, self.hi, self.is_int = lo, hi, is_int
        self.boundaries = list(boundaries or [])

    def sample(self):
        r = self.rng
        if self.boundaries and r.random() < 0.05:
            v = r.choice(self.boundaries)
        elif r.random() < 0.05:
            v = r.choice([self.lo, self.hi, self.lo - 1, self.hi + 1])
        else:
            v = r.uniform(self.lo, self.hi)
        if self.is_int:
            return int(round(v))
        return round(float(v), 1)


class NanTextSampler(ColumnSampler):
    """TEXT column storing numeric strings and the 'nan' marker (range applies to non-'nan')."""

    def __init__(self, lo: float, hi: float, rng, boundaries: list = None, nan_share: float = 0.10,
                 p: float = 0.0, max_l0: float = float('inf')):
        super().__init__([], p, max_l0, rng)
        self.lo, self.hi = lo, hi
        self.boundaries = list(boundaries or [])
        self.nan_share = nan_share

    def sample(self):
        r = self.rng
        if r.random() < self.nan_share:
            return 'nan' if r.random() < 0.9 else 'NAN'
        if self.boundaries and r.random() < 0.05:
            v = r.choice(self.boundaries)
        elif r.random() < 0.05:
            v = r.choice([self.lo, self.hi])
        else:
            v = r.uniform(self.lo, self.hi)
        return repr(round(float(v), 4))


class BoundaryStringSampler(ColumnSampler):
    """String column with planted boundary literals plus the generic string pool."""

    def __init__(self, elements, boundaries: list, rng, p: float = 0.2, max_l0: float = float('inf'),
                 boundary_share: float = 0.10):
        super().__init__(elements, p, max_l0, rng)
        self.boundaries = list(boundaries or [])
        self.boundary_share = boundary_share
        self._inner = StringSampler(elements, p, max_l0, rng)

    def sample(self):
        r = self.rng
        if self.boundaries and r.random() < self.boundary_share:
            return r.choice(self.boundaries)
        return self._inner.sample()


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
    s = _init_sampler(column_meta, literal_pool, original_values, p, max_l0, rng, 1 if column_meta.pk_pos else 0)
    return [s.sample() for _ in range(n)]


def spec_sampler(table: str, column: str, spec: dict, rng, elements: list, p: float,
                 max_l0: float) -> ColumnSampler:
    """Build a specification-aware sampler for (table, column); falls back to the generic one."""
    key = '%s.%s' % (table, column)
    enums = spec.get('enums', {})
    ranges = spec.get('ranges', {})
    boundaries = spec.get('boundaries', {})
    nan_cols = set(spec.get('nan_columns', []))
    if key in enums:
        return EnumSampler(enums[key], rng, p, max_l0)
    if key in nan_cols and key in ranges:
        lo, hi = ranges[key]
        return NanTextSampler(lo, hi, rng, boundaries.get(key), p=p, max_l0=max_l0)
    if key in ranges:
        lo, hi = ranges[key]
        is_int = isinstance(lo, int) and isinstance(hi, int)
        return RangeSampler(lo, hi, rng, is_int=is_int, boundaries=boundaries.get(key), p=p, max_l0=max_l0)
    return None
