"""Specification-driven samplers (tscore_gen/specification.json implemented by construction)."""
import re

from .values import (ColumnSampler, EnumSampler, MonthSampler, NumberSampler, StringSampler,
                     _init_sampler, make_column_sampler)


ENUM_POOLS = {
    ('bool', 'name'): ['neg', 'pos'],
    ('no_payment_due', 'bool'): ['neg', 'pos'],
    ('enlist', 'organ'): ['fire_department', 'air_force', 'navy', 'marines',
                          'foreign_legion', 'army', 'peace_corps'],
    ('enrolled', 'school'): ['occ', 'smc', 'ucb', 'ucla', 'ucsd', 'uci'],
}

BOUNDARY_POOLS = {
    ('enlist', 'name'): ['student211', 'STUDENT211'],
    ('longest_absense_from_school', 'name'): ['student348', 'STUDENT348'],
    ('disabled', 'name'): ['student117', 'STUDENT117', 'student180', 'STUDENT180',
                           'n', 'N', 'dent117', 'DENT117', '', 'x',
                           'student281', 'STUDENT281'],
    ('person', 'name'): ['student214', 'STUDENT214', 'student1000', 'STUDENT1000',
                         'student281', 'STUDENT281', 'student124', 'STUDENT124'],
    ('male', 'name'): ['studenT1000', 'student1000', 'stud000', 'STUD000',
                       'studenT1000%', 'student1000%', 'tudenT10', 'tudent10'],
    ('unemployed', 'name'): ['ent1', 'ENT1', 'student180', 'STUDENT180',
                             'student117', 'STUDENT117', 'neg', 'NEG'],
    ('no_payment_due', 'name'): ['neg', 'NEG', 'student160', 'STUDENT160',
                                 'student124', 'STUDENT124', 'student348', 'STUDENT348'],
    ('enrolled', 'name'): ['student281', 'STUDENT281', 'student214', 'STUDENT214',
                           'student211', 'STUDENT211'],
    ('enrolled', 'school'): ['occ', 'OCC', 'ulca', 'ULCA', '', 'x'],
    ('enlist', 'organ'): ['air_force', 'AIR_FORCE', 'foreign_legion', 'FOREIGN_LEGION',
                          'navy', 'NAVY', 'Foreign Legion', 'foreign legion'],
    ('bool', 'name'): ['neg', 'NEG', 'pos', 'POS'],
    ('no_payment_due', 'bool'): ['neg', 'NEG', 'pos', 'POS', 'e', 'E', 'g', 'G'],
}

LIKE_VARIANTS = {
    ('enlist', 'organ'): ['%marines%', '%air_force%', '%navy%'],
}

STRICT_ENUM_COLUMNS = {
    ('bool', 'name'),
    ('no_payment_due', 'bool'),
    ('enlist', 'organ'),
    ('enrolled', 'school'),
}

NULL_SHARES = {
    ('no_payment_due', 'bool'): (0.05, 0.30),
    ('longest_absense_from_school', 'month'): (0.05, 0.30),
}

DUP_SHARES = {
    ('enlist', 'name'): (0.20, 0.50),
    ('longest_absense_from_school', 'name'): (0.20, 0.50),
    ('disabled', 'name'): (0.20, 0.50),
    ('person', 'name'): (0.20, 0.50),
    ('male', 'name'): (0.20, 0.50),
    ('unemployed', 'name'): (0.20, 0.50),
    ('no_payment_due', 'name'): (0.20, 0.50),
    ('enrolled', 'name'): (0.20, 0.50),
    ('filed_for_bankrupcy', 'name'): (0.20, 0.50),
    ('enlist', 'organ'): (0.20, 0.50),
    ('enrolled', 'school'): (0.20, 0.50),
    ('enrolled', 'month'): (0.20, 0.50),
}

TIE_RANKS = {
    ('disabled', 'name'): [5],
    ('longest_absense_from_school', 'month'): [1, 5],
    ('no_payment_due', 'bool'): [1],
}

AGG_TIES = {
    ('enlist', 'organ'): ('DESC', 2),
    ('enrolled', 'school'): ('DESC', 2),
}

INT_RANGES = {
    ('longest_absense_from_school', 'month'): (0, 12),
    ('enrolled', 'month'): (0, 12),
}

TABLE_SIZES = {
    'bool': 2, 'person': 200, 'disabled': 20, 'enlist': 60, 'filed_for_bankrupcy': 20,
    'longest_absense_from_school': 200, 'male': 100, 'no_payment_due': 200,
    'unemployed': 20, 'enrolled': 240,
}


def _is_enum(table: str, col: str) -> bool:
    return (table, col) in ENUM_POOLS


def _is_month(table: str, col: str) -> bool:
    return (table, col) in INT_RANGES


def _is_boundary(table: str, col: str) -> bool:
    return (table, col) in BOUNDARY_POOLS


def _is_like(table: str, col: str) -> bool:
    return (table, col) in LIKE_VARIANTS


def _is_nullable(table: str, col: str) -> bool:
    return (table, col) in NULL_SHARES


def _is_strict_enum(table: str, col: str) -> bool:
    return (table, col) in STRICT_ENUM_COLUMNS


def _dup_share(table: str, col: str, rng) -> float:
    lo, hi = DUP_SHARES.get((table, col), (0.0, 0.0))
    return rng.uniform(lo, hi) if hi > 0 else 0.0


def _null_share(table: str, col: str, rng, observed: float = None) -> float:
    """NULL share: derived from the compact database's observed share, clamped to the spec range, with a floor of one
    NULL row per instance (applied by the caller)."""
    lo, hi = NULL_SHARES.get((table, col), (0.0, 0.0))
    if hi <= 0:
        return 0.0
    if observed is not None:
        return min(hi, max(lo, observed))
    return rng.uniform(lo, hi)


class BoundarySampler(ColumnSampler):
    """Samples from a comparison-boundary pool with occasional fresh values."""

    def __init__(self, elements, p, max_l0, rng, boundary_pool, like_pool=None, unique=False):
        super().__init__(elements, p, max_l0, rng)
        self.boundary = list(dict.fromkeys(boundary_pool))
        self.like = list(like_pool or [])
        self.unique = unique
        self._used = set()
        self._counter = 0

    def _fresh_unique(self):
        r = self.rng
        while True:
            self._counter += 1
            v = 'student%d' % (r.randint(1, 2000) * 1000 + self._counter)
            if v not in self._used:
                self._used.add(v)
                return v

    def sample(self):
        r = self.rng
        u = r.random()
        if u < 0.35 and self.boundary:
            v = r.choice(self.boundary)
            if self.unique:
                if v in self._used:
                    return self._fresh_unique()
                self._used.add(v)
            return v
        if u < 0.45 and self.like:
            return r.choice(self.like)
        if self.elements and r.random() >= self.p:
            v = r.choice(self.elements)
            if self.unique:
                if v in self._used:
                    return self._fresh_unique()
                self._used.add(v)
            return v
        if self.unique:
            return self._fresh_unique()
        return self._fresh_or_reuse(lambda: 'student%d' % r.randint(1, 2000))


class EnumWithBoundarySampler(ColumnSampler):
    """Enum pool with boundary variants and LIKE near-variants."""

    def __init__(self, elements, p, max_l0, rng, enum_pool, boundary_pool, like_pool=None,
                 strict=False):
        super().__init__(elements, p, max_l0, rng)
        self.enum = list(enum_pool)
        self.strict = strict
        if strict:
            allowed = set(self.enum)
            self.boundary = [v for v in boundary_pool if v in allowed]
            self.like = []
        else:
            self.boundary = list(boundary_pool)
            self.like = list(like_pool or [])

    def sample(self):
        r = self.rng
        u = r.random()
        if u < 0.55:
            return r.choice(self.enum)
        if u < 0.75 and self.boundary:
            return r.choice(self.boundary)
        if u < 0.85 and self.like:
            return r.choice(self.like)
        return r.choice(self.enum)


class NullableEnumSampler(ColumnSampler):
    """Enum pool with NULL share (spec: null_rows)."""

    def __init__(self, elements, p, max_l0, rng, enum_pool, null_share):
        super().__init__(elements, p, max_l0, rng)
        self.enum = list(enum_pool)
        self.null_share = null_share

    def sample(self):
        if self.rng.random() < self.null_share:
            return None
        return self.rng.choice(self.enum)


class NullableMonthSampler(ColumnSampler):
    """Month 0..12 with NULL share and boundary values."""

    def __init__(self, elements, p, max_l0, rng, lo, hi, null_share):
        super().__init__(elements, p, max_l0, rng)
        self.lo, self.hi = lo, hi
        self.null_share = null_share

    def sample(self):
        r = self.rng
        if r.random() < self.null_share:
            return None
        u = r.random()
        if u < 0.15:
            return self.lo
        if u < 0.30:
            return self.hi
        return r.randint(self.lo, self.hi)


def make_spec_sampler(table: str, column, literal_pool: list, original_values, p: float,
                      rng, n_pk: int, max_l0: float = float('inf'),
                      observed_null_share: float = None) -> ColumnSampler:
    """Build a sampler honouring the specification for (table, column)."""
    key = (table, column.name)
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30

    is_pk = column.pk_pos > 0

    if key in ENUM_POOLS:
        enum_pool = ENUM_POOLS[key]
        boundary = BOUNDARY_POOLS.get(key, [])
        like = LIKE_VARIANTS.get(key, [])
        if key in NULL_SHARES:
            return NullableEnumSampler(els, p, max_l0, rng, enum_pool,
                                       _null_share(table, column.name, rng, observed_null_share))
        if boundary or like:
            return EnumWithBoundarySampler(els, p, max_l0, rng, enum_pool, boundary, like,
                                           strict=_is_strict_enum(table, column.name))
        return EnumSampler(els, p, max_l0, rng)

    if key in INT_RANGES:
        lo, hi = INT_RANGES[key]
        if key in NULL_SHARES:
            return NullableMonthSampler(els, p, max_l0, rng, lo, hi,
                                        _null_share(table, column.name, rng, observed_null_share))
        return MonthSampler(els, p, max_l0, rng, lo, hi)

    if key in BOUNDARY_POOLS:
        return BoundarySampler(els, p, max_l0, rng, BOUNDARY_POOLS[key],
                               LIKE_VARIANTS.get(key, []), unique=is_pk)

    return make_column_sampler(column, els, p, max_l0, rng)


def plant_duplicates(values: list, share: float, rng) -> list:
    """Replace a fraction of values with repeats of earlier values (spec: duplicates_for_distinct)."""
    if not values or share <= 0:
        return values
    n = len(values)
    n_dup = int(n * share)
    if n_dup <= 0:
        return values
    out = list(values)
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs[:n_dup]:
        j = rng.randrange(n)
        if j != i:
            out[i] = out[j]
    return out


def plant_ties(values: list, ranks: list, rng, direction: str = 'ASC') -> list:
    """Plant ties at the given 1-based ranks of the sorted order (spec: ties_for_order_limit)."""
    if not values or not ranks:
        return values
    out = list(values)
    n = len(out)
    try:
        out.sort(key=lambda v: (v is None, v), reverse=(direction.upper() == 'DESC'))
    except TypeError:
        out.sort(key=lambda v: (v is None, str(v)), reverse=(direction.upper() == 'DESC'))
    for rank in ranks:
        if rank < 1 or rank >= n:
            continue
        out[rank] = out[rank - 1]
    return out


def plant_aggregate_tie(values: list, direction: str, min_groups: int, rng) -> list:
    """Force the top group count to be shared by at least ``min_groups`` groups."""
    if not values:
        return values
    out = list(values)
    counts: dict = {}
    for v in out:
        counts[v] = counts.get(v, 0) + 1
    if len(counts) < min_groups:
        return out
    groups = sorted(counts.items(), key=lambda kv: kv[1], reverse=(direction.upper() == 'DESC'))
    top_count = groups[0][1]
    sharing = [g for g, c in groups if c == top_count]
    if len(sharing) >= min_groups:
        return out
    second = groups[1][0]
    need = top_count - counts[second]
    if need <= 0:
        return out
    top_val = groups[0][0]
    idxs = [i for i, v in enumerate(out) if v == top_val]
    rng.shuffle(idxs)
    for i in idxs[:need]:
        out[i] = second
    return out


def apply_column_rules(table: str, col: str, values: list, rng) -> list:
    """Apply duplicate and tie rules to a sampled column."""
    key = (table, col)
    if key in DUP_SHARES:
        values = plant_duplicates(values, _dup_share(table, col, rng), rng)
    if key in TIE_RANKS:
        direction = 'DESC' if key == ('longest_absense_from_school', 'month') else 'ASC'
        values = plant_ties(values, TIE_RANKS[key], rng, direction)
    if key in AGG_TIES:
        direction, min_groups = AGG_TIES[key]
        values = plant_aggregate_tie(values, direction, min_groups, rng)
    return values


def enforce_duplicate_share(values: list, share: float, rng) -> list:
    """Post-process a column so that at least ``share`` of its rows repeat an earlier value."""
    if not values or share <= 0:
        return values
    n = len(values)
    n_dup = int(n * share)
    if n_dup <= 0:
        return values
    out = list(values)
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs[:n_dup]:
        j = rng.randrange(n)
        if j != i:
            out[i] = out[j]
    return out
