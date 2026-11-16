"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

from .spec import enum_values, has_pattern, parse_ts, fmt_ts, boundary_variants

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

US_STATES = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
             'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
             'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
             'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
             'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
             'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
             'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
             'Wisconsin', 'Wyoming']

_FIRST = ['Ron', 'Gabe', 'Candace', 'Jaden', 'Geovanni', 'Karine', 'Emmanuel', 'Keenan', 'Kacie',
          'Dejuan', 'Leonie', 'Rogelio', 'Eriberto', 'Matteo', 'Sasha', 'Eino', 'Frida', 'Randy',
          'Laverna', 'Kaya', 'Queen', 'Deon', 'Stacy', 'Rebeka']
_LAST = ['Emard', 'Schroeder', 'Schneider', 'Lang', 'Grady', 'Farrell', 'Reilly', 'Kuhic', 'Smith',
         'Johnson', 'Williams', 'Brown', 'Jones', 'Miller', 'Davis', 'Garcia', 'Rodriguez', 'Wilson']
_STREET = ['Elm', 'Sixth', 'City', 'Sam', 'Benz', 'Enisner', 'Roof', 'Kate', 'Main', 'Oak', 'Pine',
           'Maple', 'Cedar', 'Park', 'Lake', 'Hill']
_SUFFIX = ['St', 'Rd', 'Av', 'Blvd', 'Ave', 'Ln', 'Dr']
_CITY_SUFFIX = ['ville', 'town', 'side', 'mouth', 'burgh', 'ton']
_WORDS = ['Lora', 'Jaida', 'Crist', 'Adams', 'Marquardt', 'Joseph', 'Feil', 'Farrell', 'Torphy',
          'Heidenreich', 'Gerhold', 'Huel', 'Nader', 'Abshire', 'Macejkovic', 'Schowalter']


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

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None, boundary=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi_scale = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi_scale, hi_scale)
        if lo is not None:
            self.min = lo
        if hi is not None:
            self.max = hi
        self.boundary = boundary
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.10:
            return self._cast(r.choice(self.boundary))
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
        v = self._cast(v)
        if v < self.min:
            v = self.min
        if v > self.max:
            v = self.max
        return v


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


class EnumSampler(ColumnSampler):
    """Specification enumeration: values drawn from the declared enum list only."""

    def __init__(self, values, p, max_l0, rng, boundary=None):
        super().__init__(list(values), p, max_l0, rng)
        self.boundary = [b for b in (boundary or []) if b in self.elements]

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.25:
            return r.choice(self.boundary)
        return r.choice(self.elements)


class NameSampler(ColumnSampler):
    """varchar_name: random capitalized word pair from a small built-in name pool."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: r.choice(_FIRST) + ' ' + r.choice(_LAST))


class EmailSampler(ColumnSampler):
    """varchar_email: lowercase(firstname) + digits + '@example.' + {com,net,org}."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(
            lambda: r.choice(_FIRST).lower() + str(r.randint(1, 99)) + '@example.' + r.choice(['com', 'net', 'org']))


class PhoneSampler(ColumnSampler):
    """varchar_phone: '###-###-####' or '###.###.####x####'."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        if r.random() < 0.5:
            return '%03d-%03d-%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000))
        return '%03d.%03d.%04dx%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000), r.randrange(10000))


class AddressSampler(ColumnSampler):
    """varchar_address: house number + street word + suffix + optional 'Suite ###'."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        s = '%d %s %s' % (r.randint(1, 99999), r.choice(_STREET), r.choice(_SUFFIX))
        if r.random() < 0.5:
            s += ' Suite %03d' % r.randrange(1000)
        return s


class CitySampler(ColumnSampler):
    """varchar_city: capitalized word + suffix (ville, town, side, mouth)."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return r.choice(_WORDS) + r.choice(_CITY_SUFFIX)


class ZipSampler(ColumnSampler):
    """varchar_zip: 3-5 digit numeric string."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return '%0*d' % (r.randint(3, 5), r.randrange(10 ** r.randint(3, 5)))


class StateSampler(ColumnSampler):
    """varchar_state: random pick from a fixed list of US states."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return r.choice(US_STATES)


class CountrySampler(ColumnSampler):
    """varchar_country: fixed 'USA'."""

    def sample(self):
        return 'USA'


class CodeSampler(ColumnSampler):
    """varchar_code: 2-10 char uppercase token; 10% near-variants of an existing value."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            v = r.choice(self.elements)
            if r.random() < 0.10 and v:
                i = r.randrange(len(v))
                v = v[:i] + r.choice(string.ascii_uppercase) + v[i + 1:]
            return v
        return self._fresh_or_reuse(
            lambda: ''.join(r.choice(string.ascii_uppercase) for _ in range(r.randint(2, 10))))


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

    def __init__(self, elements, p, max_l0, rng, date_min=None, date_max=None):
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
        self.full = (parse_ts(date_min) or dt.datetime(2009, 1, 1),
                     parse_ts(date_max) or dt.datetime(2018, 12, 31, 23, 59, 59))
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
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        if r.random() < 0.10:
            lo, hi = self.full
            return fmt_ts(r.choice([lo, hi]))
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


def _name_kind(col: str) -> str:
    c = col.lower()
    if 'email' in c:
        return 'email'
    if 'phone' in c:
        return 'phone'
    if 'address_details' in c or c == 'address':
        return 'address'
    if 'city' in c:
        return 'city'
    if 'zip' in c or 'postcode' in c:
        return 'zip'
    if 'country' in c:
        return 'country'
    if 'state' in c or 'province' in c or 'county' in c:
        return 'state'
    if 'name' in c:
        return 'name'
    if 'code' in c:
        return 'code'
    return ''


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, spec=None, table=None) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if spec is not None and table is not None:
        ev = enum_values(spec, table, column.name)
        if ev:
            bnd = boundary_variants(spec, table, column.name)
            return EnumSampler(ev, p, max_l0, rng, boundary=bnd)
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4)
        return DateSampler(els, p, max_l0, rng,
                           date_min=(spec or {}).get('date_min'), date_max=(spec or {}).get('date_max'))
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
        lo = hi = boundary = None
        if spec is not None and table is not None and has_pattern(spec, table, column.name, 'rows_with_different_values'):
            lo, hi = 0.01, 9999.99
            boundary = [0.01, 9999.99]
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, lo=lo, hi=hi, boundary=boundary)
    if any(k in t for k in ('char', 'text', 'blob')):
        kind = _name_kind(column.name)
        if kind == 'email':
            return EmailSampler(els, p, max_l0, rng)
        if kind == 'phone':
            return PhoneSampler(els, p, max_l0, rng)
        if kind == 'address':
            return AddressSampler(els, p, max_l0, rng)
        if kind == 'city':
            return CitySampler(els, p, max_l0, rng)
        if kind == 'zip':
            return ZipSampler(els, p, max_l0, rng)
        if kind == 'country':
            return CountrySampler(els, p, max_l0, rng)
        if kind == 'state':
            return StateSampler(els, p, max_l0, rng)
        if kind == 'name':
            return NameSampler(els, p, max_l0, rng)
        if kind == 'code':
            return CodeSampler(els, p, max_l0, rng)
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), spec=None, table=None) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, spec=spec, table=table)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), spec=None, table=None) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, spec=spec, table=table)
    return [s.sample() for _ in range(n)]
