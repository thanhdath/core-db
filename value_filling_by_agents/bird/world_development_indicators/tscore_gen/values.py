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
    """fuzz/number.py; range-constrained columns are clamped after perturbation."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi_s = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi_s, hi_s)
        if lo is not None:
            self.min = lo
        if hi is not None:
            self.max = hi
        self.clamp_lo, self.clamp_hi = lo, hi
        self.list_min = min(self.elements) if self.elements else max(self.min, 0)
        self.list_max = min(self.max, _MAX)

    def _cast(self, v):
        v = int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)
        if self.clamp_lo is not None and v < self.clamp_lo:
            v = self.clamp_lo
        if self.clamp_hi is not None and v > self.clamp_hi:
            v = self.clamp_hi
        return v

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            if hi < lo:
                lo, hi = self.min, self.max
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
            v = self._fresh_or_reuse(lambda: self._rand(r.randint(self.lo, max(self.lo, self.hi))))
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
    """Uniform over an enumerated domain; emits exact enumerated values only."""

    def __init__(self, values, rng):
        super().__init__(list(values), 0.0, float('inf'), rng)

    def sample(self):
        return self.rng.choice(self.elements)


class CodeSampler(ColumnSampler):
    """Code-like strings: pool values, near-variants (case change / one char changed / truncation)."""

    def __init__(self, elements, rng, length=12):
        super().__init__([str(e) for e in elements if e is not None], 0.0, float('inf'), rng)
        self.length = length

    def _rand(self, k):
        return ''.join(self.rng.choice(string.ascii_uppercase + string.digits + '._') for _ in range(k))

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < 0.2:
            return self._rand(r.randint(3, self.length))
        v = r.choice(self.elements)
        u = r.random()
        if u < 0.05:
            v = v.upper() if r.random() < 0.5 else v.lower()
        elif u < 0.10 and v:
            i = r.randrange(len(v))
            v = v[:i] + r.choice(string.ascii_uppercase + string.digits) + v[i + 1:]
        elif u < 0.15 and len(v) > 2:
            a = r.randrange(len(v) - 1)
            b = r.randrange(a + 1, len(v) + 1)
            v = v[:a] + v[b:]
        return v


class YearCodeSampler(ColumnSampler):
    """'YR' + digits (Footnotes.Year / SeriesNotes.Year); listed boundary literals emitted by construction."""

    def __init__(self, elements, rng):
        super().__init__([str(e) for e in elements if e is not None], 0.0, float('inf'), rng)

    def sample(self):
        r = self.rng
        if self.elements and r.random() < 0.5:
            v = r.choice(self.elements)
        else:
            v = 'YR%d' % r.randint(1960, 2015)
        if r.random() < 0.10:
            if r.random() < 0.5:
                base = v[2:] if v[:2].lower() == 'yr' else re.sub(r'^\D+', '', v)
                v = ('yr' if r.random() < 0.5 else 'Yr') + (base or str(r.randint(1960, 2015)))
            else:
                v = v[:-1] + str(r.randrange(10))
        return v


class FixedLengthCodeSampler(ColumnSampler):
    """Code-like strings of a fixed length (e.g. Country.CountryCode, length 3)."""

    def __init__(self, elements, rng, length=3):
        super().__init__([str(e) for e in elements if e is not None], 0.0, float('inf'), rng)
        self.length = length

    def _rand(self):
        alpha = string.ascii_uppercase
        return ''.join(self.rng.choice(alpha if i < 2 else alpha + string.digits)
                       for i in range(self.length))

    def sample(self):
        r = self.rng
        for _ in range(3):
            v = self._rand()
            if v not in self.elements:
                return v
        if self.elements:
            v = r.choice(self.elements)
            if len(v) == self.length:
                return v[:2] + str(r.randrange(10))
        return self._rand()


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


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, domain: dict = None) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    domain = domain or {}
    els = [e for e in elements if rng.random() < 0.9]
    if domain.get('like_prefix') == 'YR%' and not domain.get('enum'):
        extra = list(domain.get('boundary') or [])
        return YearCodeSampler([str(e) for e in els if e is not None] + [str(x) for x in extra], rng)
    if domain.get('enum'):
        return EnumSampler(domain['enum'], rng)
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
        lo, hi = domain.get('range', (None, None))
        return NumberSampler(els, p, max_l0, rng, scale=4, lo=lo, hi=hi)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        lo, hi = domain.get('range', (None, None))
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, lo=lo, hi=hi)
    if any(k in t for k in ('char', 'text', 'blob')):
        if column.pk_pos > 0 and args and args[0] <= 4:
            return FixedLengthCodeSampler(els + list(domain.get('boundary') or []) + list(domain.get('like') or []),
                                          rng, length=args[0])
        if domain.get('like') or domain.get('boundary'):
            return CodeSampler(els + list(domain.get('like', [])) + list(domain.get('boundary', [])), rng,
                               length=args[0] if args else 20)
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), domain: dict = None) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, domain)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), domain: dict = None) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, domain)
    return [s.sample() for _ in range(n)]
