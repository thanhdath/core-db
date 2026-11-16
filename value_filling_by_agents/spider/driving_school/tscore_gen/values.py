"""Column samplers implementing the value domains by construction."""
import datetime
import random
import re
import string

from . import spec

_DATE_FMT = '%Y-%m-%d %H:%M:%S'
_DT_MIN = datetime.datetime(2015, 1, 1)
_DT_MAX = datetime.datetime(2018, 3, 31, 23, 59, 59)


def _rand_dt(rng):
    span = int((_DT_MAX - _DT_MIN).total_seconds())
    return (_DT_MIN + datetime.timedelta(seconds=rng.randrange(span))).strftime(_DATE_FMT)


def _word(rng, lo=3, hi=20):
    n = rng.randint(lo, hi)
    return ''.join(rng.choice(string.ascii_lowercase) for _ in range(n))


def _near_variant(rng, s):
    """5% near-variant: case flip, trailing space, doubled char."""
    if not s:
        return s
    k = rng.randrange(3)
    if k == 0:
        return s.upper() if rng.random() < 0.5 else s.lower()
    if k == 1:
        return s + ' '
    i = rng.randrange(len(s))
    return s[:i] + s[i] + s[i:]


class ColumnSampler:
    def __init__(self, elements, p, max_l0, rng):
        self.elements = list(elements)
        self.p = p
        self.max_l0 = max_l0
        self.rng = rng
        self._seen = set()

    def _fresh_or_reuse(self, draw):
        v = draw()
        if self.max_l0 != float('inf') and len(self._seen) >= self.max_l0 and self._seen:
            v = self.rng.choice(list(self._seen))
        self._seen.add(v)
        return v

    def sample(self):
        if self.elements and self.rng.random() >= self.p:
            e = str(self.rng.choice(self.elements))
            if self.rng.random() < 0.05:
                return _near_variant(self.rng, e)
            return e
        return self._fresh_or_reuse(self._draw)

    def _draw(self):
        return _word(self.rng)


class EnumSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, enum):
        super().__init__(elements, p, max_l0, rng)
        self.enum = enum

    def _draw(self):
        return self.rng.choice(self.enum)


class BoundaryTextSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, boundary):
        super().__init__(elements, p, max_l0, rng)
        self.boundary = boundary

    def _draw(self):
        return self.rng.choice(self.boundary)


class NameSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, pool):
        super().__init__(elements, p, max_l0, rng)
        self.pool = pool

    def _draw(self):
        return self.rng.choice(self.pool)


class AddressSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, kind):
        super().__init__(elements, p, max_l0, rng)
        self.kind = kind

    def _draw(self):
        r = self.rng
        if self.kind == 'line':
            return '%d %s %s' % (r.randint(1, 9999), r.choice(spec.STREET_WORDS),
                                 r.choice(spec.STREET_SUFFIX))
        if self.kind == 'city':
            return r.choice(spec.CITIES)
        if self.kind == 'state':
            return r.choice(spec.STATES)
        if self.kind == 'country':
            return r.choice(spec.COUNTRIES)
        if self.kind == 'zip':
            return '%05d' % r.randrange(100000)
        return _word(r)


class EmailSampler(ColumnSampler):
    def _draw(self):
        r = self.rng
        dom = r.choice(['example.org', 'example.com'])
        return '%s.%s@%s' % (r.choice(spec.GIVEN_NAMES).lower(),
                             r.choice(spec.SURNAMES).lower(), dom)


class PhoneSampler(ColumnSampler):
    def _draw(self):
        r = self.rng
        digits = ''.join(r.choice(string.digits) for _ in range(r.randint(10, 12)))
        k = r.randrange(4)
        if k == 0:
            return digits
        if k == 1:
            return '+%s(%s)%s' % (digits[:2], digits[2:5], digits[5:])
        if k == 2:
            return '%s-%s-%s' % (digits[:3], digits[3:6], digits[6:])
        return '%sx%s' % (digits[:10], digits[10:] or '1')


class AmountSampler(ColumnSampler):
    def _draw(self):
        return round(self.rng.uniform(0, 10000), 2)


class DateSampler(ColumnSampler):
    def _draw(self):
        return _rand_dt(self.rng)


class NumberSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=False, precision=0, unsigned=False):
        super().__init__(elements, p, max_l0, rng)
        self.is_int = is_int
        self.unsigned = unsigned

    def _draw(self):
        r = self.rng
        if self.is_int:
            v = r.randrange(0 if self.unsigned else -1000, 10000)
            return v
        return round(r.uniform(0 if self.unsigned else -1000, 10000), 2)


class StringSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, length=20):
        super().__init__(elements, p, max_l0, rng)
        self.length = length

    def _draw(self):
        return _word(self.rng, 3, max(3, min(self.length, 20)))


def make_column_sampler(column, elements, p, max_l0, rng):
    """Pick the sampler by declared type and specification domains."""
    key = (column.table, column.name)
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    if key in spec.ENUMS:
        return EnumSampler(els, p, max_l0, rng, spec.ENUMS[key])
    if key in spec.BOUNDARY_TEXT:
        return BoundaryTextSampler(els, p, max_l0, rng, spec.BOUNDARY_TEXT[key])
    if key in (('Customers', 'first_name'), ('Staff', 'first_name'), ('Staff', 'middle_name')):
        return NameSampler(els, p, max_l0, rng, spec.GIVEN_NAMES)
    if key in (('Customers', 'last_name'), ('Staff', 'last_name')):
        return NameSampler(els, p, max_l0, rng, spec.SURNAMES)
    if key == ('Staff', 'nickname'):
        return StringSampler(els, p, max_l0, rng, length=20)
    if column.table == 'Addresses':
        kind = {'line_1_number_building': 'line', 'city': 'city',
                'state_province_county': 'state', 'country': 'country',
                'zip_postcode': 'zip'}.get(column.name)
        if kind:
            return AddressSampler(els, p, max_l0, rng, kind)
    if key == ('Customers', 'email_address'):
        return EmailSampler(els, p, max_l0, rng)
    if key in (('Customers', 'phone_number'), ('Customers', 'cell_mobile_phone_number')):
        return PhoneSampler(els, p, max_l0, rng)
    if key in (('Customers', 'amount_outstanding'), ('Customer_Payments', 'amount_payment'),
               ('Lessons', 'price')):
        return AmountSampler(els, p, max_l0, rng)
    if 'date' in t or 'timestamp' in t:
        return DateSampler(els, p, max_l0, rng)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        return NumberSampler(els, p, max_l0, rng, is_int='int' in t)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool, original_values, p, rng, n_pk, max_l0=float('inf')):
    """Per-column initialisation."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng)


def random_values_for_a_column(column_meta, literal_pool, n, rng, *, original_values=(),
                               p=0.2, max_l0=float('inf')):
    """Initialise one column sampler and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng,
                      1 if column_meta.pk_pos else 0, max_l0=max_l0)
    return [s.sample() for _ in range(n)]
