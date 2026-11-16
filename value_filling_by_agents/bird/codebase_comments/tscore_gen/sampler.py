"""Sampling primitives: per-column pools, fresh values, perturbations, boundaries."""
from __future__ import annotations

import random
import string

from .spec import (
    TICK_LO, TICK_HI, LANG_DOMAIN, LANG_BOUNDARY,
    FLAG_BOUNDARY, STARS_BOUNDARY, FORKS_BOUNDARY, WATCHERS_BOUNDARY,
    FRESH_VALUE_SHARE,
)

_PREFIXES = ['', 'pre', 'x', 'new', 'old', 'tmp', 'a']
_SUFFIXES = ['', '_s', 'x', '1', '2', 'v', 'z', 'Q']
_CHARSET = string.ascii_letters + string.digits + ' '


def _fresh_short(rng: random.Random, lo: int = 3, hi: int = 12) -> str:
    n = rng.randint(lo, hi)
    return ''.join(rng.choice(_CHARSET) for _ in range(n)).strip() or 'x'


def _perturb_str(rng: random.Random, v: str) -> str:
    if not v:
        return _fresh_short(rng)
    u = rng.random()
    if u < 0.2:
        return v + rng.choice(_SUFFIXES)
    if u < 0.4:
        return rng.choice(_PREFIXES) + v
    if u < 0.6:
        return v[:max(0, len(v) - 1)]
    if u < 0.8:
        return v[1:]
    if u < 0.9:
        return v.replace('%', '')
    return v


def _perturb_int(rng: random.Random, v: int) -> int:
    u = rng.random()
    if u < 0.4:
        return v + 1
    if u < 0.7:
        return v - 1
    if u < 0.85:
        return v + 2
    return v - 2


class ColumnPool:
    """Per-column pool: observed + literal pool + fresh values + optional boundary."""

    def __init__(self, column: str, observed: list, pool: list, rng: random.Random,
                 is_int: bool, boundary: list | None = None,
                 max_observed: int | None = None):
        self.column = column
        self.rng = rng
        self.is_int = is_int
        self.observed = [v for v in observed if v is not None]
        self.pool = [v for v in pool if v is not None]
        self.boundary = [b for b in (boundary or []) if b is not None]
        self.max_observed = max_observed
        self.fresh = 0
        self.fresh_cap = rng.randint(3, 12)

    def _fresh(self):
        r = self.rng
        if self.is_int:
            hi = max(self.max_observed or 1000, 1000)
            return r.randint(0, hi)
        return _fresh_short(r)

    def _draw(self):
        r = self.rng
        u = r.random()
        if self.boundary and u < 0.20:
            return r.choice(self.boundary)
        if u < 0.45:
            if self.pool:
                return r.choice(self.pool)
        if u < 0.75:
            if self.observed:
                return r.choice(self.observed)
        if self.fresh < self.fresh_cap or (not self.observed and not self.pool):
            self.fresh += 1
            return self._fresh()
        src = self.observed or self.pool
        return r.choice(src)

    def sample(self, perturb: bool = True):
        v = self._draw()
        if perturb and self.rng.random() < 0.5:
            if self.is_int:
                return _perturb_int(self.rng, int(v))
            return _perturb_str(self.rng, str(v))
        return v


def make_column_pool(schema, table: str, column: str, pool: dict, rng: random.Random,
                     boundary: list | None = None) -> ColumnPool:
    """Build a pool for one column from observed values and literal pool."""
    key = (table, column)
    observed = [v for v in schema.original_values.get(key, []) if v is not None]
    lit = [v for v in pool.get(key, []) if v is not None]
    max_obs = schema.max_ints.get(key)
    is_int = any(isinstance(v, int) and not isinstance(v, bool) for v in observed)
    if not is_int:
        for v in lit:
            if isinstance(v, str) and v.strip().lstrip('-').isdigit():
                is_int = True
                break
    if boundary is not None:
        b = boundary
    else:
        b = []
    return ColumnPool(column, observed, lit, rng, is_int, b, max_obs)


def sample_text(rng: random.Random, pool: list, fresh_share: float = FRESH_VALUE_SHARE) -> str:
    """fresh_value_share: with prob fresh_share a fresh random string, else pool draw."""
    if rng.random() < fresh_share or not pool:
        return _fresh_short(rng)
    return rng.choice(pool)


def sample_ticks(rng: random.Random) -> int:
    return rng.randint(TICK_LO, TICK_HI)


def sample_lang(rng: random.Random) -> str:
    """Values from the enum domain plus the boundary value 'x' (relaxed semantic rule)."""
    return rng.choice(LANG_DOMAIN)


def sample_lang_boundary(rng: random.Random) -> str:
    return rng.choice(LANG_BOUNDARY)


def sample_flag(rng: random.Random) -> int:
    return 1 if rng.random() < 0.5 else 0


def sample_was_compiled(rng: random.Random) -> int:
    return sample_flag(rng)


def sample_comment_is_xml(rng: random.Random) -> int:
    return sample_flag(rng)


def sample_stars(rng: random.Random, heavy_value: int | None = None) -> int:
    if heavy_value is not None and rng.random() < 0.30:
        return heavy_value
    if rng.random() < 0.40:
        return rng.choice(STARS_BOUNDARY)
    return rng.randint(0, 1200)


def sample_forks(rng: random.Random) -> int:
    if rng.random() < 0.40:
        return rng.choice(FORKS_BOUNDARY)
    return rng.randint(0, 1200)


def sample_watchers(rng: random.Random, stars: int | None = None) -> int:
    if stars is not None and rng.random() < 0.6:
        return stars
    if rng.random() < 0.40:
        return rng.choice(WATCHERS_BOUNDARY)
    return rng.randint(0, 1200)
