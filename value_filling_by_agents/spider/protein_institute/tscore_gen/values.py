"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

from . import spec

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


def _to_num(v):
    """Coerce a string to int/float; return None if not numeric."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        s = str(v).strip()
        if re.fullmatch(r'-?\d+', s):
            return int(s)
        return float(s)
    except (TypeError, ValueError):
        return None


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


class NumberSampler(ColumnSampler):
    """fuzz/number.py; keeps the list_max overwrite quirk (number.py:60,67)."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False):
        nums = [f for f in (_to_num(e) for e in elements) if f is not None]
        super().__init__(nums, p, max_l0, rng)
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


class BoundaryNumberSampler(ColumnSampler):
    """Integer/real sampler that always includes the boundary literals."""

    def __init__(self, elements, p, max_l0, rng, boundaries, lo, hi, is_int=True):
        nums = [f for f in (_to_num(e) for e in elements) if f is not None]
        super().__init__(nums, p, max_l0, rng)
        self.boundaries = [b for b in (_to_num(x) for x in boundaries) if b is not None]
        self.lo, self.hi = lo, hi
        self.is_int = is_int
        self._bnd_i = 0

    def _cast(self, v):
        v = _to_num(v)
        if v is None:
            return self.lo
        v = max(self.lo, min(self.hi, v))
        return int(round(v)) if self.is_int else round(v, 4)

    def sample(self):
        r = self.rng
        if self._bnd_i < len(self.boundaries):
            v = self.boundaries[self._bnd_i]
            self._bnd_i += 1
            return self._cast(v)
        if self.elements and r.random() < self.p:
            v = r.choice(self.elements)
        else:
            v = self._fresh_or_reuse(lambda: r.randint(int(self.lo), int(self.hi)) if self.is_int
                                     else r.uniform(self.lo, self.hi))
        d = 1 if self.is_int else 0.1
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


class EnumSampler(ColumnSampler):
    """Enum sampler with case / near variants (spec.TYPE_VALUES)."""

    def __init__(self, elements, p, max_l0, rng, values):
        super().__init__(elements, p, max_l0, rng)
        self.values = list(values)
        self._i = 0

    def sample(self):
        r = self.rng
        if self._i < len(self.values):
            v = self.values[self._i]
            self._i += 1
            return v
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return r.choice(self.values)


class NameSampler(ColumnSampler):
    """Name sampler with explicit group-size construction (group sizes 1, 2, >=3)."""

    def __init__(self, elements, p, max_l0, rng, pool, group_values=None):
        super().__init__(elements, p, max_l0, rng)
        self.pool = list(pool)
        self.group_values = list(group_values) if group_values else []
        self._i = 0

    def sample(self):
        r = self.rng
        if self.group_values:
            if self._i == 0:
                self._i = 1
                return self.group_values[0]
            if self._i in (1, 2):
                self._i += 1
                return self.group_values[1] if len(self.group_values) > 1 else self.group_values[0]
            return self.group_values[2] if len(self.group_values) > 2 else self.group_values[-1]
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        v = r.choice(self.pool)
        u = r.random()
        if u < 0.15:
            v = v.upper()
        elif u < 0.30:
            v = v.lower()
        elif u < 0.40:
            v = v + ' '
        return v


class PercentSampler(ColumnSampler):
    """'<int>%' strings (sequence_identity_to_human_protein)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return '%d%%' % r.randint(1, 99)


class YearRangeSampler(ColumnSampler):
    """'<year1>-<year2>' / '<year1>-present' strings (Years_as_tallest)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        y1 = r.randint(1900, 2010)
        if r.random() < 0.3:
            return '%d\u2013present' % y1
        y2 = r.randint(y1 + 1, 2030)
        return '%d\u2013%d' % (y1, y2)


class AddressSampler(ColumnSampler):
    """'<number> <street name> <suffix>' addresses (Street_address)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return '%d %s' % (r.randint(1, 999), r.choice(spec.STREETS))


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


def _spec_sampler(column, elements, p, max_l0, rng):
    """Return a specification-driven sampler for a column, or None."""
    key = (column.table, column.name)
    t = (column.type_str or '').lower()
    is_int = 'int' in t
    if key in spec.BOUNDARY:
        lo, hi = spec.RANGES.get(key, (-10 ** 6, 10 ** 6))
        return BoundaryNumberSampler(elements, p, max_l0, rng, spec.BOUNDARY[key], lo, hi, is_int=is_int)
    if key == ('Institution', 'Type'):
        return EnumSampler(elements, p, max_l0, rng, spec.TYPE_VALUES)
    if key in spec.GROUP_SIZE_POOL:
        return NameSampler(elements, p, max_l0, rng, spec.NAME_POOL.get(key, spec.GROUP_SIZE_POOL[key]),
                           spec.GROUP_SIZE_POOL[key])
    if key in spec.NAME_POOL:
        return NameSampler(elements, p, max_l0, rng, spec.NAME_POOL[key])
    if key == ('protein', 'sequence_identity_to_human_protein'):
        return PercentSampler(elements, p, max_l0, rng)
    if key == ('building', 'Years_as_tallest'):
        return YearRangeSampler(elements, p, max_l0, rng)
    if key == ('building', 'Street_address'):
        return AddressSampler(elements, p, max_l0, rng)
    if key in spec.RANGES:
        lo, hi = spec.RANGES[key]
        return BoundaryNumberSampler(elements, p, max_l0, rng, [], lo, hi, is_int=is_int)
    return None


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224 (spec samplers take precedence)."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    s = _spec_sampler(column, els, p, max_l0, rng)
    if s is not None:
        return s
    return make_column_sampler(column, els, p, max_l0, rng)


def null_share(table: str, column: str) -> float:
    """NULL share for a (table, column): spec override, else the compact-derived default."""
    return spec.NULL_SHARE.get((table, column), spec.DEFAULT_NULL_SHARE)


def is_nullable(column) -> bool:
    """True iff the schema declares the column nullable and it is not force-NOT-NULL."""
    key = (column.table, column.name)
    if column.pk_pos > 0 or key in spec.FORCE_NOT_NULL:
        return False
    return not column.notnull


def apply_nulls(table: str, column, vals: list, rng) -> list:
    """NULL rule: for every nullable column, each instance gets rows with NULL and rows with non-NULL values (share
    from spec/compact, at least one NULL)."""
    if not is_nullable(column) or not vals:
        return vals
    share = null_share(table, column.name)
    out = [None if rng.random() < share else v for v in vals]
    if all(v is not None for v in out):
        out[rng.randrange(len(out))] = None
    return out


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224), draw n values and apply the NULL rule."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    vals = [s.sample() for _ in range(n)]
    return apply_nulls(column_meta.table, column_meta, vals, rng)
