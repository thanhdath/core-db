"""Per-type value generators; NULL, enum and boundary handled by construction."""
import datetime as dt
import re
import string

from .spec import BOUNDARY, ENUMS, DUP_DISTINCT_SHARE

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_lowercase
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


class ColumnSampler:
    """Base fuzzer; holds spec-derived enum/boundary pools by construction."""

    def __init__(self, column, elements: list, p: float, max_l0: float, rng, nullable: bool = False,
                 null_share: float = 0.0):
        self.column = column
        self.key = (column.table, column.name)
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.nullable = nullable
        self.null_share = null_share
        self.fresh: list = []
        self.enum_pool = list(ENUMS.get(self.key, []))
        self.boundary_pool = list(BOUNDARY.get(self.key, [])) if column.pk_pos == 0 else []
        self.dup_share = DUP_DISTINCT_SHARE

    def _fresh_or_reuse(self, draw):
        if self.fresh and len(self.fresh) > self.max_l0:
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
    """Integer/real generation; non-key integers default to [1,100]."""

    def __init__(self, column, elements, p, max_l0, rng, scale=10, is_int=True, precision=0,
                 nullable=False, null_share=0.0):
        super().__init__(column, [f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng,
                         nullable, null_share)
        self.is_int, self.precision = is_int, precision
        if is_int:
            self.min, self.max = 1, 100
        else:
            self.min, self.max = 0, float(min(10 ** min(scale, 6), _MAX))
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if self.nullable and r.random() < self.null_share:
            return None
        if self.boundary_pool and r.random() < 0.35:
            b = r.choice(self.boundary_pool)
            if isinstance(b, (int, float)):
                return self._cast(b)
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)) if self.is_int else r.uniform(lo, hi))
        else:
            v = r.choice(self.elements)
        d = 1 if self.is_int else 0.01
        u = r.random()
        if u < 1 / 6:
            v += d
        elif u < 1 / 3:
            v -= d
        elif u < 1 / 2:
            v += 2 * d
        elif u < 2 / 3:
            v -= 2 * d
        return self._cast(v)


class StringSampler(ColumnSampler):
    """String generation: enum columns restricted to enum pool; text tokens short lowercase."""

    def __init__(self, column, elements, p, max_l0, rng, length=3, nullable=False, null_share=0.0):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(column, els + extra, p, max_l0, rng, nullable, null_share)
        if self.enum_pool:
            self.lo, self.hi = min(map(len, self.enum_pool)), max(map(len, self.enum_pool))
        else:
            self.lo, self.hi = 1, max(1, min(length, 3))

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def sample(self):
        r = self.rng
        if self.nullable and r.random() < self.null_share:
            return None
        if self.enum_pool:
            return r.choice(self.enum_pool)
        if self.boundary_pool and r.random() < 0.30:
            b = r.choice(self.boundary_pool)
            return b
        if not self.elements or r.random() < self.p:
            return self._fresh_or_reuse(lambda: self._rand(r.randint(self.lo, self.hi)))
        return r.choice(self.elements)


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class DateSampler(ColumnSampler):
    """Datetime generation between 1970-01-01 and 2016-12-31, default 'YYYY-MM-DD HH:MM:SS'."""

    def __init__(self, column, elements, p, max_l0, rng, nullable=False, null_share=0.0):
        super().__init__(column, elements, p, max_l0, rng, nullable, null_share)
        self.as_int = bool(self.elements) and all(isinstance(e, int) for e in self.elements)
        strs = [str(e) for e in self.elements]
        parsed = []
        for s in strs:
            _, d = _parse_date(s)
            if d is not None:
                parsed.append(d)
        self.template = '%Y-%m-%d %H:%M:%S'
        self.full = (dt.datetime(1970, 1, 1), dt.datetime(2016, 12, 31, 23, 59, 59))
        self.rng_dates = (min(parsed), max(parsed)) if len(set(parsed)) >= 2 else self.full

    def _draw(self):
        r = self.rng
        lo, hi = self.full if (r.random() < self.p or self.rng_dates == self.full) else self.rng_dates
        base = lo + dt.timedelta(seconds=r.randint(0, max(0, int((hi - lo).total_seconds()))))
        s = base.strftime(self.template)
        return int(s) if self.as_int and s.isdigit() else s

    def sample(self):
        if self.nullable and self.rng.random() < self.null_share:
            return None
        if self.elements and self.rng.random() < self.p:
            return self.rng.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


class TimeSampler(ColumnSampler):
    """Time-of-day generation."""

    def sample(self):
        r = self.rng
        if self.nullable and r.random() < self.null_share:
            return None
        if self.elements and r.random() >= self.p:
            return str(r.choice(self.elements))
        return '%02d:%02d:%02d' % (r.randrange(24), r.randrange(60), r.randrange(60))


class BoolSampler(ColumnSampler):
    """Boolean/bit generation."""

    def __init__(self, column, elements, p, max_l0, rng, bit=False, nullable=False, null_share=0.0):
        super().__init__(column, elements, p, max_l0, rng, nullable, null_share)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if self.nullable and self.rng.random() < self.null_share:
            return None
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, nullable=False,
                        null_share=0.0) -> ColumnSampler:
    """Pick the fuzzer by declared type; unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(column, els, p, max_l0, rng, nullable, null_share)
    if t == '' or t == 'blob':
        return StringSampler(column, els, p, max_l0, rng, nullable=nullable, null_share=null_share)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(column, els, p, max_l0, rng, scale=4, nullable=nullable, null_share=null_share)
        return DateSampler(column, els, p, max_l0, rng, nullable, null_share)
    if 'bool' in t:
        return BoolSampler(column, els, p, max_l0, rng, nullable=nullable, null_share=null_share)
    if 'bit' in t:
        return BoolSampler(column, els, p, max_l0, rng, bit=True, nullable=nullable, null_share=null_share)
    if 'year' in t:
        return NumberSampler(column, els, p, max_l0, rng, scale=4, nullable=nullable, null_share=null_share)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(column, els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             nullable=nullable, null_share=null_share)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(column, els, p, max_l0, rng, length=args[0] if args else 20,
                             nullable=nullable, null_share=null_share)
    return StringSampler(column, els, p, max_l0, rng, nullable=nullable, null_share=null_share)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), *, nullable: bool = False, null_share: float = 0.0) -> ColumnSampler:
    """Per-column initialisation plus spec-derived NULL control."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, nullable=nullable, null_share=null_share)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), nullable: bool = False,
                               null_share: float = 0.0) -> list:
    """Initialise one column fuzzer and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, nullable=nullable, null_share=null_share)
    return [s.sample() for _ in range(n)]
