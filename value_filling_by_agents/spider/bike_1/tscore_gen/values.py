"""Per-type value generators driven by the specification domains."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y %H:%M',
              '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*',
               lambda m: m.group(1).title(), str(s).strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class ColumnSampler:
    """Base sampler: pool + fresh values with a random cap on distinct fresh values."""

    def __init__(self, elements: list, p: float, max_l0: float, rng, null_share: float = 0.0):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.null_share = null_share

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def _maybe_null(self, v):
        if self.null_share > 0 and self.rng.random() < self.null_share:
            return None
        return v

    def sample(self):
        raise NotImplementedError


class NumberSampler(ColumnSampler):
    """Integer / numeric sampler: pool values, fresh values in the observed range, +-1/+-2 perturbations."""

    def __init__(self, elements, p, max_l0, rng, is_int=True, precision=0, null_share=0.0):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng, null_share)
        self.is_int, self.precision = is_int, precision
        self.list_min = min(self.elements) if self.elements else 0.0
        self.list_max = max(self.elements) if self.elements else 100.0
        if self.list_min == self.list_max:
            self.list_max = self.list_min + 1.0

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def sample(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            lo, hi = self.list_min, self.list_max
            v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)) if self.is_int
                                     else r.uniform(lo, hi))
        else:
            v = r.choice(self.elements)
        d = 1 if self.is_int else 0.01
        u = r.random()
        if u < 1 / 6:
            v += d
        elif u < 1 / 3:
            v -= d
        elif u < 1 / 2:
            v += 2 * d
        elif u < 2 / 3:
            v -= 2 * d
        return self._maybe_null(self._cast(v))


class StringSampler(ColumnSampler):
    """Text sampler: pool values plus prefix/suffix/dropped-character variants."""

    def __init__(self, elements, p, max_l0, rng, length=20, null_share=0.0):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng, null_share)
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
            elif u < 0.8 and v:
                v = v[:-1]
            elif v:
                v = v[1:]
        return self._maybe_null(v)


class DateSampler(ColumnSampler):
    """Date / datetime sampler: pool values, fresh values in the observed range, same format."""

    def __init__(self, elements, p, max_l0, rng, null_share=0.0):
        super().__init__(elements, p, max_l0, rng, null_share)
        self.p = p
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

    def _fmt(self, d: dt.datetime) -> str:
        s = d.strftime(self.template)
        if self.strip0:
            s = re.sub(r'(^|[-/ :])0(\d)', r'\1\2', s)
        return s

    def _draw_after(self, lo: dt.datetime) -> str:
        r = self.rng
        hi = self.full[1] if lo > self.full[0] else self.full[1]
        hi = max(hi, lo + dt.timedelta(days=1))
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        return self._fmt(d)

    def _draw(self):
        r = self.rng
        lo, hi = self.full if (r.random() < self.p or self.n_parsed <= 1) else self.rng_dates
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        return self._fmt(d)

    def draw_ge(self, threshold):
        """A fresh value >= threshold (threshold is a value already in this column's format)."""
        if threshold is None:
            return self.sample()
        _, parsed = _parse_date(threshold)
        if parsed is None:
            return self.sample()
        return self._maybe_null(self._draw_after(parsed))

    def sample(self):
        if self.elements and self.rng.random() < self.p:
            return self._maybe_null(self.rng.choice(self.elements))
        return self._maybe_null(self._fresh_or_reuse(self._draw))


class EnumSampler(ColumnSampler):
    """Enum sampler: uniform over the listed values (plus pool literals)."""

    def sample(self):
        if not self.elements:
            return None
        return self._maybe_null(self.rng.choice(self.elements))


class SeqSampler(ColumnSampler):
    """Primary-key sampler: sequential from the compact max PK + 1, never NULL, bounded by span."""

    def __init__(self, lo: int, hi: int, rng, start: int = None):
        super().__init__([], 1.0, float('inf'), rng, 0.0)
        self.lo, self.hi = int(lo), int(hi)
        default = self.lo if start is None else start
        self.next = int(max(default, self.lo))

    def sample(self):
        v = self.next
        self.next += 1
        if self.next > self.hi + 1:
            self.next = self.lo
        return v


class NumericSeqSampler(ColumnSampler):
    """Primary-key sampler for non-integer compact PKs: fractional sequential values."""

    def __init__(self, lo, hi, rng, start=None):
        super().__init__([], 1.0, float('inf'), rng, 0.0)
        self.lo, self.hi = float(lo), float(hi)
        self.next = float(start if start is not None else self.hi + 0.000001)

    def sample(self):
        v = round(self.next, 6)
        self.next += 0.000001
        if self.next > self.hi:
            self.next = self.lo
        return v


def make_column_sampler(column, domain, elements: list, p: float, max_l0: float, rng,
                        null_share: float = 0.0, pk_start=None) -> ColumnSampler:
    """Pick the sampler by the specification domain kind (falling back to the declared type)."""
    kind = domain[0] if domain else 'text'
    if kind == 'int_seq':
        decl = (column.type_str or '').lower()
        if any(k in decl for k in ('real', 'float', 'double', 'numeric', 'decimal')):
            return NumericSeqSampler(domain[1], domain[2], rng, pk_start)
        return SeqSampler(domain[1], domain[2], rng, pk_start)
    if kind == 'int_pool':
        return NumberSampler(elements, p, max_l0, rng, is_int=True, null_share=null_share)
    if kind == 'numeric':
        return NumberSampler(elements, p, max_l0, rng, is_int=False, precision=6, null_share=null_share)
    if kind == 'date':
        return DateSampler(elements, p, max_l0, rng, null_share=null_share)
    if kind == 'enum':
        return EnumSampler(elements, p, max_l0, rng, null_share=null_share)
    if kind == 'fk':
        return NumberSampler(elements, p, max_l0, rng, is_int=True, null_share=null_share)
    return StringSampler(elements, p, max_l0, rng, null_share=null_share)


def _init_sampler(column, domain, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), null_share: float = 0.0, pk_start=None) -> ColumnSampler:
    """Per-column initialisation: observed values + pool literals, random cap on fresh values."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, domain, els, p, max_l0, rng, null_share, pk_start)


def random_values_for_a_column(column_meta, domain, literal_pool: list, n: int, rng, *,
                               original_values: list = (), p: float = 0.2,
                               max_l0: float = float('inf'), null_share: float = 0.0) -> list:
    """Initialise one column sampler and draw n values."""
    s = _init_sampler(column_meta, domain, literal_pool, original_values, p, rng,
                      1 if column_meta.pk_pos else 0, max_l0, null_share)
    return [s.sample() for _ in range(n)]
