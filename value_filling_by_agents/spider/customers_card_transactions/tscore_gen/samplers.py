"""Specification-driven column samplers."""
import datetime as dt
import random
import re
import string

from .spec import exception_targets, exceptions_for

_ALNUM = string.ascii_letters + string.digits
_TEXT_CHARS = string.ascii_letters + ' ' + string.digits + '.,()'
_CARD_DIGITS = string.digits


def _is_num_type(t: str) -> bool:
    t = (t or '').lower()
    return any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))


def _is_int_type(t: str) -> bool:
    return 'int' in (t or '').lower()


def _is_datetime_type(t: str) -> bool:
    t = (t or '').lower()
    return 'date' in t or 'time' in t or 'timestamp' in t


def _is_card_number(table: str, column: str) -> bool:
    return column.lower() == 'card_number'


def _is_phone(table: str, column: str) -> bool:
    return column.lower() == 'customer_phone'


def _is_email(table: str, column: str) -> bool:
    return column.lower() == 'customer_email'


def _is_address(table: str, column: str) -> bool:
    return column.lower() == 'customer_address'


def _is_account_name(table: str, column: str) -> bool:
    return table.lower() == 'accounts' and column.lower() == 'account_name'


def _is_enum_column(table: str, column: str, spec: dict) -> bool:
    return bool(exception_targets(spec, table, column, 'enum'))


def _enum_values(table: str, column: str, spec: dict) -> list:
    vals = []
    for t in exception_targets(spec, table, column, 'enum'):
        vals.extend(t.get('values', []) or [])
    return vals


def _is_like_pattern(v: str) -> bool:
    """True for LIKE-pattern / substring boundary variants that must not be inserted as data."""
    s = str(v)
    if '%' in s or '_' in s:
        return True
    return False


def _boundary_values(table: str, column: str, spec: dict) -> list:
    """Literal boundary values from comparison_boundary exceptions (LIKE patterns filtered out)."""
    vals = []
    for t in exception_targets(spec, table, column, 'comparison_boundary'):
        for v in (t.get('values', []) or []):
            if not _is_like_pattern(v):
                vals.append(v)
    return vals


def _dup_share(table: str, column: str, spec: dict):
    """Return (lo, hi) duplicate share fraction or None."""
    for t in exception_targets(spec, table, column, 'duplicates_for_distinct'):
        ds = str(t.get('duplicate_share', '')).strip()
        m = re.match(r'(\d+)\s*-\s*(\d+)\s*%', ds)
        if m:
            return int(m.group(1)) / 100.0, int(m.group(2)) / 100.0
        if ds.endswith('%'):
            try:
                v = float(ds[:-1]) / 100.0
                return v, v
            except ValueError:
                pass
    return None


def _rand_token(rng, lo=3, hi=12) -> str:
    k = rng.randint(lo, hi)
    return ''.join(rng.choice(_ALNUM) for _ in range(k))


def _rand_text(rng, maxlen=200) -> str:
    k = rng.randint(20, min(maxlen, 120))
    return ''.join(rng.choice(_TEXT_CHARS) for _ in range(k)).strip() or 'text'


def _near_dup(rng, v: str) -> str:
    """Case flip or one-char edit of an existing value."""
    if not v:
        return v
    u = rng.random()
    if u < 0.4:
        return v.swapcase() if rng.random() < 0.5 else v.upper()
    if u < 0.7 and len(v) > 1:
        i = rng.randrange(len(v))
        return v[:i] + rng.choice(_ALNUM) + v[i + 1:]
    if len(v) > 1:
        i = rng.randrange(len(v))
        return v[:i] + v[i + 1:]
    return v + rng.choice(_ALNUM)


def _rand_phone(rng) -> str:
    fmt = rng.randrange(4)
    d = lambda n: ''.join(rng.choice(string.digits) for _ in range(n))
    if fmt == 0:
        return '(%s)%s-%s' % (d(3), d(3), d(4))
    if fmt == 1:
        return '%s-%s-%sx%s' % (d(3), d(3), d(4), d(5))
    if fmt == 2:
        return '1-%s-%s-%s' % (d(3), d(3), d(4))
    return '+%s(%s)%s' % (d(2), d(1), d(10))


def _rand_email(rng, first: str = '', last: str = '') -> str:
    f = (first or _rand_token(rng, 3, 8)).lower()
    l = (last or _rand_token(rng, 3, 8)).lower()
    dom = rng.choice(['example.com', 'example.net', 'example.org'])
    return '%s.%s@%s' % (f, l, dom)


def _rand_address(rng) -> str:
    street = '%d %s %s' % (rng.randint(1, 9999), _rand_token(rng, 4, 10).title(),
                           rng.choice(['St', 'Ave', 'Blvd', 'Rd', 'Ln', 'Way']))
    city = _rand_token(rng, 4, 12).title()
    st = rng.choice(['VT', 'LA', 'DE', 'NH', 'KY', 'SC', 'CA', 'TX', 'NY', 'FL'])
    zipc = '%05d' % rng.randint(1000, 99999)
    return '%s\n%s, %s %s' % (street, city, st, zipc)


def _rand_card_number(rng) -> str:
    return ''.join(rng.choice(_CARD_DIGITS) for _ in range(16))


def _rand_datetime(rng, lo: dt.datetime, hi: dt.datetime) -> str:
    span = int((hi - lo).total_seconds())
    d = lo + dt.timedelta(seconds=rng.randint(0, max(0, span)))
    return d.strftime('%Y-%m-%d %H:%M:%S')


def _coerce_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class ColumnSampler:
    """Base sampler: holds observed values, pool literals, boundary literals and rng."""

    def __init__(self, table, column, type_str, observed, pool_literals, spec, rng):
        self.table = table
        self.column = column
        self.type_str = type_str or ''
        self.rng = rng
        self.spec = spec
        self.observed = [v for v in (observed or []) if v is not None]
        self.pool = [str(v) for v in (pool_literals or []) if v is not None]
        self.boundary = _boundary_values(table, column, spec)
        self.dup = _dup_share(table, column, spec)
        self.fresh: list = []
        self.max_fresh = rng.randint(3, 40)

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_fresh and self.fresh:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def sample(self, n: int) -> list:
        raise NotImplementedError


class IntSampler(ColumnSampler):
    """Integer columns: uniform [1,10000] with boundary +-1."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        nums = [v for v in (_coerce_int(x) for x in self.observed + self.pool) if v is not None]
        bnums = [v for v in (_coerce_int(x) for x in self.boundary) if v is not None]
        for _ in range(n):
            u = r.random()
            if bnums and u < 0.25:
                b = r.choice(bnums)
                out.append(b + r.choice([-1, 0, 1]))
            elif nums and u < 0.55:
                out.append(r.choice(nums))
            else:
                out.append(self._fresh_or_reuse(lambda: r.randint(1, 10000)))
        return out


class NumericStringSampler(ColumnSampler):
    """Zero-padded 3-digit strings '000'-'999' with boundary literals +-1 as strings."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        strs = [str(v) for v in self.observed + self.pool]
        bstr = [str(v) for v in self.boundary]
        for _ in range(n):
            u = r.random()
            if bstr and u < 0.35:
                b = r.choice(bstr)
                try:
                    iv = int(b)
                    out.append('%03d' % max(0, min(999, iv + r.choice([-1, 0, 1]))))
                except ValueError:
                    out.append(b)
            elif strs and u < 0.6:
                out.append(r.choice(strs))
            else:
                out.append(self._fresh_or_reuse(lambda: '%03d' % r.randint(0, 999)))
        return out


class EnumSampler(ColumnSampler):
    """Enum columns: uniform pick from the enum list only (no non-enum boundary values)."""

    def __init__(self, table, column, type_str, observed, pool_literals, spec, rng):
        super().__init__(table, column, type_str, observed, pool_literals, spec, rng)
        self.enum = _enum_values(table, column, spec) or list(dict.fromkeys(str(v) for v in self.observed))

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        for _ in range(n):
            if self.enum:
                out.append(r.choice(self.enum))
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_token(r)))
        return out


class StringSampler(ColumnSampler):
    """Short strings: random token 3-12 chars; 10% near-duplicate variants; duplicate share."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [str(v) for v in self.observed + self.pool]
        bstr = [str(v) for v in self.boundary]
        for _ in range(n):
            u = r.random()
            if bstr and u < 0.2:
                out.append(r.choice(bstr))
            elif base and u < 0.45:
                v = r.choice(base)
                out.append(_near_dup(r, v) if r.random() < 0.1 else v)
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_token(r)))
        return out


class TextSampler(ColumnSampler):
    """Text columns: sentence-like up to 200 chars; 10% near-duplicate variants; duplicate share."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [str(v) for v in self.observed + self.pool]
        lo, hi = self.dup if self.dup else (0.0, 0.0)
        share = r.uniform(lo, hi) if hi > 0 else 0.0
        for _ in range(n):
            u = r.random()
            if base and u < share:
                out.append(r.choice(base))
            elif base and u < 0.4:
                v = r.choice(base)
                out.append(_near_dup(r, v) if r.random() < 0.1 else v)
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_text(r)))
        return out


class PhoneSampler(ColumnSampler):
    """Phone formats; 20-50% duplicate share."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [str(v) for v in self.observed + self.pool]
        lo, hi = self.dup if self.dup else (0.2, 0.5)
        share = r.uniform(lo, hi)
        for _ in range(n):
            if base and r.random() < share:
                out.append(r.choice(base))
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_phone(r)))
        return out


class EmailSampler(ColumnSampler):
    """Email: first.last@example.com style; unique per row."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        seen = set()
        for _ in range(n):
            for _try in range(20):
                v = _rand_email(r)
                if v not in seen:
                    break
            seen.add(v)
            out.append(v)
        return out


class AddressSampler(ColumnSampler):
    """Multi-line US-style address."""

    def sample(self, n: int) -> list:
        r = self.rng
        return [self._fresh_or_reuse(lambda: _rand_address(r)) for _ in range(n)]


class CardNumberSampler(ColumnSampler):
    """16-digit numeric string; boundary literals +-1 as strings."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [str(v) for v in self.observed + self.pool]
        bstr = [str(v) for v in self.boundary]
        for _ in range(n):
            u = r.random()
            if bstr and u < 0.35:
                b = r.choice(bstr)
                try:
                    iv = int(b)
                    out.append(str(iv + r.choice([-1, 0, 1])))
                except ValueError:
                    out.append(b)
            elif base and u < 0.55:
                out.append(r.choice(base))
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_card_number(r)))
        return out


class DateTimeSampler(ColumnSampler):
    """Uniform timestamp in [2009-01-01, 2018-12-31]; boundary literals +-1 day."""

    LO = dt.datetime(2009, 1, 1)
    HI = dt.datetime(2018, 12, 31, 23, 59, 59)

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [str(v) for v in self.observed + self.pool]
        bstr = [str(v) for v in self.boundary]
        for _ in range(n):
            u = r.random()
            if bstr and u < 0.25:
                b = r.choice(bstr)
                try:
                    d = dt.datetime.strptime(str(b)[:19], '%Y-%m-%d %H:%M:%S')
                    d = d + dt.timedelta(days=r.choice([-1, 0, 1]))
                    out.append(d.strftime('%Y-%m-%d %H:%M:%S'))
                except ValueError:
                    out.append(str(b))
            elif base and u < 0.45:
                out.append(r.choice(base))
            else:
                out.append(self._fresh_or_reuse(lambda: _rand_datetime(r, self.LO, self.HI)))
        return out


class AmountSampler(ColumnSampler):
    """Double amount: uniform [0.01, 5000.00], 2 decimals; boundary literals +-0.01."""

    def sample(self, n: int) -> list:
        r = self.rng
        out = []
        base = [v for v in (_coerce_num(x) for x in self.observed + self.pool) if v is not None]
        bnum = [v for v in (_coerce_num(x) for x in self.boundary) if v is not None]
        for _ in range(n):
            u = r.random()
            if bnum and u < 0.25:
                b = r.choice(bnum)
                out.append(round(max(0.0, b + r.choice([-0.01, 0.0, 0.01])), 2))
            elif base and u < 0.45:
                out.append(round(r.choice(base), 2))
            else:
                out.append(self._fresh_or_reuse(lambda: round(r.uniform(0.01, 5000.00), 2)))
        return out


def make_sampler(table, column, type_str, observed, pool_literals, spec, rng) -> ColumnSampler:
    """Pick the sampler by declared type and spec exceptions."""
    t = (type_str or '').lower()
    if _is_enum_column(table, column, spec):
        return EnumSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_card_number(table, column):
        return CardNumberSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_phone(table, column):
        return PhoneSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_email(table, column):
        return EmailSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_address(table, column):
        return AddressSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_account_name(table, column):
        return NumericStringSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_datetime_type(t):
        return DateTimeSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if _is_num_type(t):
        if _is_int_type(t):
            return IntSampler(table, column, type_str, observed, pool_literals, spec, rng)
        return AmountSampler(table, column, type_str, observed, pool_literals, spec, rng)
    if 'char' in t or 'text' in t or 'varchar' in t:
        m = re.search(r'\((\d+)\)', t)
        if m and int(m.group(1)) > 80:
            return TextSampler(table, column, type_str, observed, pool_literals, spec, rng)
        return StringSampler(table, column, type_str, observed, pool_literals, spec, rng)
    return StringSampler(table, column, type_str, observed, pool_literals, spec, rng)
