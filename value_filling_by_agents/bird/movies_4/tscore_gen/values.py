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
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t


def _is_real_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'numeric', 'decimal'))


def _is_date_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _is_text_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob')) or t in ('', 'blob')


def _rand_token(rng, lo=3, hi=20) -> str:
    k = rng.randint(lo, hi)
    return ''.join(rng.choice(string.ascii_lowercase) for _ in range(k))


def _rand_sentence(rng, lo=40, hi=250) -> str:
    n = rng.randint(lo, hi)
    words, cur = [], 0
    while cur < n:
        w = _rand_token(rng, 2, 9)
        words.append(w)
        cur += len(w) + 1
    s = ' '.join(words)[:n]
    return s[:1].upper() + s[1:] if s else s


def _rand_date(rng, lo=dt.date(1900, 1, 1), hi=dt.date(2025, 12, 31)) -> str:
    span = (hi - lo).days
    return (lo + dt.timedelta(days=rng.randint(0, span))).isoformat()


def _shift_date(s: str, days: int):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
        return (d + dt.timedelta(days=days)).isoformat()
    except Exception:
        return None


def _like_variants(lit: str) -> list:
    """Values that match a LIKE pattern but differ from the exact literal."""
    out = []
    if lit.endswith('%'):
        base = lit[:-1]
        out.append(base)
        out.append(base + 'x')
        out.append(base.lower())
        out.append(base.upper())
    else:
        out.append(lit + 'x')
        out.append(lit.lower())
        out.append(lit.upper())
        if "'" in lit:
            out.append(lit.replace("'", ''))
            out.append(lit.replace("'", '').lower())
    return out


def _case_variants(v: str) -> list:
    out = [v]
    if v.lower() != v:
        out.append(v.lower())
    if v.upper() != v:
        out.append(v.upper())
    if v[:1].isupper():
        out.append(v[:1].lower() + v[1:])
    else:
        out.append(v[:1].upper() + v[1:])
    return out


class SpecColumnSampler:
    """Wraps a base sampler and injects specification targets by construction."""

    def __init__(self, column, base: ColumnSampler, rng, *, enum=None, num_range=None,
                 boundary_values=None, boundary_dates=None, like_literals=None, equality_values=None,
                 duplicate_share=None, tie_ranks=None, text_long=False):
        self.column = column
        self.base = base
        self.rng = rng
        self.enum = list(enum) if enum else None
        self.num_range = num_range
        self.boundary_values = list(boundary_values) if boundary_values else []
        self.boundary_dates = list(boundary_dates) if boundary_dates else []
        self.like_literals = list(like_literals) if like_literals else []
        self.equality_values = list(equality_values) if equality_values else []
        self.duplicate_share = duplicate_share
        self.tie_ranks = tie_ranks
        self.text_long = text_long
        self._tie_pool: list = []
        self._dup_pool: list = []
        self._n = 0
        self._planted: list = []
        self._build_planted()

    def _build_planted(self):
        r = self.rng
        planted = []
        if self.enum:
            for v in self.enum:
                planted.append(v)
            for v in self.enum:
                for cv in _case_variants(v):
                    if cv not in planted:
                        planted.append(cv)
        for v in self.boundary_values:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if _is_int_type(self.column.type_str):
                for d in (-1, 0, 1):
                    planted.append(int(f) + d)
            else:
                for d in (-1.0, 0.0, 1.0):
                    planted.append(round(f + d, 6))
        for v in self.boundary_dates:
            for d in (-1, 0, 1):
                s = _shift_date(v, d)
                if s is not None:
                    planted.append(s)
        for lit in self.like_literals:
            for v in _like_variants(lit):
                planted.append(v)
        for v in self.equality_values:
            for cv in _case_variants(v):
                planted.append(cv)
        r.shuffle(planted)
        self._planted = planted
        if self.tie_ranks:
            if self.enum:
                self._tie_pool = list(self.enum[:max(1, min(3, len(self.enum)))])
            elif _is_int_type(self.column.type_str):
                self._tie_pool = [r.randint(1, 1000) for _ in range(3)]
            elif _is_real_type(self.column.type_str):
                self._tie_pool = [round(r.uniform(0.0, 200.0), 6) for _ in range(3)]
            elif _is_date_type(self.column.type_str):
                self._tie_pool = [_rand_date(r) for _ in range(3)]
            else:
                self._tie_pool = [_rand_token(r) for _ in range(3)]
        if self.duplicate_share:
            if self.enum:
                self._dup_pool = list(self.enum)
            elif _is_text_type(self.column.type_str):
                self._dup_pool = [_rand_token(r) for _ in range(max(2, r.randint(3, 8)))]
            elif _is_int_type(self.column.type_str):
                self._dup_pool = [r.randint(1, 1000) for _ in range(3)]

    def _clamp(self, v):
        if self.num_range is None or v is None:
            return v
        lo, hi, is_int = self.num_range
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        if lo is not None and f < lo:
            f = lo
        if hi is not None and f > hi:
            f = hi
        return int(round(f)) if is_int else round(f, 6)

    def _fresh(self):
        r = self.rng
        t = self.column.type_str or ''
        if self.enum:
            return r.choice(self.enum)
        if _is_int_type(t):
            if self.num_range:
                lo, hi, _ = self.num_range
                lo = 0 if lo is None else int(lo)
                hi = 1000 if hi is None else int(hi)
                if hi < lo:
                    hi = lo
                return r.randint(lo, hi)
            return r.randint(1, 1000)
        if _is_real_type(t):
            if self.num_range:
                lo, hi, _ = self.num_range
                lo = 0.0 if lo is None else float(lo)
                hi = 200.0 if hi is None else float(hi)
                if hi < lo:
                    hi = lo
                return round(r.uniform(lo, hi), 6)
            return round(r.uniform(0.0, 200.0), 6)
        if _is_date_type(t):
            return _rand_date(r)
        if _is_text_type(t):
            return _rand_sentence(r) if self.text_long else _rand_token(r)
        return self.base.sample()

    def sample(self):
        r = self.rng
        self._n += 1
        if self._planted and self._n <= len(self._planted):
            v = self._planted[self._n - 1]
        elif self.tie_pool_hit():
            v = r.choice(self._tie_pool)
        elif self._dup_pool and r.random() < 0.35:
            v = r.choice(self._dup_pool)
        elif self.enum and r.random() < 0.6:
            v = r.choice(self.enum)
        elif r.random() < 0.5:
            v = self._fresh()
        else:
            v = self.base.sample()
            if self.enum and v not in self.enum:
                v = r.choice(self.enum)
        return self._clamp(v)

    def tie_pool_hit(self) -> bool:
        return bool(self._tie_pool) and self.rng.random() < 0.25


def make_spec_sampler(column, base: ColumnSampler, rng, exceptions: list, enum=None, num_range=None) -> SpecColumnSampler:
    """Build a SpecColumnSampler from the per-column exceptions of the specification."""
    boundary_values, boundary_dates, like_literals, equality_values = [], [], [], []
    duplicate_share, tie_ranks = None, None
    for ex in exceptions or []:
        pat = ex.get('pattern')
        tg = ex.get('targets', {}) or {}
        if pat == 'comparison_boundary':
            for v in tg.get('values', []) or []:
                if _is_date_type(column.type_str) and isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                    boundary_dates.append(v)
                elif _is_int_type(column.type_str) or _is_real_type(column.type_str):
                    try:
                        boundary_values.append(float(v))
                    except (TypeError, ValueError):
                        equality_values.append(str(v))
                else:
                    equality_values.append(str(v))
        elif pat == 'like_near_variant':
            for v in tg.get('literals', []) or []:
                if _is_date_type(column.type_str):
                    if isinstance(v, str) and v.endswith('%'):
                        y = v[:-1]
                        if re.fullmatch(r'\d{4}', y):
                            boundary_dates.extend([y + '-01-01', y + '-12-31'])
                    else:
                        boundary_dates.append(str(v))
                else:
                    like_literals.append(str(v))
            for v in tg.get('variants', []) or []:
                if _is_date_type(column.type_str):
                    boundary_dates.append(str(v))
                else:
                    equality_values.append(str(v))
        elif pat == 'duplicates_for_distinct':
            duplicate_share = tg.get('duplicate_share', '20-50 %')
        elif pat == 'ties_for_order_limit':
            tie_ranks = tg.get('tie_at_rank', [1])
    text_long = _is_text_type(column.type_str) and column.name.lower() in ('overview', 'tagline', 'homepage')
    return SpecColumnSampler(column, base, rng, enum=enum, num_range=num_range,
                             boundary_values=boundary_values, boundary_dates=boundary_dates,
                             like_literals=like_literals, equality_values=equality_values,
                             duplicate_share=duplicate_share, tie_ranks=tie_ranks, text_long=text_long)
