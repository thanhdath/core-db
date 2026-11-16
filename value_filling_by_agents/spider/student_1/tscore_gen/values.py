"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

from .spec import column_domain, FRESH_SHARE

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y%m']

_SURNAMES = ['ABOZN', 'NABOZNY', 'MADLOCK', 'RAY', 'CHRISSY', 'TARRING', 'KAWA', 'LEIA', 'GORDON',
             'LORIA', 'COVIN', 'ONDERSMA', 'KRIENER', 'MACROSTIE', 'MARROTTE', 'MOYER', 'NIBLER',
             'BARTKUS', 'BIBB', 'BRIGHTBILL', 'BRINE', 'BALBOA', 'ATWOOD', 'AREHART', 'AMY',
             'HALLOWAY', 'PENNINGTON', 'VANDERBILT', 'OKONKWO', 'SZYMANSKI', 'FITZGERALD',
             'MCCALLISTER', 'THORVALDSEN', 'QUINTANILLA', 'ESPINOZA', 'HARGREAVES', 'BLACKWOOD',
             'WETHERBY', 'KOWALCZYK', 'DIMITRIOU', 'ABERNATHY', 'CALLAGHAN', 'VASQUEZ', 'LINDQVIST',
             'MONTGOMERY', 'PETRAKIS', 'HOLLOWAY', 'BRUNSWICK', 'CASTELLANO', 'FAIRCHILD',
             'GALLAGHER', 'HUTCHINSON', 'IRVING', 'JANKOWSKI', 'KENSINGTON', 'LANGSTON',
             'MERRIWEATHER', 'NORTHCUTT', 'OPPENHEIM', 'PRESCOTT', 'RADCLIFFE', 'SUTHERLAND',
             'TREMAINE', 'UNDERWOOD', 'VICKERS', 'WHITTAKER', 'YARBOROUGH', 'ZAMORA']
_GIVEN = ['PATRINA', 'VERTIE', 'BETHEL', 'MEL', 'REYNALDO', 'SHANAE', 'ANTONY', 'FRANKLYN',
          'JEROME', 'GORDON', 'BILLIE', 'MIN', 'KIRK', 'OTHA', 'JERLENE', 'LORIA', 'CHRISSY',
          'MADLOCK', 'RAY', 'ISS', 'CHRYSSY', 'TARRING', 'KAWA', 'LEIA', 'COVIN', 'ONDERSMA',
          'ABIGAIL', 'BARNABY', 'CLEMENTINE', 'DOROTHEA', 'EZEKIEL', 'FLORENCE', 'GIDEON',
          'HARRIET', 'IGNATIUS', 'JOSEPHINE', 'KINGSLEY', 'LILIANA', 'MORDECAI', 'NICODEMUS',
          'OPHELIA', 'PERCIVAL', 'QUINTUS', 'ROSALIND', 'SEBASTIAN', 'TABITHA', 'ULYSSES',
          'VALENTINA', 'WILHELMINA', 'XAVIER', 'YVETTE', 'ZACHARIAH', 'AUGUSTUS', 'BEATRICE',
          'CASIMIR', 'DELPHINE', 'EDMUND', 'FELICITY', 'GREGORY', 'HORTENSE', 'ISADORA',
          'JASPER', 'KATRINA', 'LEOPOLD', 'MAGNOLIA', 'NATHANIEL', 'OLIVE', 'PHINEAS']


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


def _case_flip(rng, v: str) -> str:
    """Flip one or all letters' case; a valid boundary mutation."""
    if rng.random() < 0.5:
        return v.lower() if any(c.isupper() for c in v) else v.upper()
    i = rng.randrange(len(v)) if v else 0
    if not v:
        return v
    c = v[i]
    nc = c.lower() if c.isupper() else (c.upper() if c.islower() else c)
    return v[:i] + nc + v[i + 1:]


def _single_char_edit(rng, v: str) -> str:
    """One of: drop one char, replace one char by an A-Z letter, or duplicate one char."""
    if not v:
        return v
    u = rng.random()
    i = rng.randrange(len(v))
    if u < 0.34:
        return v[:i] + v[i + 1:]
    if u < 0.67:
        return v[:i] + rng.choice(string.ascii_uppercase) + v[i + 1:]
    return v[:i] + v[i] + v[i:]


class NumberSampler(ColumnSampler):
    """fuzz/number.py; keeps the list_max overwrite quirk (number.py:60,67)."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 int_range=None, boundary=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        if int_range is not None:
            self.min, self.max = int(int_range[0]), int(int_range[1])
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)
        self.boundary = [int(v) for v in (boundary or []) if _num(v) is not None]

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        from_boundary = bool(self.boundary) and r.random() < 0.35
        if from_boundary:
            v = float(r.choice(self.boundary))
        elif not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            v = self._fresh_or_reuse(
                lambda: r.randint(int(lo), int(hi)) if self.is_int else r.uniform(lo, hi))
        else:
            v = r.choice(self.elements)
        d = 1 if self.is_int else 0.01
        if from_boundary:
            u = r.random()
            if u < 1 / 3:
                v += d
            elif u < 2 / 3:
                v -= d
        else:
            if r.random() < 1 / 6:
                v += d
            elif r.random() < 1 / 5:
                v -= d
            elif r.random() < 1 / 4:
                v += 2 * d
            elif r.random() < 1 / 3:
                v -= 2 * d
        v = self._cast(v)
        if self.is_int:
            v = max(self.min, min(self.max, v))
        return v


class StringSampler(ColumnSampler):
    """fuzz/string.py (allow_none dropped)."""

    def __init__(self, elements, p, max_l0, rng, length=20, boundary=None, fresh_pool=None):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.boundary = [str(v) for v in (boundary or [])]
        self.fresh_pool = [str(v) for v in (fresh_pool or [])]

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def _fresh_name(self):
        r = self.rng
        pool = self.fresh_pool or (_SURNAMES + _GIVEN)
        v = r.choice(pool)
        u = r.random()
        if u < 0.15:
            v = v.lower()
        elif u < 0.25 and len(v) > 2:
            i = r.randrange(len(v))
            v = v[:i] + v[i + 1:]
        elif u < 0.35:
            v = v + r.choice(string.ascii_uppercase)
        return v

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.35:
            v = r.choice(self.boundary)
            u = r.random()
            if u < 0.5:
                v = _case_flip(r, v)
            elif u < 0.85:
                v = _single_char_edit(r, v)
            return v
        if not self.elements or r.random() < self.p:
            if r.random() < FRESH_SHARE:
                v = self._fresh_or_reuse(self._fresh_name)
            else:
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
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*',
               lambda m: m.group(1).title(), s.strip())
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
        self.template = self.template or '%Y-%m-%d'
        self.full = (dt.datetime(1800, 1, 1), dt.datetime(2100, 1, 1))
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


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, domain=None) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = ([int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2]
            if '(' in t else [])
    dom = domain or {}
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng, boundary=dom.get('pool'),
                             fresh_pool=_SURNAMES + _GIVEN)
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
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, int_range=dom.get('range'),
                             boundary=dom.get('pool'))
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20,
                             boundary=dom.get('pool'), fresh_pool=_SURNAMES + _GIVEN)
    return StringSampler(els, p, max_l0, rng, boundary=dom.get('pool'), fresh_pool=_SURNAMES + _GIVEN)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), domain=None) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, domain=domain)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), domain=None) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng,
                      1 if column_meta.pk_pos else 0, max_l0, domain=domain)
    return [s.sample() for _ in range(n)]
