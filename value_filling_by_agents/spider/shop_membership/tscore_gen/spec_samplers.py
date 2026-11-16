"""Specification-driven per-column samplers."""


class IntRangeSampler:
    """Integer values in [lo, hi] with explicit boundary pools (e.g. Level, Open_year)."""

    def __init__(self, rng, lo: int, hi: int, boundary_pool=(), prefer_boundary: float = 0.0,
                 distinct: int = 0, max_distinct: int = 0, positive: bool = True):
        self.rng = rng
        self.lo, self.hi = lo, hi
        self.boundary_pool = list(boundary_pool)
        self.prefer_boundary = prefer_boundary
        self.distinct = distinct
        self.max_distinct = max_distinct
        self.positive = positive

    def _draw(self):
        r = self.rng
        if self.boundary_pool and r.random() < self.prefer_boundary:
            return r.choice(self.boundary_pool)
        return r.randint(self.lo, self.hi)

    def sample(self, n: int, start: int = 1) -> list:
        out: list = []
        if self.distinct:
            k = 0
            while len(out) < n:
                v = start + k if self.positive else self.lo + k
                if v > self.hi:
                    v = self.lo + (k % max(1, self.hi - self.lo + 1))
                out.append(v)
                k += 1
            return out[:n]
        seen = set()
        for _ in range(n):
            v = self._draw()
            if self.max_distinct and len(seen) >= self.max_distinct and out:
                v = self.rng.choice(out)
            else:
                seen.add(v)
            out.append(v)
        return out


class GroupedIntSampler:
    """Integer values grouped by a label so that group sizes 1, 2, >=3 occur."""

    def __init__(self, rng, lo: int, hi: int, boundary_pool=(), prefer_boundary: float = 0.0,
                 group_sizes=(1, 2, 3)):
        self.rng = rng
        self.lo, self.hi = lo, hi
        self.boundary_pool = list(boundary_pool)
        self.prefer_boundary = prefer_boundary
        self.group_sizes = group_sizes

    def _draw(self):
        r = self.rng
        if self.boundary_pool and r.random() < self.prefer_boundary:
            return r.choice(self.boundary_pool)
        return r.randint(self.lo, self.hi)

    def sample(self, n: int) -> list:
        labels = _group_labels(self.rng, n, self.group_sizes)
        group_val = {}
        for lab in labels:
            if lab not in group_val:
                group_val[lab] = self._draw()
        return [group_val[lab] for lab in labels]


class BoundaryTextSampler:
    """TEXT columns that store numbers (Register_Year, Year, membership_amount)."""

    def __init__(self, rng, lo: int, hi: int, boundary_pool=(), prefer_boundary: float = 0.0,
                 max_distinct: int = 0):
        self.rng = rng
        self.lo, self.hi = lo, hi
        self.boundary_pool = [str(x) for x in boundary_pool]
        self.prefer_boundary = prefer_boundary
        self.max_distinct = max_distinct

    def sample(self, n: int) -> list:
        out: list = []
        seen = set()
        for _ in range(n):
            if self.boundary_pool and self.rng.random() < self.prefer_boundary:
                v = self.rng.choice(self.boundary_pool)
            else:
                v = str(self.rng.randint(self.lo, self.hi))
            if self.max_distinct and len(seen) >= self.max_distinct and out:
                v = self.rng.choice(out)
            else:
                seen.add(v)
            out.append(v)
        return out


class TextBoundarySampler:
    """TEXT year column with group sizes (branch.Open_year)."""

    def __init__(self, rng, lo: int, hi: int, boundary_pool=(), prefer_boundary: float = 0.0,
                 group_sizes=(1, 2, 3)):
        self.rng = rng
        self.lo, self.hi = lo, hi
        self.boundary_pool = [str(x) for x in boundary_pool]
        self.prefer_boundary = prefer_boundary
        self.group_sizes = group_sizes

    def _draw(self):
        r = self.rng
        if self.boundary_pool and r.random() < self.prefer_boundary:
            return r.choice(self.boundary_pool)
        return str(r.randint(self.lo, self.hi))

    def sample(self, n: int) -> list:
        labels = _group_labels(self.rng, n, self.group_sizes)
        group_val = {}
        for lab in labels:
            if lab not in group_val:
                group_val[lab] = self._draw()
        return [group_val[lab] for lab in labels]


class CitySampler:
    """branch.City in {London, Oxford}; pool includes 'london' lower-case variant for LIKE."""

    def __init__(self, rng):
        self.rng = rng

    def sample(self, n: int) -> list:
        vals = ['London', 'London', 'Oxford', 'london']
        return [self.rng.choice(vals) for _ in range(n)]


class TextPoolSampler:
    """Free-text pool (Names, Card_Number, Address, Hometown)."""

    def __init__(self, rng, pool: list, dup_share: float = 0.0, near_variants: list = None,
                 fresh_pool: list = None, max_distinct: int = 0, null_share: float = 0.0):
        self.rng = rng
        self.pool = [str(v) for v in pool if v is not None]
        self.dup_share = dup_share
        self.near_variants = near_variants or []
        self.fresh_pool = fresh_pool or ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon']
        self.max_distinct = max_distinct
        self.null_share = null_share
        self._drawn: list = []

    def _fresh(self) -> str:
        base = self.rng.choice(self.fresh_pool)
        u = self.rng.random()
        if u < 0.3:
            return base + str(self.rng.randint(0, 9))
        if u < 0.6:
            return str(self.rng.randint(0, 9)) + base
        if u < 0.8 and base:
            return base[:-1]
        return base

    def sample(self, n: int) -> list:
        out: list = []
        for _ in range(n):
            if self.rng.random() < self.null_share:
                out.append(None)
                continue
            if self.rng.random() < self.dup_share and self._drawn:
                out.append(self.rng.choice(self._drawn))
                continue
            if self.near_variants and self.rng.random() < 0.15:
                v = self.rng.choice(self.near_variants)
            elif self.pool and self.rng.random() >= 0.3:
                v = self.rng.choice(self.pool)
            else:
                v = self._fresh()
            if self.max_distinct and len(set(x for x in self._drawn if x is not None)) >= self.max_distinct:
                v = self.rng.choice([x for x in self._drawn if x is not None] or [v])
            out.append(v)
            self._drawn.append(v)
        return out


class DupTextSampler:
    """Text pool with a *deterministic* duplicate share in [0.2, 0.5] (DISTINCT targets)."""

    def __init__(self, rng, pool: list, dup_share: float = 0.35, fresh_pool: list = None):
        self.rng = rng
        self.pool = [str(v) for v in pool if v is not None] or ['A', 'B', 'C', 'D', 'E']
        self.dup_share = dup_share
        self.fresh_pool = fresh_pool or ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon']

    def _fresh(self) -> str:
        base = self.rng.choice(self.fresh_pool)
        u = self.rng.random()
        if u < 0.3:
            return base + str(self.rng.randint(0, 9))
        if u < 0.6:
            return str(self.rng.randint(0, 9)) + base
        if u < 0.8 and base:
            return base[:-1]
        return base

    def sample(self, n: int) -> list:
        if n <= 0:
            return []
        lo = -(-n * 2 // 10)
        hi = (n * 5) // 10
        k = int(round(self.dup_share * n))
        k = max(lo, min(hi, k))
        k = min(k, n - 1) if n > 1 else 0
        out: list = []
        for _ in range(n):
            if self.pool and self.rng.random() >= 0.3:
                v = self.rng.choice(self.pool)
            else:
                v = self._fresh()
            out.append(v)
        if k > 0 and len(out) > 1:
            positions = self.rng.sample(range(1, n), k)
            for p in positions:
                out[p] = out[self.rng.randrange(0, p)]
        return out


class GroupedTextSampler:
    """Text pool with group sizes 1, 2, >=3 (branch.Name)."""

    def __init__(self, rng, pool: list, group_sizes=(1, 2, 3)):
        self.rng = rng
        self.pool = [str(v) for v in pool if v is not None] or ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        self.group_sizes = group_sizes

    def sample(self, n: int) -> list:
        labels = _group_labels(self.rng, n, self.group_sizes)
        group_val = {}
        for lab in labels:
            if lab not in group_val:
                group_val[lab] = self.rng.choice(self.pool)
        return [group_val[lab] for lab in labels]


class CardNumberSampler(DupTextSampler):
    """Card_Number: deterministic 20-50% duplicate share."""

    def __init__(self, rng, pool: list):
        super().__init__(rng, pool, dup_share=0.35,
                         fresh_pool=['LE', 'LT', 'RT', 'RE', 'OLB', 'MLB', 'SLB', 'RCB'])


def _group_labels(rng, n: int, want_sizes=(1, 2, 3)) -> list:
    """Assign group labels so that group sizes 1, 2 and >=3 occur (and fill the rest)."""
    labels: list = []
    pos = 0
    remaining = n
    for sz in want_sizes:
        if remaining <= 0:
            break
        take = min(sz, remaining)
        labels.extend([pos] * take)
        remaining -= take
        pos += 1
    while remaining > 0:
        take = min(rng.randint(1, 4), remaining)
        labels.extend([pos] * take)
        remaining -= take
        pos += 1
    rng.shuffle(labels)
    return labels


def sample_group_sizes(rng, n: int, want_sizes=(1, 2, 3)) -> list:
    """Backwards-compatible helper."""
    return _group_labels(rng, n, want_sizes)
