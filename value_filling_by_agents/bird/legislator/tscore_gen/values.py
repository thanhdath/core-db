"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

ENUMS = {
    ('current', 'gender_bio'): ['M', 'F'],
    ('current', 'suffix_name'): ['Jr.', 'Sr.', 'II', 'III', 'IV'],
    ('current', 'religion_bio'): ['Lutheran', 'Roman Catholic', 'Jewish', 'Presbyterian', 'Latter Day Saints',
                                  'United Methodist', 'Southern Baptist', 'Baptist', 'Methodist', 'Episcopalian',
                                  'Non-Denominational', 'United Church of Christ', 'Unknown'],
    ('current-terms', 'chamber'): ['senate', 'house'],
    ('current-terms', 'party'): ['Democrat', 'Republican', 'Independent'],
    ('current-terms', 'type'): ['sen', 'rep'],
    ('current-terms', 'class'): [1, 2, 3],
    ('current-terms', 'state_rank'): ['senior', 'junior'],
    ('current-terms', 'title'): ['Minority Whip', 'Majority Whip', 'Minority Leader', 'Majority Leader', 'Speaker'],
    ('historical', 'gender_bio'): ['M', 'F'],
    ('historical', 'suffix_name'): ['Jr.', 'Sr.', 'II', 'III', 'IV'],
    ('historical-terms', 'chamber'): ['senate', 'house'],
    ('historical-terms', 'type'): ['sen', 'rep'],
    ('historical-terms', 'class'): [1, 2, 3],
    ('historical-terms', 'state_rank'): ['senior', 'junior'],
}

BOUNDARY = {
    ('current', 'official_full_name'): ['Sherrod Brown', 'sherrod brown', 'Maria Cantwell', 'maria cantwell',
                                        'Bob Corker', 'bob corker'],
    ('current', 'first_name'): ['Sherrod', 'sherrod', 'Bob', 'bob', 'Amy', 'amy'],
    ('current', 'last_name'): ['Brown', 'brown', 'Corker', 'corker', 'Klobuchar', 'klobuchar'],
    ('current', 'birthday_bio'): ['1959-12-31', '1960-01-01', '1960-01-02', '1960-12-31', '1961-01-01', '1961-01-02'],
    ('current', 'cspan_id'): ['', 'x'],
    ('current', 'opensecrets_id'): ['', 'x', 'N00003689', 'n00003689'],
    ('current', 'ballotpedia_id'): ['', 'x'],
    ('current', 'fec_id'): ['', 'x'],
    ('current', 'gender_bio'): ['F', 'f'],
    ('current', 'nickname_name'): ['', 'x'],
    ('current', 'religion_bio'): ['Baptist', 'baptist'],
    ('historical', 'gender_bio'): ['M', 'm', 'F', 'f'],
}

_NUMERIC_BOUNDARY_COLS = {
    ('current', 'cspan_id'),
}

NULL_SHARE = {
    ('current', 'ballotpedia_id'): 0.359, ('current', 'birthday_bio'): 0.20, ('current', 'cspan_id'): 0.22,
    ('current', 'fec_id'): 0.20, ('current', 'first_name'): 0.10, ('current', 'gender_bio'): 0.10,
    ('current', 'google_entity_id_id'): 0.102, ('current', 'govtrack_id'): 0.10,
    ('current', 'house_history_id'): 0.353, ('current', 'icpsr_id'): 0.24, ('current', 'lis_id'): 0.20,
    ('current', 'maplight_id'): 0.102, ('current', 'middle_name'): 0.601, ('current', 'nickname_name'): 0.20,
    ('current', 'official_full_name'): 0.10, ('current', 'opensecrets_id'): 0.102,
    ('current', 'religion_bio'): 0.20, ('current', 'suffix_name'): 0.20, ('current', 'thomas_id'): 0.20,
    ('current', 'votesmart_id'): 0.211, ('current', 'wikidata_id'): 0.102, ('current', 'wikipedia_id'): 0.094,
    ('current-terms', 'address'): 0.478, ('current-terms', 'caucus'): 0.999, ('current-terms', 'chamber'): 0.991,
    ('current-terms', 'class'): 0.921, ('current-terms', 'contact_form'): 0.676, ('current-terms', 'district'): 0.10,
    ('current-terms', 'end'): 0.014, ('current-terms', 'fax'): 0.664, ('current-terms', 'last'): 1.0,
    ('current-terms', 'name'): 0.989, ('current-terms', 'office'): 0.478, ('current-terms', 'party'): 0.021,
    ('current-terms', 'party_affiliations'): 0.999, ('current-terms', 'phone'): 0.478,
    ('current-terms', 'relation'): 0.989, ('current-terms', 'rss_url'): 0.657, ('current-terms', 'start'): 0.012,
    ('current-terms', 'state'): 0.021, ('current-terms', 'state_rank'): 0.952, ('current-terms', 'title'): 0.991,
    ('current-terms', 'type'): 0.021, ('current-terms', 'url'): 0.266,
    ('historical', 'ballotpedia_id'): 0.991, ('historical', 'bioguide_previous_id'): 1.0,
    ('historical', 'birthday_bio'): 0.047, ('historical', 'cspan_id'): 0.974, ('historical', 'fec_id'): 0.964,
    ('historical', 'google_entity_id_id'): 0.001, ('historical', 'house_history_alternate_id'): 1.0,
    ('historical', 'house_history_id'): 0.10, ('historical', 'icpsr_id'): 0.018, ('historical', 'lis_id'): 0.985,
    ('historical', 'maplight_id'): 0.988, ('historical', 'middle_name'): 0.299, ('historical', 'nickname_name'): 0.982,
    ('historical', 'official_full_name'): 0.981, ('historical', 'opensecrets_id'): 0.953,
    ('historical', 'religion_bio'): 0.969, ('historical', 'suffix_name'): 0.965, ('historical', 'thomas_id'): 0.857,
    ('historical', 'votesmart_id'): 0.963,
    ('historical-terms', 'address'): 0.995, ('historical-terms', 'chamber'): 1.0, ('historical-terms', 'class'): 0.894,
    ('historical-terms', 'contact_form'): 0.998, ('historical-terms', 'district'): 0.106,
    ('historical-terms', 'fax'): 0.996, ('historical-terms', 'last'): 1.0, ('historical-terms', 'middle'): 1.0,
    ('historical-terms', 'name'): 1.0, ('historical-terms', 'office'): 0.995, ('historical-terms', 'party'): 0.019,
    ('historical-terms', 'party_affiliations'): 1.0, ('historical-terms', 'phone'): 0.995,
    ('historical-terms', 'relation'): 1.0, ('historical-terms', 'rss_url'): 0.999, ('historical-terms', 'state'): 0.001,
    ('historical-terms', 'state_rank'): 0.999, ('historical-terms', 'title'): 1.0, ('historical-terms', 'type'): 0.001,
    ('historical-terms', 'url'): 0.985,
    ('social-media', 'facebook'): 0.044, ('social-media', 'facebook_id'): 0.194, ('social-media', 'govtrack'): 0.006,
    ('social-media', 'instagram'): 0.772, ('social-media', 'instagram_id'): 0.806, ('social-media', 'thomas'): 0.008,
    ('social-media', 'twitter'): 0.019, ('social-media', 'twitter_id'): 0.023, ('social-media', 'youtube'): 0.198,
    ('social-media', 'youtube_id'): 0.157,
}

NOT_NULL = {
    ('current', 'bioguide_id'), ('current', 'cspan_id'), ('current-terms', 'bioguide'), ('current-terms', 'end'),
    ('historical', 'bioguide_id'), ('historical-terms', 'bioguide'), ('historical-terms', 'end'),
    ('historical-terms', 'start'), ('social-media', 'bioguide'),
}

NUM_MIN = {
    ('current', 'cspan_id'): 0, ('current', 'govtrack_id'): 1, ('current', 'thomas_id'): 1,
    ('current', 'house_history_id'): 0, ('current', 'icpsr_id'): 0, ('current', 'maplight_id'): 0,
    ('current', 'votesmart_id'): 0, ('current-terms', 'district'): 0, ('historical', 'govtrack_id'): 1,
    ('historical', 'house_history_id'): 0, ('historical', 'icpsr_id'): 0, ('historical-terms', 'district'): -1,
    ('social-media', 'facebook_id'): 0, ('social-media', 'instagram_id'): 0, ('social-media', 'twitter_id'): 0,
    ('social-media', 'govtrack'): 1, ('social-media', 'thomas'): 1,
}


def is_numeric_boundary_column(table: str, column: str) -> bool:
    """True for a numeric-declared column whose boundary literals are text (loose type)."""
    return (table, column) in _NUMERIC_BOUNDARY_COLS


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _near_variant(v, rng):
    """5% near-variants: case change, trailing space, doubled letter (strings) / +-1 (numbers)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v + rng.choice([-1, 1])
    s = str(v)
    if not s:
        return s
    u = rng.random()
    if u < 0.34:
        return s.swapcase() if s.islower() or s.isupper() else s.lower()
    if u < 0.67:
        return s + ' '
    i = rng.randrange(len(s))
    return s[:i] + s[i] + s[i:]


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

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False, lo=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        if lo is not None:
            self.min = max(self.min, lo)
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
        v = self._cast(v)
        if self.min is not None and v < self.min:
            v = self.min
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
        self.template = self.template or '%Y-%m-%d'
        self.full = (dt.datetime(1730, 1, 1), dt.datetime(2020, 12, 31))
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
    """Uniform sample from the declared enum list; 5% near-variants (case change)."""

    def __init__(self, values, p, max_l0, rng):
        super().__init__(list(values), p, max_l0, rng)

    def sample(self):
        v = self.rng.choice(self.elements)
        if self.rng.random() < 0.05:
            v = _near_variant(v, self.rng)
        return v


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    key = (column.table, column.name)
    if key in ENUMS:
        return EnumSampler(ENUMS[key], p, max_l0, rng)
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
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, lo=NUM_MIN.get(key))
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf')) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224, plus boundary literals and fresh values."""
    key = (column.table, column.name)
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    els += [str(v) for v in BOUNDARY.get(key, [])]
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


def null_share(table: str, column: str) -> float:
    """NULL share for a column; NOT NULL columns never get NULL."""
    if (table, column) in NOT_NULL:
        return 0.0
    return NULL_SHARE.get((table, column), 0.0)
