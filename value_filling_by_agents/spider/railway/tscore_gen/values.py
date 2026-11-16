"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng, spec_hook=None):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.spec_hook = spec_hook

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
                 spec_hook=None, range_bounds=None, tie_values=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng, spec_hook)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        if range_bounds:
            lo, hi2 = range_bounds
            self.min, self.max = max(self.min, int(lo)), min(self.max, int(hi2))
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)
        self.tie_values = list(tie_values or [])

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if self.spec_hook is not None:
            v = self.spec_hook(self)
            if v is not None:
                return v
        if self.tie_values and r.random() < 0.25:
            return self._cast(r.choice(self.tie_values))
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
    """fuzz/string.py (allow_none dropped) + LIKE / comparison variant planting."""

    def __init__(self, elements, p, max_l0, rng, length=20, spec_hook=None,
                 like_variants=None, comparison_variants=None, enum_pool=None):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng, spec_hook)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.like_variants = list(like_variants or [])
        self.comparison_variants = list(comparison_variants or [])
        self.enum_pool = list(enum_pool or [])

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def sample(self):
        r = self.rng
        if self.spec_hook is not None:
            v = self.spec_hook(self)
            if v is not None:
                return v
        if self.enum_pool and r.random() < 0.6:
            return r.choice(self.enum_pool)
        if self.like_variants and r.random() < 0.35:
            return r.choice(self.like_variants)
        if self.comparison_variants and r.random() < 0.35:
            return r.choice(self.comparison_variants)
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

    def __init__(self, elements, p, max_l0, rng, spec_hook=None, year_bounds=None):
        super().__init__(elements, p, max_l0, rng, spec_hook)
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
        if year_bounds:
            self.full = (dt.datetime(int(year_bounds[0]), 1, 1), dt.datetime(int(year_bounds[1]), 12, 31))
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
        if self.spec_hook is not None:
            v = self.spec_hook(self)
            if v is not None:
                return v
        if self.elements and self.rng.random() < self.p:
            return self.rng.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


class TimeSampler(ColumnSampler):
    """fuzz/time.py."""

    def sample(self):
        r = self.rng
        if self.spec_hook is not None:
            v = self.spec_hook(self)
            if v is not None:
                return v
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

    def __init__(self, elements, p, max_l0, rng, bit=False, spec_hook=None):
        super().__init__(elements, p, max_l0, rng, spec_hook)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if self.spec_hook is not None:
            v = self.spec_hook(self)
            if v is not None:
                return v
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, **kw) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng, spec_hook=kw.get('spec_hook'))
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng, spec_hook=kw.get('spec_hook'),
                             like_variants=kw.get('like_variants'), comparison_variants=kw.get('comparison_variants'),
                             enum_pool=kw.get('enum_pool'))
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4, spec_hook=kw.get('spec_hook'),
                                 range_bounds=kw.get('range_bounds'), tie_values=kw.get('tie_values'))
        return DateSampler(els, p, max_l0, rng, spec_hook=kw.get('spec_hook'), year_bounds=kw.get('year_bounds'))
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng, spec_hook=kw.get('spec_hook'))
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True, spec_hook=kw.get('spec_hook'))
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4, spec_hook=kw.get('spec_hook'),
                             range_bounds=kw.get('range_bounds'), tie_values=kw.get('tie_values'))
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, spec_hook=kw.get('spec_hook'),
                             range_bounds=kw.get('range_bounds'), tie_values=kw.get('tie_values'))
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20, spec_hook=kw.get('spec_hook'),
                             like_variants=kw.get('like_variants'), comparison_variants=kw.get('comparison_variants'),
                             enum_pool=kw.get('enum_pool'))
    return StringSampler(els, p, max_l0, rng, spec_hook=kw.get('spec_hook'),
                         like_variants=kw.get('like_variants'), comparison_variants=kw.get('comparison_variants'),
                         enum_pool=kw.get('enum_pool'))


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), **kw) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, **kw)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), **kw) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, **kw)
    return [s.sample() for _ in range(n)]
