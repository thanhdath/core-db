"""Per-type value generators: the generation specification is produced by construction."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'

WORDS = ['photo', 'film', 'dinning', 'art', 'cafe', 'print', 'fruit', 'place', 'food', 'music', 'dance',
         'stage', 'light', 'sound', 'screen', 'edit', 'craft', 'story', 'voice', 'scene']

FIRST = ['alba', 'branson', 'buddy', 'clifford', 'connor', 'daryl', 'federico', 'garfield', 'harold',
         'jack', 'kelton', 'reinhold', 'robert', 'rosanna', 'samson', 'blake', 'jacques', 'davonte']
LAST = ['ruecker', 'breitenberg', 'quigley', 'torp', 'watsica', 'hansen', 'roosevelt', 'uhuels',
        'jerde', 'johnson', 'dalton', 'hickle', 'heathcote', 'eleannon', 'keanu', 'clemens']

STATES = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware',
          'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
          'Louisiana', 'Maine', 'Maryland']

CITY_SUFF = ['berg', 'town', 'ville', 'side', 'port', 'haven', 'mouth', 'shire', 'stad', 'ton']
STREET_SUFF = ['Highway', 'Fall', 'Islands', 'View', 'Greens', 'Union', 'Mission', 'Station']
STREET_CORE = ['Dach', 'Vandervort', 'Izabella', 'Vito', 'Boehm', 'Nathan', 'Lula', 'Jenkins', 'Kuhlman',
               'Hessel']

SERVICE_TYPES = ['provide photo service', 'provide dinning service', 'provide filming service',
                 'provide adv promoting service']
REGION_DESCS = ['Our target market', 'Our largest market', '', 'Our main market']
CURRENCIES = ['EU', 'USD']
STATUS = ['good', 'stop']
PAYMENT_METHODS = ['American E', 'MasterCard', 'Visa']
PAYMENT_DESC = ['credit', 'debit', 'Visa']
QUANTITY_STR = ['1', '2', '3', '4', '5', '6']


class ColumnSampler:
    def __init__(self, elements: list, p: float, max_l0: float, rng):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) >= self.max_l0 and self.fresh:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def sample(self):
        raise NotImplementedError

    def with_duplicates(self, n: int) -> list:
        out = []
        share = self.rng.uniform(0.2, 0.5)
        for _ in range(n):
            if out and self.rng.random() < share:
                out.append(self.rng.choice(out))
            else:
                out.append(self.sample())
        return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class NumberSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = max(self.elements) if self.elements else min(self.max, _MAX)

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


class DecimalSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, lo=0.0, hi=100000000.0):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.lo, self.hi = lo, hi
        self.edges = [0.0, 100.0, 1000000.0, 1000001.0]

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            v = r.choice(self.elements)
        elif r.random() < 0.05:
            v = r.choice(self.edges) + r.choice([-1.0, 0.0, 1.0]) * 0.0001
        else:
            v = self._fresh_or_reuse(lambda: round(r.uniform(self.lo, self.hi), 4))
        v = max(self.lo, min(self.hi, float(v)))
        return round(v, 4)


class StringSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, length=20):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng)

    def _word(self):
        return self.rng.choice(WORDS)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(self._word)
        else:
            v = r.choice(self.elements)
        if r.random() < 0.05:
            u = r.random()
            if u < 0.5:
                v = v.upper() if r.random() < 0.5 else v.lower()
            else:
                v = ' ' + v
        return v


class CitySampler(ColumnSampler):
    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: r.choice(FIRST).title() + r.choice(CITY_SUFF))


class StateSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        if self.elements and r.random() < 0.5:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: r.choice(STATES))


class EmailSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        return self._fresh_or_reuse(
            lambda: '%s.%s@example.%s' % (r.choice(FIRST), r.choice(LAST), r.choice(['com', 'net', 'org'])))


class PhoneSampler(ColumnSampler):
    def sample(self):
        return self._fresh_or_reuse(self._phone)

    def _phone(self):
        r = self.rng
        u = r.random()
        if u < 0.4:
            return '(%03d)%03d-%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000))
        if u < 0.75:
            return '%03d-%03d-%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000))
        return '1-%03d-%03d-%04dx%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000),
                                          r.randrange(10000))


class AddressLineSampler(ColumnSampler):
    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        v = self._fresh_or_reuse(lambda: '%d %s %s' % (r.randrange(1, 9999), r.choice(STREET_CORE),
                                                       r.choice(STREET_SUFF)))
        if r.random() < 0.5:
            v += ' ' + r.choice(['Apt.', 'Suite']) + ' %d' % r.randrange(1, 999)
        return v


class IDSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, taken=None):
        super().__init__(elements, p, max_l0, rng)
        self.taken = set(str(x) for x in (taken or ()))
        self.counter = 0

    def sample(self):
        r = self.rng
        if self.elements and r.random() < 0.15:
            v = r.choice(self.elements)
            if str(v) not in self.taken:
                self.taken.add(str(v))
                return v
        while True:
            self.counter += 1
            width = r.randint(3, 6)
            v = '%0*d' % (width, self.counter)
            if v not in self.taken:
                self.taken.add(v)
                return v


class DateSampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng):
        super().__init__(elements, p, max_l0, rng)
        self.template = '%Y-%m-%d %H:%M:%S'
        self.full = (dt.datetime(1970, 1, 1), dt.datetime(2020, 12, 31, 23, 59, 59))

    def _draw(self):
        r = self.rng
        lo, hi = self.full
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        return d.strftime(self.template)

    def sample(self):
        r = self.rng
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        v = self._fresh_or_reuse(self._draw)
        if r.random() < 0.5:
            u = r.random()
            if u < 0.4:
                v = v + ' '
            elif u < 0.7:
                v = v.lstrip('0')
            else:
                v = v[:len(v) - 1] if len(v) > 1 else v
        return v


class QuantitySampler(ColumnSampler):
    def __init__(self, elements, p, max_l0, rng, as_int=False):
        super().__init__(elements, p, max_l0, rng)
        self.as_int = as_int

    def sample(self):
        r = self.rng
        if self.as_int:
            if self.elements and r.random() < 0.5:
                return max(1, int(float(r.choice(self.elements))))
            return r.randint(1, 10)
        if self.elements and r.random() < 0.5:
            return r.choice(self.elements)
        return r.choice(QUANTITY_STR)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, taken_ids=None) -> ColumnSampler:
    els = [e for e in elements if rng.random() < 0.9]
    name = column.name.lower()
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if name.endswith('_id') or name == 'id':
        if 'int' in t or t == '':
            return NumberSampler(els, p, max_l0, rng, is_int=True)
        return IDSampler(els, p, max_l0, rng, taken=taken_ids)
    if 'email' in name:
        return EmailSampler(els, p, max_l0, rng)
    if 'phone' in name:
        return PhoneSampler(els, p, max_l0, rng)
    if name in ('line_1', 'line_2'):
        return AddressLineSampler(els, p, max_l0, rng)
    if name in ('city_town',):
        return CitySampler(els, p, max_l0, rng)
    if name in ('state_county',):
        return StateSampler(els, p, max_l0, rng)
    if 'quantity' in name:
        return QuantitySampler(els, p, max_l0, rng, as_int=('int' in t and 'varchar' not in t))
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4)
        return DateSampler(els, p, max_l0, rng)
    if 'bool' in t:
        return NumberSampler(els, p, max_l0, rng, scale=1, is_int=True)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4)
    if any(k in t for k in ('decimal', 'numeric')):
        return DecimalSampler(els, p, max_l0, rng)
    if any(k in t for k in ('int', 'float', 'double', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), taken_ids=None) -> ColumnSampler:
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, taken_ids=taken_ids)
