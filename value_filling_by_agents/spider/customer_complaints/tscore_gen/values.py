"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

ENUMS = {
    ('Staff', 'gender'): ['0', '1'],
    ('Customers', 'customer_type_code'): ['Good Credit Rating', 'Defaults on payments'],
    ('Products', 'product_category_code'): ['Food', 'Book', 'Hardware'],
    ('Complaints', 'complaint_outcome_code'): ['OK', 'ok'],
    ('Complaints', 'complaint_status_code'): ['Closed', 'New', 'Open'],
    ('Complaints', 'complaint_type_code'): ['Product Failure', 'Product Unusable'],
}
DISTINCT_COLUMNS = {
    ('Customers', 'phone_number'), ('Customers', 'email_address'),
    ('Customers', 'address_line_1'), ('Customers', 'address_line_2'),
    ('Customers', 'town_city'),
    ('Products', 'product_name'), ('Staff', 'last_name'),
    ('Complaints', 'complaint_status_code'),
}
TIE_COLUMNS = {
    ('Customers', 'phone_number'): 'ASC',
    ('Customers', 'address_line_2'): 'ASC',
    ('Products', 'product_price'): 'BOTH',
    ('Products', 'product_id'): 'BOTH',
    ('Products', 'product_name'): 'BOTH',
    ('Products', 'product_category_code'): 'DESC',
}
BOUNDARY_COLUMNS = {('Complaints', 'complaint_outcome_code')}
GROUP_SIZE_COLUMNS = {
    ('Products', 'product_name'), ('Products', 'parent_product_id'),
}
UNMATCHED_PARENT = {
    ('Products', 'product_id'): ('Complaints', 'product_id'),
    ('Staff', 'staff_id'): ('Complaints', 'staff_id'),
}
DIFFERENT_VALUE_COLUMNS = {('Products', 'product_price')}

US_STATES = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
             'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
             'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
             'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
             'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
             'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
             'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
             'Wisconsin', 'Wyoming']
CITY_SUFFIXES = ['port', 'berg', 'haven', 'bury', 'ville', 'stad']
STREET_SUFFIXES = ['Street', 'Avenue', 'Road', 'Lane', 'Drive', 'Court', 'Place', 'Way']


def _num(x):
    """Numeric coercion of a value; None when it is not numeric."""
    if isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_numeric(x) -> bool:
    return _num(x) is not None


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
        self.template = self.template or '%Y-%m-%d %H:%M:%S'
        self.full = (dt.datetime(1970, 1, 1), dt.datetime(2015, 12, 31, 23, 59, 59))
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
    """Uniform draw from a fixed enum domain (specification per_column_exceptions)."""

    def __init__(self, values, rng):
        super().__init__(list(values), 1.0, float('inf'), rng)
        self.values = list(values)

    def sample(self):
        return self.rng.choice(self.values)


class BoundarySampler(ColumnSampler):
    """Comparison-boundary sampler: literal, literal-1 step, literal+1 step, plus enum values."""

    def __init__(self, values, rng):
        super().__init__(list(values), 1.0, float('inf'), rng)
        self.values = list(values)
        self.boundary = []
        for v in values:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.boundary += [v, v - 1, v + 1]
            elif isinstance(v, str) and re.fullmatch(r'-?\d+', v):
                i = int(v)
                self.boundary += [str(i), str(i - 1), str(i + 1)]
            else:
                self.boundary.append(v)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.5:
            return r.choice(self.boundary)
        return r.choice(self.values)


class NameSampler(ColumnSampler):
    """Capitalized word of 3-10 letters (varchar_name)."""

    def _word(self):
        k = self.rng.randint(3, 10)
        return self.rng.choice(string.ascii_uppercase) + ''.join(
            self.rng.choice(string.ascii_lowercase) for _ in range(k - 1))

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._word)


class EmailSampler(ColumnSampler):
    """Random local part + '@example.' + {com,org,net} (varchar_email)."""

    def _email(self):
        r = self.rng
        local = ''.join(r.choice(string.ascii_lowercase) for _ in range(r.randint(3, 10)))
        return local + '@example.' + r.choice(['com', 'org', 'net'])

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._email)


class PhoneSampler(ColumnSampler):
    """Random digits with optional separators, length 10-15 (varchar_phone)."""

    def _phone(self):
        r = self.rng
        n = r.randint(10, 15)
        digits = [r.choice(string.digits) for _ in range(n)]
        if r.random() < 0.5:
            return ''.join(digits)
        out = []
        for i, d in enumerate(digits):
            out.append(d)
            if i in (2, 5) and i < n - 1:
                out.append(r.choice(['-', '.', ' ']))
        return ''.join(out)

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._phone)


class AddressSampler(ColumnSampler):
    """Random number + capitalized word + street suffix (varchar_address)."""

    def _addr(self):
        r = self.rng
        num = r.randint(1, 99999)
        word = r.choice(string.ascii_uppercase) + ''.join(
            r.choice(string.ascii_lowercase) for _ in range(r.randint(3, 9)))
        return '%d %s %s' % (num, word, r.choice(STREET_SUFFIXES))

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._addr)


class CitySampler(ColumnSampler):
    """Random capitalized word + suffix (varchar_city)."""

    def _city(self):
        r = self.rng
        word = r.choice(string.ascii_uppercase) + ''.join(
            r.choice(string.ascii_lowercase) for _ in range(r.randint(3, 9)))
        return word + r.choice(CITY_SUFFIXES)

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._city)


class StateSampler(ColumnSampler):
    """Uniform from a fixed list of US state names (varchar_state)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return r.choice(US_STATES)


class PriceSampler(ColumnSampler):
    """Uniform random decimal in [0.01, 200.00] rounded to 4 places (decimal_price)."""

    def __init__(self, elements, p, max_l0, rng):
        super().__init__([e for e in elements if _is_numeric(e)], p, max_l0, rng)

    def _price(self):
        return round(self.rng.uniform(0.01, 200.00), 4)

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return round(float(r.choice(self.elements)), 4)
        return self._fresh_or_reuse(self._price)


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


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]


def make_spec_sampler(table: str, column, literal_pool: list, original_values: list, rng,
                      null_share: float, distinct_count: int) -> ColumnSampler:
    """Build the sampler for one column, honouring the specification exceptions."""
    key = (table, column.name)
    t = (column.type_str or '').lower().strip()
    ov = [v for v in original_values if v is not None]
    pool = [str(v) for v in literal_pool]
    els = list(ov) + pool
    if key in ENUMS:
        if key in BOUNDARY_COLUMNS:
            return BoundarySampler(ENUMS[key], rng)
        return EnumSampler(ENUMS[key], rng)
    max_l0 = float('inf')
    if key in DISTINCT_COLUMNS or key in TIE_COLUMNS or key in GROUP_SIZE_COLUMNS:
        max_l0 = max(1, min(len(els) if els else 3, rng.randint(1, 4)))
    if key in DIFFERENT_VALUE_COLUMNS:
        max_l0 = float('inf')
    p = 0.2
    if column.checked:
        p = 0.0
    if 'price' in column.name.lower() or 'decimal' in t:
        return PriceSampler(els, p, max_l0, rng)
    if 'email' in column.name.lower():
        return EmailSampler(els, p, max_l0, rng)
    if 'phone' in column.name.lower():
        return PhoneSampler(els, p, max_l0, rng)
    if 'address_line' in column.name.lower():
        return AddressSampler(els, p, max_l0, rng)
    if column.name.lower() in ('town_city', 'city'):
        return CitySampler(els, p, max_l0, rng)
    if column.name.lower() == 'state':
        return StateSampler(els, p, max_l0, rng)
    if column.name.lower() in ('first_name', 'last_name') or 'name' in column.name.lower():
        return NameSampler(els, p, max_l0, rng)
    return make_column_sampler(column, els, p, max_l0, rng)


def _nonnull_indices(values: list) -> list:
    return [i for i, v in enumerate(values) if v is not None]


def apply_duplicate_share(values: list, rng, share_lo: float = 0.2, share_hi: float = 0.5) -> list:
    """Force 20-50 % of values to duplicate another row's value (DISTINCT target)."""
    n = len(values)
    if n < 2:
        return values
    nn = _nonnull_indices(values)
    if len(nn) < 2:
        return values
    target = int(round(n * rng.uniform(share_lo, share_hi)))
    target = max(1, min(target, len(nn) - 1))
    idx = list(nn)
    rng.shuffle(idx)
    dup_idx = idx[:target]
    src_idx = idx[target:]
    if not src_idx:
        return values
    for i in dup_idx:
        values[i] = values[rng.choice(src_idx)]
    return values


def apply_tie(values: list, rng, direction: str) -> list:
    """Ensure at least two rows share the value at the listed rank (ORDER target)."""
    n = len(values)
    if n < 2:
        return values
    nn = _nonnull_indices(values)
    if len(nn) < 2:
        return values
    if direction == 'ASC':
        best = min(nn, key=lambda i: (str(values[i]), i))
    elif direction == 'DESC':
        best = max(nn, key=lambda i: (str(values[i]), -i))
    else:
        best = min(nn, key=lambda i: (str(values[i]), i))
        other = max(nn, key=lambda i: (str(values[i]), -i))
        if other != best:
            values[other] = values[best]
        return values
    other = next(i for i in nn if i != best)
    values[other] = values[best]
    return values


def apply_group_sizes(values: list, rng, numeric: bool = False) -> list:
    """Ensure group sizes 1, 2 and >= 3 exist (GROUP target)."""
    n = len(values)
    if n < 6:
        return values
    nn = _nonnull_indices(values)
    if len(nn) < 6:
        return values
    rng.shuffle(nn)
    if numeric:
        nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        base = max(nums) + 1 if nums else 1
        if all(isinstance(v, int) for v in nums):
            base = int(base)
        g1, g2, g3 = base, base + 1, base + 2
    else:
        g1 = 'g1_%d' % rng.randint(0, 10 ** 6)
        g2 = 'g2_%d' % rng.randint(0, 10 ** 6)
        g3 = 'g3_%d' % rng.randint(0, 10 ** 6)
    values[nn[0]] = g1
    values[nn[1]] = g2
    values[nn[2]] = g2
    for i in nn[3:6]:
        values[i] = g3
    return values


def apply_null_rule(values: list, rng, null_share: float, nullable: bool) -> list:
    """NULL rule: share from the compact database, at least one NULL row per nullable column."""
    if not nullable:
        return values
    n = len(values)
    if n == 0:
        return values
    k = int(round(n * null_share))
    if k < 1:
        k = 1
    k = min(k, n)
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:k]:
        values[i] = None
    return values
