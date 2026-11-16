"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
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
        hi_ = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi_, hi_)
        if lo is not None:
            self.min = lo
        if hi is not None:
            self.max = hi
        if self.min > self.max:
            self.min, self.max = self.max, self.min
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)
        self.list_min = max(self.list_min, self.min)
        self.list_max = min(self.list_max, self.max)
        if self.list_min > self.list_max:
            self.list_min, self.list_max = self.min, self.max

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def _clamp(self, v):
        if self.is_int:
            v = int(round(v))
        return max(self.min, min(self.max, v))

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            lo, hi = min(lo, hi), max(lo, hi)
            if self.is_int:
                lo_i, hi_i = int(lo), int(hi)
                if lo_i > hi_i:
                    lo_i, hi_i = hi_i, lo_i
                v = self._fresh_or_reuse(lambda: r.randint(lo_i, hi_i))
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
        return self._cast(self._clamp(v))


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
        if lo > hi:
            lo, hi = hi, lo
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
    """Explicit enum / flag domain (spec enums); always returns a member of the domain."""

    def __init__(self, domain, p, max_l0, rng):
        super().__init__(list(domain), p, max_l0, rng)
        self.domain = list(domain)

    def sample(self):
        return self.rng.choice(self.domain)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, lo=None, hi=None) -> ColumnSampler:
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
        return DateSampler(els, p, max_l0, rng, lo=lo, hi=hi)
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng)
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4, lo=lo, hi=hi)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, lo=lo, hi=hi)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _clamp_boundary(key, b):
    """Clamp a boundary value to the declared spec range for bounded columns."""
    rng_spec = spec.RANGES.get(key)
    if rng_spec is None:
        return b
    lo, hi = rng_spec
    if isinstance(b, (int, float)) and not isinstance(b, bool) and isinstance(lo, (int, float)):
        return max(lo, min(hi, b))
    return b


def _spec_elements(table, column, literal_pool, original_values, rng):
    """Specification-driven element pool: observed values, pool literals, boundary literals, LIKE near variants, enum
    members and range endpoints."""
    key = (table, column)
    els = list(original_values)
    els += sorted({str(v) for v in literal_pool})
    for b in spec.BOUNDARY.get(key, ()):
        els.append(b)
        if isinstance(b, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', b):
            els.append(_clamp_boundary(key, spec.date_shift(b, -1)))
            els.append(_clamp_boundary(key, spec.date_shift(b, 1)))
        elif isinstance(b, (int, float)) and not isinstance(b, bool):
            els.append(_clamp_boundary(key, b - 1))
            els.append(_clamp_boundary(key, b + 1))
    for lit in spec.LIKE_LITERALS.get(key, ()):
        body = lit.replace('%', '')
        els.append(body)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', body):
            els.append(_clamp_boundary(key, spec.date_shift(body, -1)))
            els.append(_clamp_boundary(key, spec.date_shift(body, 1)))
    return els


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), table: str = '') -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224, extended with the specification pools."""
    key = (table, column.name)
    if key == ('customers', 'SubscribedToEmailList') or key in (
            ('rootbeerbrand', 'CaneSugar'), ('rootbeerbrand', 'CornSyrup'), ('rootbeerbrand', 'Honey'),
            ('rootbeerbrand', 'ArtificialSweetener'), ('rootbeerbrand', 'Caffeinated'),
            ('rootbeerbrand', 'Alcoholic'), ('rootbeerbrand', 'AvailableInCans'),
            ('rootbeerbrand', 'AvailableInBottles'), ('rootbeerbrand', 'AvailableInKegs')):
        return EnumSampler(spec.FLAG, p, max_l0, rng)
    if key == ('customers', 'Gender'):
        return EnumSampler(spec.GENDER, p, max_l0, rng)
    if key == ('rootbeer', 'ContainerType'):
        return EnumSampler(spec.CONTAINER, p, max_l0, rng)
    if key == ('transaction', 'CreditCardType'):
        return EnumSampler(spec.CARD_TYPE, p, max_l0, rng)

    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + _spec_elements(table, column.name, literal_pool, ov, rng)
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    lo = hi = None
    rng_spec = spec.RANGES.get(key)
    if rng_spec is not None:
        lo, hi = rng_spec
    return make_column_sampler(column, els, p, max_l0, rng, lo=lo, hi=hi)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), table: str = '') -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, table=table)
    return [s.sample() for _ in range(n)]


def apply_null_rule(values: list, nullable: bool, share: float, rng) -> list:
    """NULL rule (authoritative): strip pre-existing NULLs, then plant exactly the target number of NULLs."""
    if not nullable or not values:
        return values
    n = len(values)
    non_null = [v for v in values if v is not None]
    if not non_null:
        return values
    k = max(1, int(round(share * n)))
    if n >= 2:
        k = min(k, n - 1)
    k = min(k, n)
    out = list(non_null)
    while len(out) < n:
        out.append(rng.choice(non_null))
    rng.shuffle(out)
    idx = rng.sample(range(n), k)
    for i in idx:
        out[i] = None
    return out
