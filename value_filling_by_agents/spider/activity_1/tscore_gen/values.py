"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


def near_variants(v: str) -> list:
    """Case change, one-character edit and single-character typo variants of v."""
    out = []
    if not v:
        return out
    out.append(v.lower())
    out.append(v.upper())
    out.append(v.capitalize())
    for i in range(len(v)):
        out.append(v[:i] + v[i + 1:])
    for i in range(len(v)):
        for ch in ('x', 'q', 'z'):
            out.append(v[:i] + ch + v[i + 1:])
    for i in range(len(v) - 1):
        out.append(v[:i] + v[i + 1] + v[i] + v[i + 2:])
    return out


def like_patterns(v: str) -> list:
    """LIKE patterns for v (with and without '%')."""
    return ['%' + v, v + '%', '%' + v + '%', v]


def _strip_like(v: str) -> str:
    return v.replace('%', '')


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng, nullable: bool = False,
                 null_share: float = 0.0):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.nullable = nullable
        self.null_share = null_share

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def _maybe_null(self, v):
        """NULL rule: nullable columns may emit None with the configured share."""
        if self.nullable and self.rng.random() < self.null_share:
            return None
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
                 formula=None, boundary=None, dup_share=None, nullable=False, null_share=0.0):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng,
                         nullable=nullable, null_share=null_share)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)
        self.formula = formula
        self.boundary = list(boundary or [])
        self.dup_share = dup_share
        self._apply_formula()
        self._pool: list = []
        self._build_pool()

    def _apply_formula(self):
        f = self.formula
        if not f:
            return
        kind, arg = f
        if kind == 'gt':
            self.min = max(self.min, int(arg) + 1)
            self.list_min = max(self.list_min, int(arg) + 1)
        elif kind == 'ge':
            self.min = max(self.min, int(arg))
            self.list_min = max(self.list_min, int(arg))
        elif kind == 'between':
            lo, hi = int(arg[0]), int(arg[1])
            self.min = max(self.min, lo)
            self.max = min(self.max, hi)
            self.list_min = max(self.list_min, lo)
            self.list_max = min(self.list_max, hi)
        if self.min > self.max:
            self.min, self.max = self.max, self.min

    def _build_pool(self):
        """Boundary values (value, value-1, value+1) plus observed values."""
        pool = []
        for b in self.boundary:
            for d in (0, -1, 1):
                v = int(b) + d
                if self.min <= v <= self.max:
                    pool.append(v)
        for e in self.elements:
            v = int(round(e)) if self.is_int else e
            if self.min <= v <= self.max:
                pool.append(v)
        self._pool = pool

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if self.dup_share and self.fresh and r.random() < self.dup_share:
            return self._maybe_null(self._cast(r.choice(self.fresh)))
        if self._pool and r.random() < 0.6:
            v = r.choice(self._pool)
        elif not self.elements or r.random() < self.p:
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
        v = self._cast(v)
        if v < self.min:
            v = self.min
        if v > self.max:
            v = self.max
        return self._maybe_null(v)


class StringSampler(ColumnSampler):
    """fuzz/string.py (allow_none dropped)."""

    def __init__(self, elements, p, max_l0, rng, length=20, targets=None, enum=None,
                 near_variant=False, like=None, dup_share=None, formula=None,
                 nullable=False, null_share=0.0):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng, nullable=nullable, null_share=null_share)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.length = length
        self.targets = list(targets or [])
        self.enum = list(enum or [])
        self.near_variant = near_variant
        self.like = list(like or [])
        self.dup_share = dup_share
        self.formula = formula
        self._pool = self._build_pool()

    def _build_pool(self):
        pool = []
        for t in self.targets:
            pool.append(t)
            if self.near_variant:
                pool.extend(near_variants(_strip_like(t)))
        for e in self.enum:
            pool.append(e)
            if self.near_variant:
                pool.extend(near_variants(e))
        seen, out = set(), []
        for v in pool:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def _fit(self, v: str) -> str:
        f = self.formula
        if f and f[0] == 'len':
            n = int(f[1])
            if len(v) < n:
                v = v + self._rand(n - len(v))
            elif len(v) > n:
                v = v[:n]
        return v

    def sample(self):
        r = self.rng
        if self.dup_share and self.fresh and r.random() < self.dup_share:
            return self._maybe_null(self._fit(r.choice(self.fresh)))
        if self._pool and r.random() < 0.6:
            v = r.choice(self._pool)
        elif not self.elements or r.random() < self.p:
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
        return self._maybe_null(self._fit(v))


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

    def __init__(self, elements, p, max_l0, rng, nullable=False, null_share=0.0):
        super().__init__(elements, p, max_l0, rng, nullable=nullable, null_share=null_share)
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
            return self._maybe_null(self.rng.choice(self.elements))
        return self._maybe_null(self._fresh_or_reuse(self._draw))


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
            return self._maybe_null(e)
        return self._maybe_null('%02d:%02d:%02d' % (r.randrange(24), r.randrange(60), r.randrange(60)))


class BoolSampler(ColumnSampler):
    """fuzz/bool.py (Bool True/False, Bit 1/0)."""

    def __init__(self, elements, p, max_l0, rng, bit=False, nullable=False, null_share=0.0):
        super().__init__(elements, p, max_l0, rng, nullable=nullable, null_share=null_share)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            v = self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        else:
            v = self.rng.choice(self.elements)
        return self._maybe_null(v)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, exc: dict = None,
                        formula=None, nullable: bool = False, null_share: float = 0.0) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    exc = exc or {}
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    dup_share = exc.get('dup_share')
    dup_mid = (dup_share[0] + dup_share[1]) / 2.0 if dup_share else None
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng, nullable=nullable, null_share=null_share)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng, targets=exc.get('targets'), enum=exc.get('enum'),
                             near_variant=exc.get('near_variant', False), like=exc.get('like_patterns'),
                             dup_share=dup_mid, formula=formula, nullable=nullable, null_share=null_share)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4, nullable=nullable, null_share=null_share)
        return DateSampler(els, p, max_l0, rng, nullable=nullable, null_share=null_share)
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng, nullable=nullable, null_share=null_share)
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True, nullable=nullable, null_share=null_share)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4, nullable=nullable, null_share=null_share)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, formula=formula, boundary=exc.get('boundary'),
                             dup_share=dup_mid, nullable=nullable, null_share=null_share)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20,
                             targets=exc.get('targets'), enum=exc.get('enum'),
                             near_variant=exc.get('near_variant', False), like=exc.get('like_patterns'),
                             dup_share=dup_mid, formula=formula, nullable=nullable, null_share=null_share)
    return StringSampler(els, p, max_l0, rng, targets=exc.get('targets'), enum=exc.get('enum'),
                         near_variant=exc.get('near_variant', False), like=exc.get('like_patterns'),
                         dup_share=dup_mid, formula=formula, nullable=nullable, null_share=null_share)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), exc: dict = None, formula=None,
                  nullable: bool = False, null_share: float = 0.0) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224 (round-1: spec exceptions + formula)."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, exc=exc, formula=formula,
                               nullable=nullable, null_share=null_share)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), exc: dict = None,
                               formula=None, nullable: bool = False, null_share: float = 0.0) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, exc=exc, formula=formula, nullable=nullable, null_share=null_share)
    return [s.sample() for _ in range(n)]
