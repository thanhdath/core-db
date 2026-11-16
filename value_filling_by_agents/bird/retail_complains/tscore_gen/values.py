"""Per-type value generators implementing the specification by construction."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'

FIRST_NAMES = ["Emma", "Noah", "Olivia", "Liam", "Sophia", "Mason", "Jacob", "Ava", "Mia", "Ethan",
               "Isabella", "Lucas", "Amelia", "Logan", "Harper", "Elijah", "Evelyn", "James",
               "Abigail", "Benjamin", "Emily", "Alexander", "Ella", "Michael", "Elizabeth"]
MIDDLE_NAMES = ["Avaya", "Everest", "Brooklynne", "Irvin", "Danae", "Javen", "Khai", "Eliora",
                "Bronx", "Eliza", "Lewis", "Marie", "Grace", "Lee", "Rose", "James", "Ann", "Lynn"]
LAST_NAMES = ["Smith", "Thompson", "Johnson", "White", "Williams", "Lopez", "Lee", "Brown",
              "Pierce", "Hicks", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson", "Martinez",
              "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Gonzalez"]
CITIES = ["Albuquerque", "New York City", "Indianapolis", "Portland", "Louisville", "Springfield",
          "Lynn", "New Bedford", "Norwalk", "Jacksonville", "Columbus", "Charlotte", "Seattle",
          "Denver", "Washington", "Boston", "Chicago", "Houston", "Phoenix", "Philadelphia"]
STREETS = ["Wellington Ave.", "W. Berkshire St.", "Second St.", "Sunnyslope Street",
           "Galvin Street", "Arnold Drive", "N. Green Lake Court", "Joy Ridge Dr.",
           "Main Street", "Oak Avenue", "Maple Lane", "Pine Road"]
ADDRESS2 = ["Unit 1", "Unit 6", "Unit 80", "Unit 1B", "Apt. 3D", "Unit 81", "Unit 7", "Unit 77",
            "Apt. 2A", "Suite 100", "Unit 12", "Apt. 5C"]
ISSUES = ["Deposits and withdrawals", "Account opening, closing, or management", "Billing disputes",
          "Problems caused by my funds being low", "Other fee", "Collection debt dispute", "Other",
          "Identity theft / Fraud / Embezzlement"]
NARRATIVES = [
    "Deposited a check into my account and the bank placed a hold on the funds.",
    "I called the customer service line and was placed on hold for a long time.",
    "I was a victim of fraud involving my debit card and reported it immediately.",
    "I initiated a wire transfer and the funds were delayed by several days.",
    "I attempted to cash a check at a branch and was refused service.",
    "I am being charged a debt for a company I have never had an account with.",
    "Someone used my debit card to make fraudulent transactions.",
    "The bank sent me a notice about a qualifying direct deposit promotion.",
]
REVIEWS = [
    "Great job! Each person was professional and helped us move through our refinance smoothly.",
    "The loan officer is professional and helpful. He helped us find the correct product.",
    "We had a past experience with the mortgage team and would use them again.",
    "We have been dealing with the team from the beginning of a stressful time.",
    "I can't express how grateful I am for the support during this home purchase.",
    "I had the pleasure of working with the team as my family made a home purchase.",
    "The loan officer answered all my questions by email immediately.",
    "I loved working with this group of people! They answered my questions quickly.",
]
STATE_NAMES = {
    "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _case_variant(s: str, rng) -> str:
    """Case near-variant: flip the whole string or one character."""
    if not s:
        return s
    u = rng.random()
    if u < 0.5:
        return s.upper() if s != s.upper() else s.lower()
    i = rng.randrange(len(s))
    c = s[i]
    return s[:i] + (c.lower() if c.isupper() else c.upper()) + s[i + 1:]


def _one_char_edit(s: str, rng) -> str:
    """One-character edit (insert / delete / substitute)."""
    if not s:
        return s
    u = rng.random()
    i = rng.randrange(len(s))
    if u < 0.34:
        return s[:i] + rng.choice(string.ascii_letters) + s[i:]
    if u < 0.67:
        return s[:i] + s[i + 1:]
    return s[:i] + rng.choice(string.ascii_letters) + s[i + 1:]


def _boundary_strings(lit: str) -> list:
    """Literal, one step below and one step above (case variant for strings)."""
    return [lit, lit.lower(), lit.upper()]


def _boundary_numbers(lit: int) -> list:
    return [lit - 1, lit, lit + 1]


def _parse_iso(s: str):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


class ColumnSampler:
    """Base sampler: holds the value pool, the NULL share and the RNG."""

    def __init__(self, column, exception: dict, pool: list, original: list, rng,
                 null_share: float = 0.0):
        self.column = column
        self.exc = exception or {}
        self.targets = self.exc.get('targets', {})
        self.rng = rng
        self.null_share = float(null_share)
        self.pool = [v for v in pool if v is not None]
        self.original = [v for v in original if v is not None]
        self.fresh: list = []
        self.max_fresh = max(1, int(rng.random() * 30) + 1)

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_fresh:
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


class EnumSampler(ColumnSampler):
    """text_enum / integer_enum: uniform over the enumerated list, ~2% case near-variants."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        vals = list(self.targets.get('values', []))
        if not vals:
            vals = list(self.original) or list(self.pool) or ['']
        self.values = vals
        self.is_int = all(isinstance(v, int) for v in vals)
        allowed = set(vals)
        self.boundary = [b for b in self.targets.get('boundary_literals', []) if b in allowed]

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.10:
            b = r.choice(self.boundary)
            return self._maybe_null(b)
        v = r.choice(self.values)
        if not self.is_int and r.random() < 0.02:
            v = _case_variant(str(v), r)
        return self._maybe_null(v)


class IntegerRangeSampler(ColumnSampler):
    """integer_range: uniform in [min,max], boundary literals, +-1 / +-2 perturbations."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        self.lo = int(self.targets.get('min', 0))
        self.hi = int(self.targets.get('max', 100))
        self.boundary = [int(b) for b in self.targets.get('boundary_literals', [])
                         if self.lo <= int(b) <= self.hi]
        self.max_fresh = max(8, int(rng.random() * 60) + 8)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.10:
            return self._maybe_null(r.choice(self.boundary))
        v = self._fresh_or_reuse(lambda: r.randint(self.lo, self.hi))
        u = r.random()
        if u < 1 / 6:
            v += 1
        elif u < 1 / 3:
            v -= 1
        elif u < 1 / 2:
            v += 2
        elif u < 2 / 3:
            v -= 2
        v = max(self.lo, min(self.hi, v))
        return self._maybe_null(v)


class IdentifierSampler(ColumnSampler):
    """text_identifier: formatted identifiers, ~2% near-variants, fresh against compact rows."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        self.fmt = self.targets.get('format', 'X########')
        self.used = set(str(v) for v in self.original)
        self.used |= set(str(v) for v in self.pool)
        self.boundary = list(self.targets.get('boundary_literals', []))

    def _draw(self):
        r = self.rng
        out = []
        for ch in self.fmt:
            if ch == '#':
                out.append(str(r.randrange(10)))
            elif ch == 'X':
                out.append(r.choice(string.ascii_uppercase))
            else:
                out.append(ch)
        return ''.join(out)

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.05:
            return self._maybe_null(r.choice(self.boundary))
        for _ in range(50):
            v = self._draw()
            if v not in self.used:
                self.used.add(v)
                if r.random() < 0.02:
                    v = _one_char_edit(v, r)
                return self._maybe_null(v)
        v = self._draw() + str(r.randrange(1000))
        self.used.add(v)
        return self._maybe_null(v)


class NameSampler(ColumnSampler):
    """text_name: name pool with a duplicate share and case near-variants."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        self.dup_share = float(self.targets.get('duplicates_for_distinct', 0.35))
        self.boundary = list(self.targets.get('boundary_literals', []))
        base = list(self.original) or list(self.pool)
        if not base:
            base = FIRST_NAMES
        self.base = base
        self.recent: list = []

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.05:
            return self._maybe_null(r.choice(self.boundary))
        if self.recent and r.random() < self.dup_share:
            v = r.choice(self.recent)
        else:
            v = r.choice(self.base)
            self.recent.append(v)
            if len(self.recent) > 40:
                self.recent.pop(0)
        if r.random() < 0.02:
            v = _case_variant(str(v), r)
        return self._maybe_null(v)


class FreeTextSampler(ColumnSampler):
    """text_free: small realistic pool, near-variants, boundary literals."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        self.boundary = list(self.targets.get('boundary_literals', []))
        base = list(self.original) or list(self.pool)
        if not base:
            base = CITIES
        self.base = base

    def sample(self):
        r = self.rng
        if self.boundary and r.random() < 0.10:
            return self._maybe_null(r.choice(self.boundary))
        v = r.choice(self.base)
        if r.random() < 0.02:
            v = _case_variant(str(v), r)
        return self._maybe_null(v)


class EmailSampler(ColumnSampler):
    """email: local.part@domain with gmail/outlook, ~2% near-variants."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        self.domains = ["gmail.com", "outlook.com"]
        self.near = list(self.targets.get('like_near_variant', []))
        self.used = set(str(v) for v in self.original)

    def sample(self):
        r = self.rng
        if self.near and r.random() < 0.02:
            local = r.choice(FIRST_NAMES).lower() + str(r.randrange(100))
            pat = r.choice(self.near)
            if pat.startswith('%'):
                v = local + pat[1:]
            elif pat.startswith('@'):
                v = local + pat
            else:
                v = local + '@' + pat
            return self._maybe_null(v)
        local = r.choice(FIRST_NAMES).lower() + '.' + r.choice(LAST_NAMES).lower() + str(r.randrange(100))
        v = local + '@' + r.choice(self.domains)
        return self._maybe_null(v)


class PhoneSampler(ColumnSampler):
    """phone_us: NNN-NNN-NNNN."""

    def sample(self):
        r = self.rng
        v = '%03d-%03d-%04d' % (r.randrange(1000), r.randrange(1000), r.randrange(10000))
        return self._maybe_null(v)


class SSNSampler(ColumnSampler):
    """ssn_us: NNN-NN-NNNN."""

    def sample(self):
        r = self.rng
        v = '%03d-%02d-%04d' % (r.randrange(1000), r.randrange(100), r.randrange(10000))
        return self._maybe_null(v)


class ZipcodeSampler(ColumnSampler):
    """zipcode: integer 1000-99999."""

    def sample(self):
        r = self.rng
        lo = int(self.targets.get('min', 1000))
        hi = int(self.targets.get('max', 99999))
        return self._maybe_null(r.randint(lo, hi))


class DateSampler(ColumnSampler):
    """date_iso: YYYY-MM-DD within the stated range, boundary dates +-1 day."""

    def __init__(self, column, exception, pool, original, rng, null_share=0.0):
        super().__init__(column, exception, pool, original, rng, null_share)
        lo = _parse_iso(self.targets.get('min', '1900-01-01')) or dt.date(1900, 1, 1)
        hi = _parse_iso(self.targets.get('max', '2100-01-01')) or dt.date(2100, 1, 1)
        self.lo, self.hi = lo, hi
        self.boundary = [lo, hi, lo - dt.timedelta(days=1), hi + dt.timedelta(days=1)]

    def sample(self):
        r = self.rng
        if r.random() < 0.10:
            d = r.choice(self.boundary)
        else:
            span = (self.hi - self.lo).days
            d = self.lo + dt.timedelta(days=r.randint(0, max(0, span)))
        return self._maybe_null(d.isoformat())


class TimeSampler(ColumnSampler):
    """time_hhmmss: HH:MM:SS within 00:00:00-23:59:59."""

    def sample(self):
        r = self.rng
        v = '%02d:%02d:%02d' % (r.randrange(24), r.randrange(60), r.randrange(60))
        return self._maybe_null(v)


_PATTERN_CLASSES = {
    'text_enum': EnumSampler,
    'integer_enum': EnumSampler,
    'integer_range': IntegerRangeSampler,
    'text_identifier': IdentifierSampler,
    'text_name': NameSampler,
    'text_free': FreeTextSampler,
    'email': EmailSampler,
    'phone_us': PhoneSampler,
    'ssn_us': SSNSampler,
    'zipcode': ZipcodeSampler,
    'date_iso': DateSampler,
    'time_hhmmss': TimeSampler,
}


def make_column_sampler(column, exception: dict, pool: list, original: list, rng,
                        null_share: float = 0.0) -> ColumnSampler:
    """Pick the sampler by the specification's pattern name; fall back to text_free."""
    pat = (exception or {}).get('pattern', 'text_free')
    cls = _PATTERN_CLASSES.get(pat, FreeTextSampler)
    return cls(column, exception, pool, original, rng, null_share)


def _init_sampler(column, exception, literal_pool, original_values, rng, null_share=0.0):
    """Per-column initialisation used by instance.py."""
    return make_column_sampler(column, exception, literal_pool, original_values, rng, null_share)
