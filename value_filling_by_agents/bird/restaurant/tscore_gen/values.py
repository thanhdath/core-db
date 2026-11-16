"""Per-column value generators driven by the specification's domains."""
import random
import string

from . import specification as S

CHARSET = string.ascii_letters + ' ' + string.digits + '()'


def _variants(v: str, rng: random.Random) -> list:
    """near-variants: case change, truncation prefix/suffix, one-character edit."""
    out = []
    if v:
        out.append(v.upper())
        out.append(v.lower())
        out.append(v[:max(1, len(v) - 1)])
        out.append(v[1:])
        out.append(' ' + v)
        out.append(v + ' ')
    return out


def _safe_choice(rng: random.Random, seq: list):
    """rng.choice guarded against empty sequences."""
    if not seq:
        return None
    return rng.choice(seq)


def _safe_sample(rng: random.Random, seq: list, k: int) -> list:
    """rng.sample guarded against empty sequences and k=0."""
    if not seq or k <= 0:
        return []
    k = min(k, len(seq))
    return rng.sample(seq, k)


def _safe_shuffle(rng: random.Random, seq: list) -> None:
    if seq:
        rng.shuffle(seq)


class BaseSampler:
    def __init__(self, rng: random.Random, pool: list, null_share: float):
        self.rng = rng
        self.pool = self._clean(pool)
        self.null_share = max(0.0, min(1.0, null_share))

    def _clean(self, pool):
        out = []
        for x in pool:
            if x is None:
                continue
            out.append(x)
        return out

    def draw(self):
        """Return one value; NULL with share null_share."""
        if self.rng.random() < self.null_share:
            return None
        return self._draw()

    def _draw(self):
        if not self.pool:
            return None
        return self.rng.choice(self.pool)


class TextSampler(BaseSampler):
    def __init__(self, rng, pool, null_share=0.02, near_variant=0.05, boundary_lits=None,
                 case_variant_only=False):
        super().__init__(rng, pool, null_share)
        self.near_variant = near_variant
        self.boundary_lits = [b for b in (boundary_lits or []) if b is not None]
        self.case_variant_only = case_variant_only
        if not self.pool:
            self.pool = ['unknown']

    def _draw(self):
        r = self.rng
        if self.boundary_lits and r.random() < 0.10:
            return r.choice(self.boundary_lits)
        if r.random() < self.near_variant:
            base = r.choice(self.pool)
            vs = _variants(str(base), r)
            if self.case_variant_only:
                vs = [str(base).upper(), str(base).lower()]
            return r.choice(vs) if vs else str(base)
        if self.case_variant_only and r.random() < 0.15:
            base = str(r.choice(self.pool))
            if self.boundary_lits:
                probe = r.choice(self.boundary_lits)
                return probe.upper() if r.random() < 0.5 else probe.lower()
            return base.upper() if r.random() < 0.5 else base.lower()
        return r.choice(self.pool)


class NumberSampler(BaseSampler):
    def __init__(self, rng, pool, null_share=0.05, lo=1, hi=5000, is_int=True, precision=0,
                 boundary_nums=None):
        super().__init__(rng, pool, null_share)
        self.lo = lo
        self.hi = hi
        self.is_int = is_int
        self.precision = precision
        self.boundary_nums = list(boundary_nums or [])
        self.pool = []
        for x in super()._clean(pool):
            try:
                self.pool.append(float(x) if not is_int else int(float(x)))
            except (TypeError, ValueError):
                pass

    def _draw(self):
        r = self.rng
        if self.boundary_nums and r.random() < 0.12:
            return r.choice(self.boundary_nums)
        if self.pool and r.random() < 0.5:
            v = r.choice(self.pool)
            if self.is_int and r.random() < 0.2:
                v += r.choice([-2, -1, 1, 2])
            return self._cast(v)
        v = r.randint(int(self.lo), int(self.hi)) if self.is_int else r.uniform(self.lo, self.hi)
        if not self.is_int and self.precision:
            v = round(v, self.precision)
        return self._cast(v)

    def _cast(self, v):
        if self.is_int:
            v = int(v)
            if v < self.lo:
                v = int(self.lo)
            if v > self.hi:
                v = int(self.hi)
            return v
        v = float(v)
        if v < self.lo:
            v = float(self.lo)
        if v > self.hi:
            v = float(self.hi)
        return round(v, self.precision) if self.precision else v


class RealSampler(BaseSampler):
    def __init__(self, rng, pool, null_share=0.0, lo=1.0, hi=5.0, precision=1):
        super().__init__(rng, pool, null_share)
        self.lo = lo
        self.hi = hi
        self.precision = precision
        self.pool = []
        for x in super()._clean(pool):
            try:
                self.pool.append(float(x))
            except (TypeError, ValueError):
                pass

    def _draw(self):
        r = self.rng
        if self.pool and r.random() < 0.6:
            return self._round(r.choice(self.pool))
        return self._round(r.uniform(self.lo, self.hi))

    def _round(self, v):
        v = min(self.hi, max(self.lo, float(v)))
        return round(v, self.precision)


def _domain_for(table: str, column: str, declared_type: str) -> str:
    t = (declared_type or '').lower()
    if (table, column) == ('generalinfo', 'review'):
        return 'real_review'
    if any(k in t for k in ('int', 'year')):
        return 'integer'
    if any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number')):
        return 'real'
    return 'text'


def _spec_pool(table: str, column: str) -> list:
    """Specification-based fallback pool for known columns (uncertainty section)."""
    if column == 'food_type':
        return list(S.FOOD_TYPES)
    if column == 'region':
        return list(S.REGIONS)
    if column == 'county':
        return list(S.COUNTIES)
    if column == 'city':
        return list(S.CITIES)
    if column == 'street_name':
        return list(S.STREETS)
    if column == 'label':
        return list(S.LABELS)
    return []


def make_sampler(schema, table: str, column: str, literal_pool: list, spec: dict,
                 rng: random.Random, is_fk_parent=False):
    """Route declared type + spec domain to a sampler for (table, column)."""
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == column)
    dtype = _domain_for(table, column, cm.type_str)
    observed = [v for v in schema.original_values.get((table, column), []) if v is not None]
    literals = list(literal_pool or [])
    key = (table, column)

    boundary = spec['boundary'].get(key)
    boundary_num = spec['boundary_num'].get(key)

    pool = []
    if observed:
        k = min(len(observed), 400)
        pool += _safe_sample(rng, observed, k) if len(observed) > k else list(observed)
    pool += literals
    if not pool:
        pool = _spec_pool(table, column)

    null_share = spec['null_share'].get(key, 0.02)
    if (table, column) not in spec['null_share']:
        null_share = 0.02 if cm.notnull is False else 0.0
    if not cm.notnull:
        null_share = max(null_share, 0.02)
        null_share = min(null_share, 0.30)
    else:
        null_share = 0.0

    if dtype == 'real_review':
        return RealSampler(rng, pool, null_share, lo=1.0, hi=5.0)
    if dtype == 'real':
        return RealSampler(rng, pool, null_share, lo=0.0, hi=1.0, precision=2)
    if dtype == 'integer':
        lo, hi = _integer_range(table, column, cm)
        return NumberSampler(rng, pool, null_share, lo=lo, hi=hi, is_int=True,
                             boundary_nums=boundary_num)
    return TextSampler(rng, [str(x) for x in pool], null_share=null_share,
                       near_variant=0.05, boundary_lits=boundary)


def _integer_range(table, column, cm):
    if cm.pk_pos > 0:
        return 1, 10 ** 6
    if (table, column) == ('location', 'street_num'):
        return 1, 9999
    return 1, 5000
