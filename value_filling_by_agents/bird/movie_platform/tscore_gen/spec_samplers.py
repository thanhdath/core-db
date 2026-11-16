"""Specification-aware samplers (implemented by construction, in Python)."""
import datetime as dt
import random
import re
import string

CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_MAX = 2 ** 31 - 1


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_int_type(t: str) -> bool:
    return 'int' in t


def _is_date_type(t: str) -> bool:
    return 'date' in t or 'timestamp' in t


def _is_text_type(t: str) -> bool:
    return any(k in t for k in ('char', 'text', 'clob', 'blob')) or t in ('', 'blob')


class BaseSampler:
    """Common machinery: pools, fresh cap, perturbations."""

    def __init__(self, column, elements, p, max_l0, rng, spec_policy=None):
        self.column = column
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh = []
        self.policy = spec_policy or {}

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def sample(self):
        raise NotImplementedError


class NumberSampler(BaseSampler):
    """Integer / real values inside the specification's domain."""

    def __init__(self, column, elements, p, max_l0, rng, spec_policy=None,
                 lo=None, hi=None, is_int=True, precision=0, boundary=None,
                 boundary_p=0.15):
        nums = [f for f in (_num(e) for e in elements) if f is not None]
        super().__init__(column, nums, p, max_l0, rng, spec_policy)
        self.is_int = is_int
        self.precision = precision
        if lo is None:
            lo = min(nums) if nums else -10 ** 10
        if hi is None:
            hi = max(nums) if nums else 10 ** 10
        self.lo, self.hi = int(lo), int(hi)
        self.list_min = min(nums) if nums else self.lo
        self.list_max = max(nums) if nums else self.hi
        self.boundary = [int(b) for b in (boundary or []) if _num(b) is not None]
        self.boundary_p = boundary_p

    def _cast(self, v):
        if self.is_int:
            return int(round(v))
        return round(v, self.precision) if self.precision else v

    def _draw(self):
        r = self.rng
        full = r.random() < self.p or len(self.elements) <= 1
        lo, hi = (self.lo, self.hi) if full else (self.list_min, self.list_max)
        if self.is_int:
            return r.randint(int(lo), int(hi))
        return r.uniform(lo, hi)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < self.boundary_p:
            return r.choice(self.boundary)
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(self._draw)
        else:
            v = r.choice(self.elements)
        d = 1 if self.is_int else 0.01
        u = r.random()
        if u < 1 / 6:
            v += d
        elif u < 1 / 5:
            v -= d
        elif u < 1 / 4:
            v += 2 * d
        elif u < 1 / 3:
            v -= 2 * d
        v = self._cast(v)
        return max(self.lo, min(self.hi, v))


class StringSampler(BaseSampler):
    """Short text with prefix / suffix / dropped-character variants and LIKE patterns."""

    def __init__(self, column, elements, p, max_l0, rng, spec_policy=None, length=20):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(column, els + extra, p, max_l0, rng, spec_policy)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (3, length))

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def _draw(self):
        r = self.rng
        return self._rand(r.randint(self.lo, self.hi))

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(self._draw)
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
            elif u < 0.8 and len(v) > 1:
                v = v[:-1]
            elif len(v) > 1:
                v = v[1:]
        return v


class DateSampler(BaseSampler):
    """Datetime / date strings between 2009-01-01 and 2020-12-31."""

    def __init__(self, column, elements, p, max_l0, rng, spec_policy=None, with_time=True,
                 boundary=None, boundary_p=0.15, year_bias=None, year_bias_p=0.3):
        super().__init__(column, elements, p, max_l0, rng, spec_policy)
        self.with_time = with_time
        self.fmt = '%Y-%m-%d %H:%M:%S' if with_time else '%Y-%m-%d'
        self.lo = dt.datetime(2009, 1, 1)
        self.hi = dt.datetime(2020, 12, 31, 23, 59, 59)
        self.boundary = [str(b) for b in (boundary or [])]
        self.boundary_p = boundary_p
        self.year_bias = [int(y) for y in (year_bias or [])]
        self.year_bias_p = year_bias_p

    def _draw(self):
        r = self.rng
        if self.year_bias and r.random() < self.year_bias_p:
            y = r.choice(self.year_bias)
            d = dt.datetime(y, r.randint(1, 12), r.randint(1, 28),
                            r.randint(0, 23), r.randint(0, 59), r.randint(0, 59))
            return d.strftime(self.fmt)
        span = int((self.hi - self.lo).total_seconds())
        d = self.lo + dt.timedelta(seconds=r.randint(0, span))
        return d.strftime(self.fmt)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < self.boundary_p:
            return r.choice(self.boundary)
        if not self.elements or r.random() < self.p:
            return self._fresh_or_reuse(self._draw)
        return r.choice(self.elements)


class BoolSampler(BaseSampler):
    """0/1 flags (or '0'/'1' text flags)."""

    def __init__(self, column, elements, p, max_l0, rng, spec_policy=None, as_text=False):
        super().__init__(column, elements, p, max_l0, rng, spec_policy)
        self.vals = ('0', '1') if as_text else (0, 1)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < 0.5:
            return self.vals[0] if r.random() < 0.5 else self.vals[1]
        return r.choice(self.elements)


def _boundary_for(policy: dict) -> list:
    """Boundary literals from a column policy (comparison_boundary payload)."""
    return list(policy.get('comparison_boundary') or [])


def make_spec_sampler(column, elements, p, max_l0, rng, spec_policy=None):
    """Pick the sampler by declared type and specification domain."""
    t = (column.type_str or '').lower().strip()
    pol = spec_policy or {}
    boundary = _boundary_for(pol)
    if t == 'time':
        return StringSampler(column, elements, p, max_l0, rng, pol, length=8)
    if _is_date_type(t):
        with_time = 'timestamp' in t or 'datetime' in t
        years = []
        for b in boundary:
            m = re.match(r'^(\d{4})', str(b))
            if m:
                years.append(int(m.group(1)))
        return DateSampler(column, elements, p, max_l0, rng, pol, with_time=with_time,
                           boundary=boundary, year_bias=years)
    if 'bool' in t:
        return BoolSampler(column, elements, p, max_l0, rng, pol)
    if 'bit' in t:
        return BoolSampler(column, elements, p, max_l0, rng, pol)
    if 'year' in t:
        return NumberSampler(column, elements, p, max_l0, rng, pol, lo=1900, hi=2020,
                             boundary=boundary)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = _is_int_type(t)
        return NumberSampler(column, elements, p, max_l0, rng, pol, is_int=is_int,
                             precision=0 if is_int else 4, boundary=boundary)
    if _is_text_type(t):
        return StringSampler(column, elements, p, max_l0, rng, pol)
    return StringSampler(column, elements, p, max_l0, rng, pol)
