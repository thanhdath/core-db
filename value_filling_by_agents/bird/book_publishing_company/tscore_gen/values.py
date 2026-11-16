"""Per-type value generators implementing the specification by construction."""
import datetime as dt
import re
import string

from . import spec

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S.0', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y',
              '%Y%m%d', '%Y-%m']


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


def _fmt_date(d: dt.datetime) -> str:
    return d.strftime('%Y-%m-%d %H:%M:%S.0')


def _case_variants(v: str) -> list:
    """Case variants of a text literal (boundary / near-variant rule)."""
    out = [v, v.lower(), v.upper(), v.title()]
    if v:
        out.append(v[0].lower() + v[1:])
        out.append(v[0].upper() + v[1:])
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def _like_variants(v: str) -> list:
    """LIKE-prefix variants without '%' (near-variant rule)."""
    body = v.replace('%', '')
    out = [body]
    if body:
        out.append(body[:max(1, len(body) // 2)])
        out.append(body + 'x')
        out.append('x' + body)
    return out


def _is_text_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return not any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real', 'blob',
                                    'date', 'timestamp'))


def _coerce_literal(v, type_str: str):
    """Normalize a boundary literal to the declared column type."""
    t = (type_str or '').lower()
    if 'blob' in t:
        return v
    if 'date' in t or 'timestamp' in t:
        if isinstance(v, str):
            _, d = _parse_date(v)
            return _fmt_date(d) if d is not None else v
        return v
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        n = _num(v)
        if n is None:
            return v
        return int(round(n)) if 'int' in t else round(n, 2)
    return str(v)


class ColumnSampler:
    """Base sampler: value pool + fresh values + NULL rule + exception patterns."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0):
        self.table, self.column = table, column
        self.type_str = (type_str or '').lower().strip()
        self.nullable = nullable
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.null_share = null_share if nullable else 0.0
        self.n_rows = n_rows
        self.null_emitted = 0
        self.nonnull_emitted = 0
        self._boundary = self._boundary_values()
        self._boundary_i = 0
        self._dup_pool: list = []
        self._dup_share = self._dup_share()
        self._tie_value = None
        self._tie_emitted = 0
        self._group_plan = self._group_plan()
        self._group_i = 0
        self._diff_pool: list = []

    def _boundary_values(self) -> list:
        vals = []
        for pat, tgt in spec.exceptions_for(self.table, self.column):
            if pat in ('comparison_boundary', 'like_near_variant'):
                for v in tgt.get('values', []):
                    vals.append(_coerce_literal(v, self.type_str))
                    if isinstance(v, str):
                        for cv in _case_variants(v):
                            vals.append(_coerce_literal(cv, self.type_str))
                        if pat == 'like_near_variant' or '%' in v:
                            for lv in _like_variants(v):
                                vals.append(_coerce_literal(lv, self.type_str))
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        vals.append(_coerce_literal(v - 1, self.type_str))
                        vals.append(_coerce_literal(v + 1, self.type_str))
        seen, res = set(), []
        for v in vals:
            k = (type(v).__name__, str(v))
            if k not in seen:
                seen.add(k)
                res.append(v)
        return res

    def _dup_share(self) -> float:
        for pat, tgt in spec.exceptions_for(self.table, self.column):
            if pat == 'duplicates_for_distinct':
                lo, hi = tgt.get('duplicate_share', (0.2, 0.5))
                return self.rng.uniform(lo, hi)
        return 0.0

    def _group_plan(self) -> list:
        for pat, tgt in spec.exceptions_for(self.table, self.column):
            if pat == 'group_sizes':
                return [1, 2, 3, 3]
        return []

    def _tie_target(self):
        for pat, tgt in spec.exceptions_for(self.table, self.column):
            if pat == 'ties_for_order_limit':
                return True
        return False

    def _want_null(self) -> bool:
        if not self.nullable:
            return False
        if self.null_emitted == 0 and self.nonnull_emitted >= max(1, self.n_rows - 1):
            return True
        if self.null_emitted == 0 and self.n_rows > 0 and self.rng.random() < 0.5:
            return True
        return self.rng.random() < self.null_share

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def _draw(self):
        raise NotImplementedError

    def _coerce(self, v):
        return v

    def sample(self):
        if self._want_null():
            self.null_emitted += 1
            return None
        self.nonnull_emitted += 1
        if self._boundary and self._boundary_i < len(self._boundary):
            v = self._boundary[self._boundary_i]
            self._boundary_i += 1
            return self._coerce(v)
        if self._dup_pool and self.rng.random() < self._dup_share:
            return self.rng.choice(self._dup_pool)
        if self._tie_target() and self._tie_value is not None and self._tie_emitted < 2:
            self._tie_emitted += 1
            return self._tie_value
        if self._group_plan and self._group_i < len(self._group_plan):
            self._group_i += 1
        v = self._draw()
        v = self._coerce(v)
        if self._dup_share > 0 and v is not None:
            self._dup_pool.append(v)
        if self._tie_target() and self._tie_value is None and v is not None:
            self._tie_value = v
        return v


class NumberSampler(ColumnSampler):
    """Integer / real sampler with bounds, boundary perturbations and fresh values."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0, is_int=True, precision=0):
        super().__init__(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows)
        self.is_int = is_int
        self.precision = precision
        nums = [f for f in (_num(e) for e in self.elements) if f is not None]
        self.nums = nums
        lo, hi = spec.BOUNDS.get((table, column), (None, None))
        self.bound_lo = lo
        self.bound_hi = hi
        if nums:
            self.list_min = min(nums)
            self.list_max = max(nums)
        else:
            self.list_min, self.list_max = (lo if lo is not None else 0), (hi if hi is not None else 100)
        if lo is not None:
            self.list_min = max(self.list_min, lo)
        if hi is not None:
            self.list_max = min(self.list_max, hi)
        if self.list_max < self.list_min:
            self.list_max = self.list_min
        self.min, self.max = -10 ** 6, 10 ** 6
        if lo is not None:
            self.min = lo
        if hi is not None:
            self.max = hi

    def _cast(self, v):
        if self.is_int:
            v = int(round(v))
        else:
            v = round(float(v), self.precision) if self.precision else float(v)
        if self.bound_lo is not None and v < self.bound_lo:
            v = self.bound_lo
        if self.bound_hi is not None and v > self.bound_hi:
            v = self.bound_hi
        return v

    def _draw(self):
        r = self.rng
        if not self.elements or r.random() < self.p:
            full = r.random() < self.p or len(self.elements) <= 1
            lo, hi = (self.min, self.max) if full else (self.list_min, self.list_max)
            if self.is_int:
                v = self._fresh_or_reuse(lambda: r.randint(int(lo), int(hi)))
            else:
                v = self._fresh_or_reuse(lambda: r.uniform(lo, hi))
        else:
            v = r.choice(self.nums)
        d = 1 if self.is_int else 0.01
        u = r.random()
        if u < 1 / 6:
            v += d
        elif u < 1 / 5:
            v -= d
        elif u < 1 / 4:
            v += 2 * d
        elif u < 1 / 3:
            v -= 2 * d
        return v


class StringSampler(ColumnSampler):
    """Text sampler with pools, case / prefix / suffix / dropped-char variants."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0, length=20):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(table, column, type_str, nullable, els + extra, p, max_l0, rng, null_share, n_rows)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.enum = spec.ENUMS.get((table, column))

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def _draw(self):
        r = self.rng
        if self.enum and r.random() < 0.7:
            return r.choice(self.enum)
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


class DateSampler(ColumnSampler):
    """Datetime sampler with boundary dates."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0):
        super().__init__(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows)
        strs = [str(e) for e in self.elements]
        parsed = []
        for s in strs:
            _, d = _parse_date(s)
            if d is not None:
                parsed.append(d)
        self.full = (dt.datetime(1800, 1, 1), dt.datetime(2100, 1, 1))
        self.rng_dates = (min(parsed), max(parsed)) if len(set(parsed)) >= 2 else self.full
        self.n_parsed = len(set(parsed))

    def _coerce(self, v):
        if isinstance(v, str):
            _, d = _parse_date(v)
            if d is not None:
                return _fmt_date(d)
        return v

    def _draw(self):
        r = self.rng
        lo, hi = self.full if (r.random() < self.p or self.n_parsed <= 1) else self.rng_dates
        if hi < lo:
            hi = lo
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        return _fmt_date(d)


class BlobSampler(ColumnSampler):
    """Short synthetic byte string for BLOB columns."""

    def _draw(self):
        n = self.rng.randint(4, 16)
        return bytes(self.rng.randrange(256) for _ in range(n))


class TextPkSampler(ColumnSampler):
    """Text primary key: stable prefix + zero-padded counter, unique against compact rows."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0, prefix='GEN-', start=1):
        super().__init__(table, column, type_str, False, [], 1.0, max_l0, rng, 0.0, n_rows)
        self.prefix = prefix
        self.counter = start

    def sample(self):
        v = '%s%06d' % (self.prefix, self.counter)
        self.counter += 1
        return v


class IntPkSampler(ColumnSampler):
    """Integer primary key: fresh integers above the compact max."""

    def __init__(self, table, column, type_str, nullable, elements, p, max_l0, rng,
                 null_share=0.0, n_rows=0, start=1):
        super().__init__(table, column, type_str, False, [], 1.0, max_l0, rng, 0.0, n_rows)
        self.counter = start

    def sample(self):
        v = self.counter
        self.counter += 1
        return v


def make_column_sampler(table, column, type_str, nullable, elements, p, max_l0, rng,
                        null_share=0.0, n_rows=0) -> ColumnSampler:
    """Pick the sampler by declared type; unknown types fall back to String."""
    t = (type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'blob':
        return BlobSampler(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows)
    if 'date' in t or 'timestamp' in t:
        return DateSampler(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        prec = 0 if is_int else (args[1] if len(args) > 1 else 2)
        return NumberSampler(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows,
                             is_int=is_int, precision=prec)
    return StringSampler(table, column, type_str, nullable, elements, p, max_l0, rng, null_share, n_rows,
                         length=args[0] if args else 20)


def _init_sampler(table, column, type_str, nullable, literal_pool, original_values, p, rng, n_pk,
                  null_share=0.0, n_rows=0, max_l0=float('inf'), is_pk=False, pk_start=1) -> ColumnSampler:
    """Per-column initialisation: observed values + pool literals + fresh values."""
    if is_pk:
        t = (type_str or '').lower()
        if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
            return IntPkSampler(table, column, type_str, False, [], 1.0, max_l0, rng, 0.0, n_rows,
                                start=pk_start)
        prefix = spec.TEXT_PK_PREFIX.get((table, column), 'GEN-%s-' % column.upper())
        return TextPkSampler(table, column, type_str, False, [], 1.0, max_l0, rng, 0.0, n_rows,
                             prefix=prefix, start=pk_start)
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
    return make_column_sampler(table, column, type_str, nullable, els, p, max_l0, rng, null_share, n_rows)
