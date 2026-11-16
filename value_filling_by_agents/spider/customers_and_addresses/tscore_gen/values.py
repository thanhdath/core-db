"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224) + spec-aware samplers."""
import datetime as dt
import re
import string

from .spec import like_body

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


class BoundaryGate:
    """Tracks which required literals have already been emitted for a column."""

    def __init__(self, required):
        self.required = [str(r) for r in required]
        self.remaining = list(self.required)
        self.emitted = set()

    def is_boundary(self, value):
        return str(value) in self.emitted

    def pending(self):
        if self.remaining:
            v = self.remaining.pop(0)
            self.emitted.add(v)
            return v
        return None


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements, p, max_l0, rng):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh = []

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
                 positive=False, start=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        self.positive = positive
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        if positive:
            self.min, self.max = 1, min(10 ** scale, _MAX)
        if start is not None and is_int:
            self.min = max(self.min, int(start))
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)

    def _cast(self, v):
        v = int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)
        if self.positive:
            v = max(1, v)
        if self.is_int:
            v = max(int(self.min), v)
        return v

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            if self.is_int:
                v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)))
            else:
                v = self._fresh_or_reuse(lambda: r.uniform(lo, hi))
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
    """fuzz/string.py (allow_none dropped), plus boundary and near-variant literals."""

    def __init__(self, elements, p, max_l0, rng, length=20, boundary=(), required=()):
        els = [str(e) for e in elements if e is not None]
        extra = []
        for e in els:
            if '%' in e:
                extra.append(e)
                body = like_body(e)
                if body:
                    extra.append(body)
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        for b in boundary:
            b = str(b)
            if '%' in b:
                extra.append(b)
                body = like_body(b)
                if body:
                    extra.append(body)
                continue
            body = like_body(b)
            if not body:
                continue
            extra += [body]
            if len(body) > 1:
                extra += [body.strip()]
        for b in required:
            if b not in extra:
                extra.append(str(b))
        super().__init__(els + extra, p, max_l0, rng)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.gate = BoundaryGate(required)

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def sample(self):
        r = self.rng
        v = self.gate.pending()
        if v is not None:
            return v
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(lambda: self._rand(r.randint(self.lo, self.hi)))
        else:
            v = r.choice(self.elements)
        if self.gate.is_boundary(v):
            return v
        if '%' in v:
            return v
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
    """Uniform choice from a declared enum domain."""

    def __init__(self, choices, rng):
        els = list(dict.fromkeys(str(c) for c in choices if c is not None))
        super().__init__(els, 1.0, float('inf'), rng)

    def sample(self):
        return self.rng.choice(self.elements)


class PositiveQuantitySampler(ColumnSampler):
    """Positive integer stored as text (``CAST(order_quantity AS INTEGER) > 0``)."""

    def __init__(self, elements, p, max_l0, rng):
        ints = [int(e) for e in elements if re.fullmatch(r'-?\d+', str(e))]
        super().__init__(ints, p, max_l0, rng)
        self.num = NumberSampler(ints, 1.0, max_l0, rng, scale=2, is_int=True, positive=True)

    def sample(self):
        return str(self.num.sample())


def _parse_date(s):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(),
               str(s).strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class DateSampler(ColumnSampler):
    """fuzz/date.py + utils/data_parser.py (an ELEMENT is returned w.p. p)."""

    def __init__(self, elements, p, max_l0, rng, window=None):
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
        self.template = self.template or '%Y-%m-%d %H:%M:%S'
        self.full = (dt.datetime(1800, 1, 1), dt.datetime(2100, 1, 1))
        if window:
            lo = _parse_date(window[0])
            hi = _parse_date(window[1])
            if lo and hi and lo[1] < hi[1]:
                self.full = (lo[1], hi[1])
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
    def __init__(self, elements, p, max_l0, rng, bit=False):
        super().__init__(elements, p, max_l0, rng)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements, p, max_l0, rng, *, boundary=(), required=(), enum=None,
                        positive=False, window=None, start=None):
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); spec-aware overrides first."""
    if enum:
        return EnumSampler(enum, rng)
    els = [e for e in elements if rng.random() < 0.9]
    if positive:
        return PositiveQuantitySampler(els, p, max_l0, rng)
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng, boundary=boundary, required=required)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4)
        return DateSampler(els, p, max_l0, rng, window=window)
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
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, positive=positive, start=start)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20, boundary=boundary,
                             required=required)
    return StringSampler(els, p, max_l0, rng, boundary=boundary, required=required)


def _init_sampler(column, literal_pool, original_values, p, rng, n_pk, max_l0=float('inf'), *, boundary=(),
                  required=(), enum=None, positive=False, window=None, start=None):
    """Per-column initialisation of fuzz/fuzz.py:198-224, extended by specification domains."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, boundary=boundary, required=required, enum=enum,
                               positive=positive, window=window, start=start)


def random_values_for_a_column(column_meta, literal_pool, n, rng, *, original_values=(), p=0.2,
                               max_l0=float('inf'), boundary=(), required=(), enum=None, positive=False,
                               window=None, start=None):
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, boundary=boundary, required=required, enum=enum, positive=positive, window=window,
                      start=start)
    return [s.sample() for _ in range(n)]
