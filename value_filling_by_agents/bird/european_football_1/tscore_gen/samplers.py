"""Specification-driven column samplers (built on the generic tscore_gen.values fuzzers)."""
import datetime as dt
import random
import re
import string

from .values import make_column_sampler

_ALPHA = string.ascii_letters


def _near_variant(v: str, rng: random.Random) -> str:
    """Case change, leading/trailing space or one-character edit of a pool value."""
    if not v:
        return v
    u = rng.random()
    if u < 0.3:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.5:
        return (' ' + v) if rng.random() < 0.5 else (v + ' ')
    if u < 0.75:
        i = rng.randrange(len(v))
        return v[:i] + rng.choice(_ALPHA) + v[i + 1:]
    if u < 0.9 and len(v) > 1:
        i = rng.randrange(len(v))
        return v[:i] + v[i + 1:]
    i = rng.randrange(len(v) + 1)
    return v[:i] + rng.choice(_ALPHA) + v[i:]


def _parse_date(s):
    try:
        return dt.datetime.strptime(str(s), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


class SpecSampler:
    """One column's sampler: pool, domain, NULL rule and near-variants."""

    def __init__(self, column, spec_col: dict, pool_values: list, observed: list, rng: random.Random,
                 nullable: bool, null_share: float):
        self.column = column
        self.spec = spec_col
        self.rng = rng
        self.pattern = spec_col.get('pattern', 'text_short')
        self.nullable = bool(nullable)
        self.null_share = float(null_share) if self.nullable else 0.0
        self.observed = [v for v in observed if v is not None]
        pool = []
        for v in list(spec_col.get('values') or []) + list(pool_values or []) + [str(v) for v in self.observed]:
            if v is not None and str(v) not in pool:
                pool.append(str(v))
        self.pool = pool
        self._fresh: list = []
        self._max_fresh = rng.choice([3, 5, 8, 12, 20])
        self._generic = None
        self._date_lo = _parse_date(spec_col.get('lo', '2020-08-01')) or dt.date(2020, 8, 1)
        self._date_hi = _parse_date(spec_col.get('hi', '2021-06-30')) or dt.date(2021, 6, 30)
        self._boundary = [b for b in (spec_col.get('boundary') or []) if b is not None]
        self._lo = int(spec_col.get('lo', 0)) if isinstance(spec_col.get('lo', 0), (int, float)) else 0
        self._hi = int(spec_col.get('hi', 10)) if isinstance(spec_col.get('hi', 10), (int, float)) else 10
        self._boundary_nums = [int(b) for b in self._boundary if isinstance(b, (int, float))]

    def _generic_sampler(self):
        if self._generic is None:
            self._generic = make_column_sampler(self.column, self.pool, 0.2, float('inf'), self.rng)
        return self._generic

    def _fresh_or_reuse(self, draw):
        if len(self._fresh) > self._max_fresh:
            return self.rng.choice(self._fresh)
        v = draw()
        self._fresh.append(v)
        return v

    def _draw_text(self) -> str:
        r = self.rng
        if self.pool and r.random() < 0.75:
            v = r.choice(self.pool)
            if r.random() < 0.10:
                v = _near_variant(v, r)
            return v
        return self._fresh_or_reuse(lambda: self._generic_sampler().sample())

    def _draw_int(self) -> int:
        r = self.rng
        if self._boundary_nums and r.random() < 0.35:
            return r.choice(self._boundary_nums)
        if self.pool and r.random() < 0.25:
            try:
                return int(float(r.choice(self.pool)))
            except (TypeError, ValueError):
                pass
        lo, hi = self._lo, self._hi
        if hi < lo:
            lo, hi = hi, lo
        return self._fresh_or_reuse(lambda: r.randint(lo, hi))

    def _draw_season(self) -> int:
        r = self.rng
        vals = [int(v) for v in (self.spec.get('values') or []) if str(v).lstrip('-').isdigit()]
        if vals and r.random() < 0.6:
            return r.choice(vals)
        lo, hi = self._lo, self._hi
        if hi < lo:
            lo, hi = hi, lo
        return r.randint(lo, hi)

    def _draw_date(self) -> str:
        r = self.rng
        if self._boundary and r.random() < 0.3:
            return str(r.choice(self._boundary))
        lo, hi = self._date_lo, self._date_hi
        span = (hi - lo).days
        if span < 0:
            lo, hi, span = hi, lo, -span
        d = lo + dt.timedelta(days=r.randint(0, span))
        return d.strftime(self.spec.get('format', '%Y-%m-%d'))

    def _draw_enum(self) -> str:
        r = self.rng
        vals = self.spec.get('values') or self.pool
        if vals:
            return str(r.choice(vals))
        return self._draw_text()

    def sample(self):
        """Draw one value; NULL is a value following the NULL rule."""
        if self.nullable and self.rng.random() < self.null_share:
            return None
        p = self.pattern
        if p in ('text_short', 'text_name', 'primary_key_text'):
            return self._draw_text()
        if p == 'integer_small':
            return self._draw_int()
        if p == 'integer_season':
            return self._draw_season()
        if p == 'date_iso':
            return self._draw_date()
        if p == 'enum_short':
            return self._draw_enum()
        return self._draw_text()


def make_spec_sampler(column, spec_col: dict, pool_values: list, observed: list, rng: random.Random,
                      nullable: bool, null_share: float) -> SpecSampler:
    """Factory used by the instance builder."""
    return SpecSampler(column, spec_col, pool_values, observed, rng, nullable, null_share)
