"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py), with
specification-driven pools, ranges, boundaries, rank ties, duplicate shares and NULL shares."""
import datetime as dt
import re
import string

from . import specification as spec

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng, table: str = '', column: str = '',
                 nullable: bool = True, null_share: float = 0.05):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.table = table
        self.column = column
        self.nullable = nullable
        self.null_share = null_share if nullable else 0.0

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def sample(self):
        raise NotImplementedError

    def _numeric_pool(self) -> list:
        return [float(e) for e in self.elements if _num(e) is not None]

    def _forced(self, n: int) -> list:
        """Positions whose value is forced by the specification (boundaries, ties, duplicates, groups)."""
        r = self.rng
        forced = [None] * n
        bounds = spec.bound_values(self.table, self.column)
        if bounds and n:
            k = min(n, len(bounds))
            for pos, v in zip(r.sample(range(n), k), bounds):
                forced[pos] = v
        ranks = spec.tie_ranks(self.table, self.column)
        if ranks and n:
            nums = self._numeric_pool()
            hi = max(nums) if nums else 100.0
            lo = min(nums) if nums else 0.0
            span = max(hi - lo, 1.0)
            free = [i for i in range(n) if forced[i] is None]
            r.shuffle(free)
            cursor = 0
            for rank in sorted(ranks):
                cnt = ranks[rank]
                val = hi - (rank - 1) * (span / (max(ranks) + 2))
                for _ in range(cnt):
                    if cursor < len(free):
                        forced[free[cursor]] = val
                        cursor += 1
        tie = spec.tie_top(self.table, self.column)
        if tie and n >= tie:
            free = [i for i in range(n) if forced[i] is None]
            nums = self._numeric_pool()
            top = max(nums) if nums else None
            if top is not None:
                for i in r.sample(free, min(tie, len(free))):
                    forced[i] = top
        dup = spec.duplicate_share(self.table, self.column)
        if dup > 0 and n >= 2:
            free = [i for i in range(n) if forced[i] is None]
            k = int(round(dup * n))
            if k and len(free) >= 2:
                n_don = max(1, min(len(free) // 2, k))
                donors = free[:n_don]
                targets = free[n_don:n_don + k]
                if targets:
                    donor_vals = [self.elements[i % len(self.elements)] if self.elements else None
                                  for i in range(len(donors))]
                    for j, pos in enumerate(targets):
                        v = donor_vals[j % len(donor_vals)] if donor_vals else None
                        if v is not None:
                            forced[pos] = v
        shape = spec.group_shape(self.table, self.column)
        if shape and n >= 6:
            pool = spec.enum_values(self.table, self.column) or self.elements
            reps = []
            for v in pool:
                if v not in reps:
                    reps.append(v)
                if len(reps) == 3:
                    break
            while len(reps) < 3:
                reps.append('grp_%d_%d' % (len(reps), r.randrange(10 ** 6)))
            a, b, c = reps[0], reps[1], reps[2]
            for v, cnt in ((a, 1), (b, 2), (c, 3)):
                for _ in range(cnt):
                    for i in range(n):
                        if forced[i] is None:
                            forced[i] = v
                            break
        return forced

    def sample_many(self, n: int) -> list:
        forced = self._forced(n)
        out = [self.sample() for _ in range(n)]
        for i, v in enumerate(forced):
            if v is not None:
                out[i] = v
        if self.nullable and n:
            k = max(1, int(round(self.null_share * n)))
            k = min(k, n)
            for i in self.rng.sample(range(n), k):
                out[i] = None
        return out

    def fix_relation(self, values: list, rows: list) -> list:
        """Hook for relational constraints; rows[i] is the dict of other columns of row i."""
        return values


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class NumberSampler(ColumnSampler):
    """fuzz/number.py; honours a specification range; keeps the list_max overwrite quirk."""

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 table='', column='', nullable=True, null_share=0.05, spec_range=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng,
                         table, column, nullable, null_share)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        if spec_range is not None:
            self.min, self.max = spec_range
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
        v = max(self.min, min(self.max, v))
        return self._cast(v)


class StringSampler(ColumnSampler):
    """fuzz/string.py (allow_none dropped) with an optional enum pool, exact for spec enums."""

    def __init__(self, elements, p, max_l0, rng, length=20, table='', column='', nullable=True,
                 null_share=0.05, enum=None):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng, table, column, nullable, null_share)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.enum = list(enum) if enum else None

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def sample(self):
        r = self.rng
        if self.enum and r.random() < 0.85:
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

    def __init__(self, elements, p, max_l0, rng, table='', column='', nullable=True, null_share=0.05):
        super().__init__(elements, p, max_l0, rng, table, column, nullable, null_share)
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
    """fuzz/time.py (race-time strings like H:MM.SS.S keep the original template)."""

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

    def __init__(self, elements, p, max_l0, rng, bit=False, table='', column='', nullable=True, null_share=0.05):
        super().__init__(elements, p, max_l0, rng, table, column, nullable, null_share)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, *, nullable=True,
                        null_share=0.05, enum=None) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    rng_val = spec.range_of(column.table, column.name)
    kw = dict(table=column.table, column=column.name, nullable=nullable, null_share=null_share)
    if t == 'time':
        return TimeSampler(elements, p, max_l0, rng, **kw)
    if t == '' or t == 'blob':
        return StringSampler(elements, p, max_l0, rng, enum=enum, **kw)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in elements if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(elements, p, max_l0, rng, scale=4, **kw)
        return DateSampler(elements, p, max_l0, rng, **kw)
    if 'bool' in t:
        return BoolSampler(elements, p, max_l0, rng, **kw)
    if 'bit' in t:
        return BoolSampler(elements, p, max_l0, rng, bit=True, **kw)
    if 'year' in t:
        return NumberSampler(elements, p, max_l0, rng, scale=4, **kw)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(elements, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, spec_range=rng_val, **kw)
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(elements, p, max_l0, rng, length=args[0] if args else 20, enum=enum, **kw)
    return StringSampler(elements, p, max_l0, rng, enum=enum, **kw)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), null_share: float = None) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224 plus specification pools."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + [str(v) for v in literal_pool]
    for b in spec.bound_values(column.table, column.name):
        els.append(str(b))
    enum = spec.enum_values(column.table, column.name)
    if enum:
        els = list(enum) + els
    p = 1.0 - spec.reuse_share()
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    nullable = not column.notnull and column.pk_pos == 0
    if nullable:
        if null_share is None:
            null_share = compact_null_share(original_values)
        null_share = spec.null_share(column.table, column.name, null_share)
    else:
        null_share = 0.0
    return make_column_sampler(column, els, p, max_l0, rng, nullable=nullable, null_share=null_share, enum=enum)


def compact_null_share(original_values) -> float:
    """NULL share of a column in the compact database (0.0 when it has no rows)."""
    vals = list(original_values)
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return s.sample_many(n)
