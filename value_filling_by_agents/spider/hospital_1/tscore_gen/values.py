"""Per-type value generators plus the specification constants (implemented by construction)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_LETTERS = string.ascii_letters
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

BOUNDARY_LITERALS = {
    ('Procedures', 'Cost'): [999, 1000, 1001, 4999, 5000, 5001],
    ('Room', 'Unavailable'): [0, 1],
    ('Room', 'RoomNumber'): [110, 111, 112, 113],
    ('Stay', 'Room'): [110, 111, 112, 113],
    ('Block', 'BlockFloor'): [0, 1, 2],
}
REQUIRED_LITERALS = {
    ('Procedures', 'Cost'): [999, 1000, 1001, 4999, 5000, 5001],
    ('Room', 'RoomNumber'): [110, 111, 112, 113],
    ('Stay', 'Room'): [110, 111, 112, 113],
    ('Block', 'BlockFloor'): [0, 1, 2],
}
PLANTED_STRINGS = {
    ('Physician', 'Name'): ['John Wen', 'john wen'],
}
DUPLICATE_SHARE = {
    ('Physician', 'Name'): 0.30,
    ('Physician', 'Position'): 0.30,
    ('Procedures', 'Name'): 0.30,
    ('Medication', 'Name'): 0.30,
}
GROUP_SIZE_COLUMNS = {('Patient', 'Name'), ('Appointment', 'Patient')}
TIE_COLUMNS = {
    ('Nurse', 'Name'): 'any',
    ('Stay', 'StayStart'): [1, 2],
    ('Department', 'DepartmentID'): [1],
}
NULLABLE_COLUMNS = {
    ('Appointment', 'PrepNurse'): 0.222,
    ('Prescribes', 'Appointment'): 0.333,
    ('Undergoes', 'AssistingNurse'): 0.20,
}
NUMERIC_TEXT_COLUMNS = {('Prescribes', 'Dose'): (1, 20)}
NOT_NULL_COLUMNS = {('Appointment', 'Start'), ('On_Call', 'Nurse')}
BOOLEAN_STORED = {('Room', 'Unavailable'), ('Affiliated_With', 'PrimaryAffiliation'), ('Nurse', 'Registered')}
DATETIME_FORMATS = {
    ('Appointment', 'Start'): '%Y-%m-%d %H:%M',
    ('Appointment', 'End'): '%Y-%m-%d %H:%M',
    ('On_Call', 'OnCallStart'): '%Y-%m-%d %H:%M',
    ('On_Call', 'OnCallEnd'): '%Y-%m-%d %H:%M',
    ('Stay', 'StayStart'): '%Y-%m-%d',
    ('Stay', 'StayEnd'): '%Y-%m-%d',
    ('Trained_In', 'CertificationDate'): '%Y-%m-%d',
    ('Trained_In', 'CertificationExpires'): '%Y-%m-%d',
    ('Undergoes', 'DateUndergoes'): '%Y-%m-%d',
    ('Prescribes', 'Date'): '%Y-%m-%d %H:%M',
}

TABLE_SIZES = {
    'Physician': 9, 'Department': 3, 'Affiliated_With': 11, 'Procedures': 7, 'Trained_In': 15,
    'Patient': 4, 'Nurse': 3, 'Appointment': 9, 'Medication': 5, 'Prescribes': 3, 'Block': 12,
    'Room': 36, 'On_Call': 6, 'Stay': 3, 'Undergoes': 6,
}


def is_numeric_type(type_str: str) -> bool:
    """True for declared numeric SQLite types."""
    t = (type_str or '').lower().strip()
    if not t:
        return False
    return any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))


def safe_float(v, default=0.0) -> float:
    """Coerce any stored value to a float; never raises."""
    if v is None:
        return default
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def safe_int(v, default=1) -> int:
    """Coerce any stored value to an int; never raises."""
    if v is None:
        return default
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


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

    def __init__(self, elements, p, max_l0, rng, scale=None, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        if lo is not None and hi is not None:
            self.min, self.max = lo, hi
        elif is_int:
            self.min, self.max = (1, 1000) if not unsigned else (1, 1000)
        else:
            self.min, self.max = (0.0, 20000.0)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(max(self.elements), self.max) if self.elements else self.max

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)) if self.is_int else r.uniform(lo, hi))
        else:
            v = float(r.choice(self.elements))
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
        self.short = length <= 30
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))

    def _rand(self, k):
        if self.short:
            k = max(3, min(12, k))
            body = ''.join(self.rng.choice(_LETTERS) for _ in range(k - 1))
            return body[:1].upper() + body[1:]
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


class DigitsSampler(ColumnSampler):
    """Numeric-text sampler: emits digit strings only (Dose)."""

    def __init__(self, elements, p, max_l0, rng, lo=1, hi=20):
        els = [str(e) for e in elements if e is not None and str(e).isdigit()]
        super().__init__(els, p, max_l0, rng)
        self.lo, self.hi = lo, hi

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(lambda: str(r.randint(self.lo, self.hi)))
        else:
            v = r.choice(self.elements)
        return str(max(1, safe_int(v, 1)))


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

    def __init__(self, elements, p, max_l0, rng, fmt=None):
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
        self.template = fmt or self.template or '%Y-%m-%d'
        self.full = (dt.datetime(2008, 1, 1), dt.datetime(2008, 12, 31))
        self.n_parsed = len(set(parsed))

    def _draw(self):
        r = self.rng
        lo, hi = self.full
        span = max(1, int((hi - lo).total_seconds()))
        d = lo + dt.timedelta(seconds=r.randint(0, span))
        s = d.strftime(self.template)
        return int(s) if self.as_int and s.isdigit() else s

    def sample(self):
        if self.elements and self.rng.random() < self.p:
            return self.rng.choice(self.elements)
        return self._fresh_or_reuse(self._draw)


class BoolSampler(ColumnSampler):
    """fuzz/bool.py (Bool True/False, Bit 1/0)."""

    def __init__(self, elements, p, max_l0, rng, bit=False):
        super().__init__(elements, p, max_l0, rng)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        v = self.rng.choice(self.elements)
        return 1 if v in (1, True) else 0


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    key = (column.table, column.name)
    if key in NUMERIC_TEXT_COLUMNS:
        lo, hi = NUMERIC_TEXT_COLUMNS[key]
        els = [e for e in elements if e is not None]
        return DigitsSampler(els, p, max_l0, rng, lo, hi)
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == '' or t == 'blob':
        els = [e for e in elements if rng.random() < 0.9]
        return StringSampler(els, p, max_l0, rng)
    if 'date' in t or 'timestamp' in t:
        els = [e for e in elements if rng.random() < 0.9]
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            els = [e for e in els if _num(e) is not None]
            return NumberSampler(els, p, max_l0, rng, scale=4)
        return DateSampler(els, p, max_l0, rng, fmt=DATETIME_FORMATS.get(key))
    if 'bool' in t:
        els = [e for e in elements if rng.random() < 0.9]
        return BoolSampler(els, p, max_l0, rng)
    if 'bit' in t:
        els = [e for e in elements if rng.random() < 0.9]
        return BoolSampler(els, p, max_l0, rng, bit=True)
    if 'year' in t:
        els = [e for e in elements if _num(e) is not None]
        return NumberSampler(els, p, max_l0, rng, scale=4)
    if is_numeric_type(t):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 2)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        els = [f for f in (_num(e) for e in elements) if f is not None]
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t)
    if any(k in t for k in ('char', 'text', 'blob')):
        els = [e for e in elements if rng.random() < 0.9]
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    els = [e for e in elements if rng.random() < 0.9]
    return StringSampler(els, p, max_l0, rng)


def _spec_elements(table: str, column: str, rng) -> list:
    """Specification-driven value pool additions (boundary literals, planted strings)."""
    out = []
    if (table, column) in BOOLEAN_STORED:
        out += [0, 1]
    else:
        for v in BOUNDARY_LITERALS.get((table, column), []):
            out += [v - 1, v, v + 1]
    out += PLANTED_STRINGS.get((table, column), [])
    return out


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224, plus specification value pools."""
    ov = list(original_values)
    spec = _spec_elements(column.table, column.name, rng)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool}) + spec
    if column.pk_pos > 0:
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
