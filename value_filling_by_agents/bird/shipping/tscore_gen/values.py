"""Per-type value generators plus specification-aware sampling."""
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

    def __init__(self, elements, p, max_l0, rng, date_range=None):
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
        self.date_range = date_range

    def _draw(self):
        r = self.rng
        if self.date_range is not None:
            lo, hi = self.date_range
        else:
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


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng,
                        date_range=None) -> ColumnSampler:
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
        return DateSampler(els, p, max_l0, rng, date_range=date_range)
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
                  max_l0: float = float('inf'), date_range=None) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, date_range=date_range)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]


def _is_numeric_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('int', 'real', 'float', 'double', 'decimal', 'numeric', 'number', 'year'))


def _is_text_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob', 'varchar')) or t in ('', 'blob')


def _is_date_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'date' in t or 'timestamp' in t


def _like_to_value(pattern: str) -> str:
    """LIKE pattern without '%' -> a concrete value (underscore -> a letter)."""
    v = pattern.replace('%', '')
    return re.sub(r'_', lambda m: 'x', v)


def _near_variants(v: str) -> list:
    """Case / spacing / trailing-character variants of a text value."""
    out = []
    if v:
        out.append(v.lower())
        out.append(v.upper())
        out.append(v + ' x')
        out.append(v + 'x')
        out.append(v[:-1] if len(v) > 1 else v)
        out.append(' ' + v)
        out.append(v.replace(' ', '  '))
    return out


def _step_values(v, type_str: str) -> list:
    """One step on each side of a numeric boundary."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return [v - 1, v + 1]
    return []


def _coerce_like(v, type_str: str):
    if _is_numeric_type(type_str):
        try:
            return int(v) if 'int' in (type_str or '').lower() else float(v)
        except (TypeError, ValueError):
            return v
    return str(v)


def _date_range_from_formula(spec_col, type_str):
    """Extract a (lo, hi) datetime range from the formula source text."""
    if not _is_date_type(type_str):
        return None
    src = spec_col.get('formula_src')
    if not src:
        fn = spec_col.get('formula')
        src = getattr(fn, '__src__', None) if fn is not None else None
    if not src:
        return None
    lo = re.search(r">=\s*'(\d{4}-\d{2}-\d{2})'", src)
    hi = re.search(r"<=\s*'(\d{4}-\d{2}-\d{2})'", src)
    try:
        lo_d = dt.datetime.strptime(lo.group(1), '%Y-%m-%d') if lo else None
        hi_d = dt.datetime.strptime(hi.group(1), '%Y-%m-%d') if hi else None
    except ValueError:
        return None
    if lo_d is None and hi_d is None:
        return None
    return (lo_d or dt.datetime(1800, 1, 1), hi_d or dt.datetime(2100, 1, 1))


def _allowed_pool(column, spec_col, original_values, rng):
    """Build the allowed value pool for a constrained column."""
    type_str = column.type_str or ''
    pool = [v for v in original_values if v is not None]
    for b in spec_col.get('boundary') or []:
        pool.append(b)
        pool.extend(_step_values(b, type_str))
    for p in spec_col.get('like') or []:
        lv = _like_to_value(p)
        pool.append(_coerce_like(lv, type_str))
        if _is_text_type(type_str):
            pool.extend(_near_variants(lv))
    if _is_text_type(type_str):
        for v in list(pool):
            if isinstance(v, str) and rng.random() < 0.15:
                pool.extend(_near_variants(v))
    return pool


def spec_column_values(column, spec_col: dict, n: int, rng, base_sampler: ColumnSampler,
                       original_values: list, *, is_null_target: bool = False,
                       compact_null_share: float = 0.0) -> list:
    """Draw n values for one column honouring the specification by construction."""
    type_str = column.type_str or ''
    boundary = list(spec_col.get('boundary') or [])
    like = list(spec_col.get('like') or [])
    tie = bool(spec_col.get('tie'))
    dup_share = float(spec_col.get('dup_share') or 0.0)
    formula = spec_col.get('formula')
    null_share = spec_col.get('null_share')

    pool = _allowed_pool(column, spec_col, original_values, rng)

    def ok(v):
        if v is None:
            return True
        if formula is not None and not formula(v):
            return False
        return True

    vals: list = []
    planted = []
    for b in boundary:
        planted.append(b)
        planted.extend(_step_values(b, type_str))
    for p in like:
        lv = _coerce_like(_like_to_value(p), type_str)
        planted.append(lv)
        if _is_text_type(type_str):
            planted.extend(_near_variants(lv))
    planted = [v for v in planted if ok(v)]
    rng.shuffle(planted)
    cap = max(0, n // 2)
    for v in planted[:cap]:
        vals.append(v)

    if tie and n > 0:
        cand = [v for v in pool if ok(v)]
        if cand:
            n_tie = max(1, int(n * rng.uniform(0.1, 0.3)))
            n_tie = min(n_tie, max(0, n - len(vals)))
            for _ in range(n_tie):
                vals.append(rng.choice(cand))

    if dup_share > 0 and n > 0:
        cand = [v for v in pool if ok(v)]
        if cand:
            n_dup = max(1, int(n * dup_share))
            n_dup = min(n_dup, max(0, n - len(vals)))
            for _ in range(n_dup):
                vals.append(rng.choice(cand))

    guard = 0
    while len(vals) < n and guard < n * 20 + 100:
        guard += 1
        v = base_sampler.sample()
        if not ok(v):
            cand = [x for x in pool if ok(x)]
            if cand:
                v = rng.choice(cand)
            else:
                continue
        vals.append(v)
    while len(vals) < n:
        cand = [x for x in pool if ok(x)]
        if cand:
            vals.append(rng.choice(cand))
        else:
            v = base_sampler.sample()
            vals.append(v if ok(v) else None)

    if not column.notnull and column.pk_pos == 0:
        if is_null_target:
            share = null_share if null_share is not None else 0.1
        else:
            share = compact_null_share
        n_null = int(round(n * share))
        if is_null_target and n_null == 0 and n > 0:
            n_null = 1
        n_null = min(n_null, n)
        if n_null > 0:
            idx = list(range(n))
            rng.shuffle(idx)
            for j in idx[:n_null]:
                vals[j] = None
    return vals
