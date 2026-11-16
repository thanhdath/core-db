"""Per-type value generators, adapted to the generation specification."""
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


class EnumSampler(ColumnSampler):
    """Draw from a fixed enum pool; 5% case variants for text enums."""

    def __init__(self, pool: list, rng, case_variants: bool = True):
        super().__init__(pool, 0.0, float('inf'), rng)
        self.case_variants = case_variants

    def sample(self):
        v = self.rng.choice(self.elements)
        if self.case_variants and isinstance(v, str) and self.rng.random() < 0.05:
            return spec.case_variant(self.rng, v)
        return v


class BoundarySampler(ColumnSampler):
    """Mix of boundary targets, observed values and fresh values inside the rule range."""

    def __init__(self, targets: list, observed: list, rng, rule=None, kind='short'):
        super().__init__(targets + observed, 0.0, float('inf'), rng)
        self.targets = list(targets)
        self.observed = [o for o in observed if o is not None]
        self.rule = rule
        self.kind = kind

    def _fresh(self):
        r = self.rng
        rule = self.rule
        if rule and rule[0] == 'range':
            lo, hi = rule[1], rule[2]
            if isinstance(lo, int) and isinstance(hi, int):
                return r.randint(lo, hi)
            return round(r.uniform(lo, hi), 1)
        if rule and rule[0] == 'min':
            return r.randint(rule[1], rule[1] + 5000)
        if self.kind in ('year',):
            return r.randint(2002, 2013)
        if self.kind in ('percentile',):
            return r.randint(0, 100)
        if self.kind in ('rate',):
            return round(r.uniform(0.0, 100.0), 1)
        if self.kind in ('quantity', 'count'):
            return r.randint(0, 5000)
        if self.kind in ('grad_count',):
            return str(r.randint(0, 2000))
        if self.kind in ('grad_rate',):
            return '%.1f' % r.uniform(0.0, 100.0)
        if self.kind in ('grad_cohort',):
            return str(r.randint(0, 5000))
        if self.kind in ('numeric',):
            return str(r.randint(0, 9999))
        if self.kind in ('rank',):
            return str(r.randint(1, 52))
        if self.kind in ('coord_x',):
            return round(r.uniform(-180.0, -60.0), 6)
        if self.kind in ('coord_y',):
            return round(r.uniform(15.0, 72.0), 6)
        return ''.join(r.choice(CHARSET) for _ in range(r.randint(3, 12)))

    def sample(self):
        r = self.rng
        u = r.random()
        if self.targets and u < 0.35:
            v = r.choice(self.targets)
        elif self.observed and u < 0.6:
            v = r.choice(self.observed)
        else:
            v = self._fresh()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and r.random() < 0.2:
            d = 1 if isinstance(v, int) else 0.1
            v = v + r.choice([-2 * d, -d, d, 2 * d])
            if self.rule and self.rule[0] == 'range':
                lo, hi = self.rule[1], self.rule[2]
                v = max(lo, min(hi, v))
            if isinstance(v, float):
                v = round(v, 1)
        elif isinstance(v, str) and v and r.random() < 0.15:
            u2 = r.random()
            if u2 < 0.3:
                v = v + ''.join(r.choice(CHARSET) for _ in range(3))
            elif u2 < 0.6:
                v = ''.join(r.choice(CHARSET) for _ in range(3)) + v
            elif len(v) > 1:
                v = v[:-1]
        return v


class NameSampler(ColumnSampler):
    """Capitalized words; 5% case variants; small pool for duplicate share."""

    _WORDS = ['University', 'College', 'State', 'Central', 'Northern', 'Southern', 'Eastern', 'Western',
              'Institute', 'Technology', 'Community', 'Technical', 'Auburn', 'Alabama', 'Boston', 'Chicago',
              'Harvard', 'Brown', 'Columbia', 'Cornell', 'Dartmouth', 'Princeton', 'Yale', 'Pennsylvania']

    def __init__(self, targets: list, observed: list, rng, dup: bool = False):
        super().__init__(targets + observed, 0.0, float('inf'), rng)
        self.targets = list(targets)
        self.observed = [o for o in observed if o is not None]
        self.dup = dup
        self.pool: list = []

    def _fresh(self):
        r = self.rng
        k = r.randint(1, 3)
        return ' '.join(r.choice(self._WORDS) for _ in range(k))

    def sample(self):
        r = self.rng
        if self.dup and self.pool and r.random() < 0.4:
            v = r.choice(self.pool)
        elif self.targets and r.random() < 0.3:
            v = r.choice(self.targets)
        elif self.observed and r.random() < 0.3:
            v = r.choice(self.observed)
        else:
            v = self._fresh()
        if self.dup:
            self.pool.append(v)
            if len(self.pool) > 20:
                self.pool.pop(0)
        if isinstance(v, str) and r.random() < 0.05:
            v = spec.case_variant(r, v)
        return v


class UrlSampler(ColumnSampler):
    """www.<token>.edu; 5% duplicate values."""

    def __init__(self, observed: list, rng):
        super().__init__(observed, 0.0, float('inf'), rng)
        self.observed = [o for o in observed if o is not None]
        self.pool: list = []

    def _fresh(self):
        r = self.rng
        tok = ''.join(r.choice(string.ascii_lowercase) for _ in range(r.randint(3, 10)))
        return 'www.%s.edu' % tok

    def sample(self):
        r = self.rng
        if self.pool and r.random() < 0.05:
            v = r.choice(self.pool)
        elif self.observed and r.random() < 0.3:
            v = r.choice(self.observed)
        else:
            v = self._fresh()
        self.pool.append(v)
        if len(self.pool) > 40:
            self.pool.pop(0)
        return v


class PipeListSampler(ColumnSampler):
    """Pipe-joined list of 5-20 random integers."""

    def sample(self):
        r = self.rng
        k = r.randint(5, 20)
        return '|'.join(str(r.randint(1, 999999)) for _ in range(k))


class FlagSampler(ColumnSampler):
    """Choice from ['X', None] with 10% NULL."""

    def sample(self):
        return None if self.rng.random() < 0.1 else 'X'


class EmptyOrXSampler(ColumnSampler):
    """Choice from ['', 'x', None] with 5% NULL."""

    def sample(self):
        r = self.rng
        if r.random() < 0.05:
            return None
        return r.choice(['', 'x'])


class StateSampler(ColumnSampler):
    """52 US state names; 5% case variants; boundary targets included."""

    def __init__(self, targets: list, rng):
        super().__init__(spec.STATES + list(targets), 0.0, float('inf'), rng)
        self.targets = list(targets)

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            v = r.choice(self.targets)
        else:
            v = r.choice(spec.STATES)
        if r.random() < 0.05:
            v = spec.case_variant(r, v)
        return v


class StateAbbrSampler(ColumnSampler):
    """52 two-letter abbreviations; 5% case variants; boundary targets included."""

    def __init__(self, targets: list, rng):
        super().__init__(spec.STATE_ABBR + list(targets), 0.0, float('inf'), rng)
        self.targets = list(targets)

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            v = r.choice(self.targets)
        else:
            v = r.choice(spec.STATE_ABBR)
        if r.random() < 0.05:
            v = spec.case_variant(r, v)
        return v


class StatePostSampler(ColumnSampler):
    """52 postal abbreviations."""

    def sample(self):
        return self.rng.choice(spec.STATE_POST)


class RankSampler(ColumnSampler):
    """Numeric string in [1, 52]."""

    def sample(self):
        return str(self.rng.randint(1, 52))


class NumericStringSampler(ColumnSampler):
    """Numeric string with 1-4 digits and optional one decimal."""

    def sample(self):
        r = self.rng
        if r.random() < 0.5:
            return str(r.randint(0, 9999))
        return '%.1f' % r.uniform(0.0, 9999.0)


class GradCountSampler(ColumnSampler):
    """Numeric string in [0, 2000]; boundary targets included."""

    def __init__(self, targets: list, rng):
        super().__init__(list(targets), 0.0, float('inf'), rng)
        self.targets = list(targets)

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            return r.choice(self.targets)
        return str(r.randint(0, 2000))


class GradRateSampler(ColumnSampler):
    """Numeric string in [0.0, 100.0] with 1 decimal."""

    def sample(self):
        return '%.1f' % self.rng.uniform(0.0, 100.0)


class GradCohortSampler(ColumnSampler):
    """Numeric string in [0, 5000]; small pool for ties / group sizes."""

    def __init__(self, rng, small_pool: bool = False):
        super().__init__([], 0.0, float('inf'), rng)
        self.small_pool = small_pool
        self.pool: list = []

    def sample(self):
        r = self.rng
        if self.small_pool and self.pool and r.random() < 0.5:
            return r.choice(self.pool)
        v = str(r.randint(0, 5000))
        if self.small_pool:
            self.pool.append(v)
            if len(self.pool) > 6:
                self.pool.pop(0)
        return v


class YearSampler(ColumnSampler):
    """Uniform choice from [2002..2013]; boundary targets included."""

    def __init__(self, targets: list, rng):
        super().__init__(list(targets), 0.0, float('inf'), rng)
        self.targets = list(targets)

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            return r.choice(self.targets)
        return r.randint(2002, 2013)


class PercentileSampler(ColumnSampler):
    """Uniform integer in [0, 100]."""

    def sample(self):
        return self.rng.randint(0, 100)


class RateSampler(ColumnSampler):
    """Uniform real in [0.0, 100.0] rounded to 1 decimal."""

    def sample(self):
        return round(self.rng.uniform(0.0, 100.0), 1)


class QuantitySampler(ColumnSampler):
    """Uniform integer in [1, 5000]; boundary targets included."""

    def __init__(self, rng, targets: list = None):
        super().__init__(list(targets or []), 0.0, float('inf'), rng)
        self.targets = list(targets or [])

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            return r.choice(self.targets)
        return r.randint(1, 5000)


class CountSampler(ColumnSampler):
    """Uniform integer in [0, 500]; small pool for ties / different values."""

    def __init__(self, rng, small_pool: bool = False, targets: list = None):
        super().__init__(list(targets or []), 0.0, float('inf'), rng)
        self.small_pool = small_pool
        self.targets = list(targets or [])
        self.pool: list = []

    def sample(self):
        r = self.rng
        if self.targets and r.random() < 0.3:
            return r.choice(self.targets)
        if self.small_pool and self.pool and r.random() < 0.5:
            return r.choice(self.pool)
        v = r.randint(0, 500)
        if self.small_pool:
            self.pool.append(v)
            if len(self.pool) > 6:
                self.pool.pop(0)
        return v


class CoordSampler(ColumnSampler):
    """long_x in [-180.0, -60.0], lat_y in [15.0, 72.0]."""

    def __init__(self, rng, axis: str):
        super().__init__([], 0.0, float('inf'), rng)
        self.axis = axis

    def sample(self):
        r = self.rng
        if self.axis == 'x':
            return round(r.uniform(-180.0, -60.0), 6)
        return round(r.uniform(15.0, 72.0), 6)


class ShortTokenSampler(ColumnSampler):
    """Random token of 3-12 letters; 5% near-duplicate case variants."""

    def sample(self):
        r = self.rng
        v = ''.join(r.choice(string.ascii_letters) for _ in range(r.randint(3, 12)))
        if r.random() < 0.05:
            v = spec.case_variant(r, v)
        return v


def make_spec_sampler(table: str, column: str, column_meta, literal_pool: list,
                      original_values: list, rng) -> ColumnSampler:
    """Build the sampler for one column from the specification."""
    kind = spec.kind_for(table, column)
    targets = spec.boundary_values(table, column)
    observed = [v for v in original_values if v is not None]
    pool = [str(v) for v in literal_pool]
    rule = spec.rule_for(table, column)

    if kind == 'int_pk':
        return None
    if kind == 'int_fk':
        return None
    if kind == 'name':
        return NameSampler(targets, observed, rng, dup=spec.is_dup_column(table, column))
    if kind == 'url':
        return UrlSampler(observed, rng)
    if kind == 'pipe':
        return PipeListSampler([], 0.0, float('inf'), rng)
    if kind == 'flag':
        return FlagSampler([], 0.0, float('inf'), rng)
    if kind == 'empty_or_x':
        return EmptyOrXSampler([], 0.0, float('inf'), rng)
    if kind == 'state':
        return StateSampler(targets, rng)
    if kind == 'state_abbr':
        return StateAbbrSampler(targets, rng)
    if kind == 'state_post':
        return StatePostSampler([], 0.0, float('inf'), rng)
    if kind == 'rank':
        return RankSampler([], 0.0, float('inf'), rng)
    if kind == 'numeric':
        return NumericStringSampler([], 0.0, float('inf'), rng)
    if kind == 'grad_count':
        return GradCountSampler(targets, rng)
    if kind == 'grad_rate':
        return GradRateSampler([], 0.0, float('inf'), rng)
    if kind == 'grad_cohort':
        return GradCohortSampler(rng, small_pool=spec.is_tie_column(table, column)
                                 or spec.is_group_size_column(table, column))
    if kind == 'year':
        return YearSampler(targets, rng)
    if kind == 'percentile':
        return PercentileSampler([], 0.0, float('inf'), rng)
    if kind == 'rate':
        return RateSampler([], 0.0, float('inf'), rng)
    if kind == 'quantity':
        return QuantitySampler(rng, targets=targets)
    if kind == 'count':
        return CountSampler(rng, small_pool=spec.is_tie_column(table, column)
                            or spec.is_diff_column(table, column), targets=targets)
    if kind == 'coord_x':
        return CoordSampler(rng, 'x')
    if kind == 'coord_y':
        return CoordSampler(rng, 'y')
    if kind == 'race':
        return EnumSampler(spec.RACES + [t for t in targets if t not in spec.RACES], rng)
    if kind == 'gender':
        return EnumSampler(spec.GENDERS + [t for t in targets if t not in spec.GENDERS], rng)
    if kind == 'cohort':
        return EnumSampler(spec.COHORTS + [t for t in targets if t not in spec.COHORTS], rng)
    if kind == 'control':
        return EnumSampler(spec.CONTROLS + [t for t in targets if t not in spec.CONTROLS], rng)
    if kind == 'level':
        return EnumSampler(spec.LEVELS + [t for t in targets if t not in spec.LEVELS], rng)
    return BoundarySampler(targets, observed + pool, rng, rule=rule, kind=kind)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224 (kept for compatibility)."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng)


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
    if any(k in char for char in ('char', 'text', 'blob') for k in [char]):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]
