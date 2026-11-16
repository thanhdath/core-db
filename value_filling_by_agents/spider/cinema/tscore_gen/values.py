"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224) adapted to the specification rules."""
import datetime as dt
import re
import string

from .spec import like_variant_set, satisfies_rule

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m',
              '%d %b', '%d %B']


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []

    def _fresh_or_reuse(self, draw):
        if self.max_l0 != float('inf') and len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh) if self.fresh else None
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
    """fuzz/number.py with optional value list restrictions from the spec."""

    def __init__(self, elements, p, max_l0, rng, is_int=True, lo=None, hi=None, precision=0):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        if lo is None and self.elements:
            lo = min(self.elements)
        if hi is None and self.elements:
            hi = max(self.elements)
        self.lo = -_MAX if is_int else -1e9
        self.hi = _MAX if is_int else 1e9
        if lo is not None:
            self.lo = float(lo) if lo < self.lo else self.lo
        if hi is not None:
            self.hi = float(hi) if hi > self.hi else self.hi
        if self.elements:
            self.lo = min([self.lo] + [v for v in self.elements])
            self.hi = max([self.hi] + [v for v in self.elements])
        self.rules = []

    def add_rule(self, rule: dict):
        self.rules.append(rule)

    def _cast(self, v):
        if self.is_int:
            return int(round(v))
        return round(v, self.precision) if self.precision else v

    def _fix(self, v):
        """Apply the column rule in Python: nudge towards the valid region or drop to NULL upstream."""
        v = self._cast(v)
        if not self.rules:
            return v
        if all(satisfies_rule(r, v) for r in self.rules):
            return v
        cand = self.elements or []
        cand = sorted({c for c in cand if all(satisfies_rule(r, c) for r in self.rules)})
        if cand:
            return cand[0]
        for delta in (1, -1, 2, -2, 5, -5, 10, -10):
            cv = v + delta
            if all(satisfies_rule(r, cv) for r in self.rules):
                return cv
        return None

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            def draw():
                if self.lo >= self.hi:
                    return self.lo
                if self.is_int:
                    return r.randint(int(self.lo), int(self.hi))
                return r.uniform(self.lo, self.hi)
            v = self._fresh_or_reuse(draw)
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
        return self._fix(v)


class StringSampler(ColumnSampler):
    """fuzz/string.py with LIKE variants added to the element list."""

    def __init__(self, elements, p, max_l0, rng, length=20, prefix=None, suffix=None):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        if prefix:
            extra = list(prefix) + extra
        super().__init__(els + extra, p, max_l0, rng)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.list_max = len(self.elements)
        self.rules = []

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
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*',
               lambda m: m.group(1).title(), s.strip())
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
        if self.template is None:
            for s in strs:
                m = re.match(r'^(\d{1,2}) (\w+)', s)
                if m:
                    self.template = '%d %b'
                    break
        self.template = self.template or '%Y-%m-%d'
        self.full = (dt.datetime(1990, 1, 1), dt.datetime(2000, 1, 1))
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


class NullSampler(ColumnSampler):
    """Wraps a sampler and returns NULL with the requested share."""

    def __init__(self, base: ColumnSampler, null_share: float, rng):
        self.base, self.null_share, self.rng = base, null_share, rng

    def sample(self):
        if self.rng.random() < self.null_share:
            return None
        return self.base.sample()


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, *,
                        int_range=None, float_range=None, like_prefix=None):
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
            return NumberSampler(els, p, max_l0, rng, int_range=None, float_range=None)
        return DateSampler(els, p, max_l0, rng)
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng)
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, int_range=int_range, float_range=None)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        prec = (args[1] if len(args) > 1 else 2) if not is_int else 0
        return NumberSampler(els, p, max_l0, rng, is_int=is_int,
                             lo=(int_range[0] if int_range else None) if is_int else (float_range[0] if float_range else None),
                             hi=(int_range[1] if int_range else None) if is_int else (float_range[1] if float_range else None),
                             precision=prec)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20, prefix=like_prefix)
    return StringSampler(els, p, max_l0, rng, prefix=like_prefix)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')):
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
