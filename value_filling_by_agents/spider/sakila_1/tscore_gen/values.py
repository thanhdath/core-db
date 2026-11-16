"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']
_WORDS = [
    'ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO', 'FOXTROT', 'GOLF', 'HOTEL', 'INDIA', 'JULIET',
    'KILO', 'LIMA', 'MIKE', 'NOVEMBER', 'OSCAR', 'PAPA', 'QUEBEC', 'ROMEO', 'SIERRA', 'TANGO',
    'UNIFORM', 'VICTOR', 'WHISKEY', 'XRAY', 'YANKEE', 'ZULU', 'NORTH', 'SOUTH', 'EAST', 'WEST',
    'APPLE', 'BANANA', 'CHERRY', 'DRAGON', 'EAGLE', 'FALCON', 'GRAPE', 'HAWK', 'IGLOO', 'JACKET',
    'KETTLE', 'LEMON', 'MANGO', 'NEBULA', 'ORANGE', 'PEBBLE', 'QUARTZ', 'RIVER', 'STONE', 'TIGER',
    'UMBRELLA', 'VIOLET', 'WALNUT', 'XENON', 'YELLOW', 'ZEBRA', 'ANCHOR', 'BREEZE', 'CANDLE', 'DOLPHIN',
    'EMBER', 'FROST', 'GLACIER', 'HARBOR', 'ISLAND', 'JUNGLE', 'KITTEN', 'LANTERN', 'MEADOW', 'NECTAR',
    'OCEAN', 'PRAIRIE', 'QUIVER', 'RAVEN', 'SADDLE', 'THUNDER', 'UPLAND', 'VALLEY', 'WILLOW', 'XEROX',
    'YONDER', 'ZEPHYR', 'AMBER', 'BLAZE', 'CRYSTAL', 'DUSK', 'ETHER', 'FLAME', 'GARNET', 'HORIZON',
    'IVORY', 'JASPER', 'KARMA', 'LUNAR', 'MIRAGE', 'NOVA', 'ONYX', 'PRISM', 'QUASAR', 'RADIANT',
    'SOLAR', 'TWILIGHT', 'ULTRA', 'VORTEX', 'WONDER', 'XENIAL', 'YOUTH', 'ZENITH', 'ARBOR', 'BLOOM',
    'CEDAR', 'DAWN', 'ELM', 'FERN', 'GROVE', 'HAZE', 'IRIS', 'JADE', 'KELP', 'LOTUS',
    'MOSS', 'NIMBUS', 'ORCHID', 'PEARL', 'QUILL', 'ROSE', 'SAGE', 'THYME', 'UMBRA', 'VINE',
    'WHEAT', 'XYLEM', 'YARROW', 'ZINNIA', 'ACORN', 'BIRCH', 'CLOVER', 'DOGWOOD', 'ELDER', 'FIR',
    'GINGER', 'HOLLY', 'IVY', 'JUNIPER', 'KIWI', 'LAUREL', 'MAPLE', 'NUTMEG', 'OAK', 'PINE',
    'QUINCE', 'ROWAN', 'SPRUCE', 'TEAK', 'UMBRELLA', 'VERBENA', 'WALNUT', 'XERANTHEMUM', 'YUCCA', 'ZAMIA',
    'ALDER', 'BAMBOO', 'CACTUS', 'DAISY', 'ELM', 'FIG', 'GINKGO', 'HAZEL', 'INDIGO', 'JASMINE',
    'KALE', 'LILAC', 'MINT', 'NARCISSUS', 'OLIVE', 'POPPY', 'QUINOA', 'RUE', 'SORREL', 'TULIP',
    'UVA', 'VERVAIN', 'WISTERIA', 'XANTHIUM', 'YAM', 'ZUCCHINI', 'AZALEA', 'BEGONIA', 'CROCUS', 'DAHLIA',
    'EDELWEISS', 'FREESIA', 'GARDENIA', 'HEATHER', 'IMPATIENS', 'JONQUIL', 'KALANCHOE', 'LAVENDER', 'MAGNOLIA', 'NIGELLA',
    'ORCHID', 'PEONY', 'QUEEN', 'ROSE', 'SUNFLOWER', 'TANSY', 'URSULA', 'VIOLET', 'WALLFLOWER', 'XEROPHYTE',
    'YARROW', 'ZINNIA', 'ASTER', 'BLUEBELL', 'CAMELLIA', 'DELPHINIUM', 'ERICA', 'FOXGLOVE', 'GERANIUM', 'HYACINTH',
    'IRIS', 'JACARANDA', 'KNAUTIA', 'LUPINE', 'MARIGOLD', 'NEMESIA', 'OSTEOSPERMUM', 'PRIMROSE', 'QUAMASH', 'RUDBECKIA',
    'SALVIA', 'THRIFT', 'UMBELLIFER', 'VERONICA', 'WISTERIA', 'XERANTHEMUM', 'YUCCA', 'ZEPHYRANTHES', 'ANEMONE', 'BORAGE',
    'CALENDULA', 'DIGITALIS', 'ECHINACEA', 'FUMARIA', 'GAZANIA', 'HELIOTROPE', 'IBERIS', 'JASIONE', 'KNIPHOFIA', 'LATHYRUS',
    'MALVA', 'NEPETA', 'OENOTHERA', 'PAPAVER', 'QUERCUS', 'RANUNCULUS', 'SCABIOSA', 'TRIFOLIUM', 'UMBILICUS', 'VERBASCUM',
    'WISTERIA', 'XERANTHEMUM', 'YUCCA', 'ZINNIA', 'ALYSSUM', 'BUDDLEJA', 'CISTUS', 'DIANTHUS', 'ERIGERON', 'FRITILLARIA',
    'GAILLARDIA', 'HELENIUM', 'INCARVILLEA', 'JOVIBARBA', 'KIRENGESHOMA', 'LIBERTIA', 'MECONOPSIS', 'NANDINA', 'OMPHALODES', 'PULMONARIA',
    'QUERCUS', 'RODGERSIA', 'SAXIFRAGA', 'TELLIMA', 'UVULARIA', 'VERONICASTRUM', 'WALDSTEINIA', 'XEROPHYLLUM', 'YPSILANDRA', 'ZIGADENUS',
]


class ColumnSampler:
    """Base fuzzer (fuzz/base.py): drops None elements, p := 1 without elements."""

    def __init__(self, elements: list, p: float, max_l0: float, rng, duplicate_share: float = 0.0):
        self.elements = [e for e in elements if e is not None]
        self.p = p if self.elements else 1.0
        self.max_l0 = max_l0
        self.rng = rng
        self.fresh: list = []
        self.duplicate_share = duplicate_share

    def _fresh_or_reuse(self, draw):
        if len(self.fresh) > self.max_l0:
            return self.rng.choice(self.fresh)
        v = draw()
        self.fresh.append(v)
        return v

    def _maybe_duplicate(self):
        """With probability duplicate_share reuse an already drawn value (DISTINCT targets)."""
        if self.fresh and self.duplicate_share > 0 and self.rng.random() < self.duplicate_share:
            return self.rng.choice(self.fresh)
        return None

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
                 domain=None, duplicate_share=0.0):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng,
                         duplicate_share=duplicate_share)
        self.is_int, self.precision = is_int, precision
        hi = min(10 ** scale, _MAX)
        self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-hi, hi)
        self.list_min = min(self.elements) if self.elements else self.min
        self.list_max = min(self.max, _MAX)
        self.domain = domain

    def _cast(self, v):
        return int(round(v)) if self.is_int else (round(v, self.precision) if self.precision else v)

    def _domain_value(self):
        d = self.domain
        if not d:
            return None
        kind, vals = d
        if kind == 'const':
            return vals
        if kind == 'range' and vals:
            return self.rng.choice(vals)
        if kind == 'boundary' and vals and self.rng.random() < 0.2:
            return self.rng.choice(vals)
        return None

    def sample(self):
        r = self.rng
        dup = self._maybe_duplicate()
        if dup is not None:
            return self._cast(dup)
        dv = self._domain_value()
        if dv is not None:
            return self._cast(dv)
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


class StringSampler(ColumnSampler):
    """fuzz/string.py (allow_none dropped)."""

    def __init__(self, elements, p, max_l0, rng, length=20, domain=None, duplicate_share=0.0):
        els = [str(e) for e in elements if e is not None]
        extra = [e.replace('%', '') for e in els if '%' in e]
        for e in els:
            if re.fullmatch(r'-?\d+', e):
                extra += [str(int(e) + 1), str(int(e) - 1)]
        super().__init__(els + extra, p, max_l0, rng, duplicate_share=duplicate_share)
        self.lo, self.hi = ((min(map(len, self.elements)), max(map(len, self.elements)) + 1)
                            if self.elements else (0, length))
        self.domain = domain

    def _rand(self, k):
        return ''.join(self.rng.choice(CHARSET) for _ in range(k))

    def _domain_value(self):
        d = self.domain
        if not d:
            return None
        kind, vals = d
        if kind == 'enum' and vals:
            return self.rng.choice(vals)
        if kind == 'boundary' and vals and self.rng.random() < 0.2:
            return self.rng.choice(vals)
        return None

    def sample(self):
        r = self.rng
        dup = self._maybe_duplicate()
        if dup is not None:
            return dup
        dv = self._domain_value()
        if dv is not None:
            return dv
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


class WordSampler(StringSampler):
    """Uppercase word pool (varchar_short rule): 3-20 chars, near-variants for equality/LIKE targets."""

    def _rand(self, k):
        w = self.rng.choice(_WORDS)
        return (w * (k // len(w) + 1))[:max(3, min(20, k))]

    def sample(self):
        r = self.rng
        dup = self._maybe_duplicate()
        if dup is not None:
            return dup
        dv = self._domain_value()
        if dv is not None:
            return dv
        if not self.elements or r.random() < self.p:
            v = self._fresh_or_reuse(lambda: self._rand(r.randint(3, 20)))
        else:
            v = r.choice(self.elements)
        if r.random() < 0.3:
            u = r.random()
            if u < 0.25:
                v = v + ' '
            elif u < 0.5:
                v = v.lower()
            elif u < 0.75:
                v = v[:-1]
            else:
                v = v[1:]
        return v


class SpecialFeaturesSampler(ColumnSampler):
    """enum_special_features: random subset of the four features joined by comma, or NULL."""

    def __init__(self, elements, p, max_l0, rng, features, duplicate_share=0.0):
        super().__init__(elements, p, max_l0, rng, duplicate_share=duplicate_share)
        self.features = list(features)

    def sample(self):
        r = self.rng
        dup = self._maybe_duplicate()
        if dup is not None:
            return dup
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
        k = r.randint(1, len(self.features))
        chosen = r.sample(self.features, k)
        return ','.join(chosen)


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

    def __init__(self, elements, p, max_l0, rng, window=None, duplicate_share=0.0):
        super().__init__(elements, p, max_l0, rng, duplicate_share=duplicate_share)
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
        self.full = (dt.datetime(1800, 1, 1), dt.datetime(2100, 1, 1))
        self.rng_dates = (min(parsed), max(parsed)) if len(set(parsed)) >= 2 else self.full
        self.n_parsed = len(set(parsed))
        self.strip0 = not any(s.startswith('0') or '-0' in s for s in strs)
        self.window = window

    def _draw(self):
        r = self.rng
        if self.window is not None:
            lo, hi = self.window
        else:
            lo, hi = self.full if (r.random() < self.p or self.n_parsed <= 1) else self.rng_dates
        d = lo + dt.timedelta(seconds=r.randint(0, int((hi - lo).total_seconds())))
        s = d.strftime(self.template)
        if self.strip0:
            s = re.sub(r'(^|[-/ :])0(\d)', r'\1\2', s)
        return int(s) if self.as_int and s.isdigit() else s

    def sample(self):
        r = self.rng
        dup = self._maybe_duplicate()
        if dup is not None:
            return dup
        if self.elements and r.random() < self.p:
            return r.choice(self.elements)
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
    """fuzz/bool.py (Bool True/False, Bit 1/0); 90% 1 per the boolean rule."""

    def __init__(self, elements, p, max_l0, rng, bit=False):
        super().__init__(elements, p, max_l0, rng)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.9 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, domain=None,
                        window=None, duplicate_share=0.0) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
    els = [e for e in elements if rng.random() < 0.9]
    t = (column.type_str or '').lower().strip()
    args = [int(a) for a in re.findall(r'\d+', (re.search(r'\(([^)]*)\)', t) or [''])[0])][:2] if '(' in t else []
    if t == 'time':
        return TimeSampler(els, p, max_l0, rng)
    if t == '' or t == 'blob':
        return StringSampler(els, p, max_l0, rng, domain=domain, duplicate_share=duplicate_share)
    if 'date' in t or 'timestamp' in t:
        first = next((e for e in els if e is not None), None)
        if first is not None and re.fullmatch(r'-?\d+', str(first)):
            return NumberSampler(els, p, max_l0, rng, scale=4, domain=domain, duplicate_share=duplicate_share)
        return DateSampler(els, p, max_l0, rng, window=window, duplicate_share=duplicate_share)
    if 'bool' in t:
        return BoolSampler(els, p, max_l0, rng)
    if 'bit' in t:
        return BoolSampler(els, p, max_l0, rng, bit=True)
    if 'year' in t:
        return NumberSampler(els, p, max_l0, rng, scale=4, domain=domain, duplicate_share=duplicate_share)
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real')):
        is_int = 'int' in t
        scale, prec = 10, (0 if is_int else 4)
        if args:
            prec = args[1] if len(args) > 1 else 0
            scale = max(args[0] - prec, 0)
        return NumberSampler(els, p, max_l0, rng, scale=scale, is_int=is_int, precision=prec,
                             unsigned='unsigned' in t, domain=domain, duplicate_share=duplicate_share)
    if any(k in t for k in ('char', 'text', 'blob')):
        if domain is None and args and args[0] <= 45:
            return WordSampler(els, p, max_l0, rng, length=args[0], duplicate_share=duplicate_share)
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20, domain=domain,
                             duplicate_share=duplicate_share)
    return StringSampler(els, p, max_l0, rng, domain=domain, duplicate_share=duplicate_share)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), domain=None, window=None, duplicate_share=0.0) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    if domain is not None and domain[0] == 'enum' and column.name.lower() == 'special_features':
        return SpecialFeaturesSampler(els, p, max_l0, rng, domain[1], duplicate_share=duplicate_share)
    return make_column_sampler(column, els, p, max_l0, rng, domain=domain, window=window,
                               duplicate_share=duplicate_share)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf'), domain=None) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0,
                      max_l0, domain=domain)
    return [s.sample() for _ in range(n)]
