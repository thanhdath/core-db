"""Per-type value generators (fuzz/fuzz.py:40-80, 198-224; fuzz/{base,number,string,date,time,bool}.py)."""
import datetime as dt
import re
import string

_MAX = 2 ** 31 - 1
CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_TEMPLATES = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%Y%m%d', '%Y-%m']

_WORDS = ('the a of and to in that it was for on are with as his they be at one have this from or had by hot '
          'word but what some we can out other were all there when up use your how said an each she which do '
          'their time if will way about many then them write would like so these her long make thing see him '
          'two has look more day could go come did number sound no most people my over know water than call '
          'first who may down side been now find any new work part take get place made live where after back '
          'little only round man year came show every good me give our under name very through just form much '
          'great think say help low line before turn cause same mean differ move right boy old too does tell '
          'sentence set three want air well also play small end put home read hand port large spell add even '
          'land here must big high such follow act why ask men change went light kind off need house picture '
          'try us again animal point mother world near build self earth father head stand own page should '
          'country found answer school grow study still learn plant cover food sun four between state keep '
          'eye never last let thought city tree cross farm hard start might story saw far sea draw left late '
          'run while press close night real life few north open seem together next white children begin got '
          'walk example ease paper group always music those both mark often letter until mile river car feet '
          'care second book carry took science eat room friend began idea fish mountain stop once base hear '
          'horse cut sure watch color face wood main enough plain girl usual young ready above ever red list '
          'though feel talk bird soon body dog family direct pose leave song measure door product black short '
          'numeral class wind question happen complete ship area half rock order fire south problem piece '
          'told knew pass since top whole king space heard best hour better true during hundred five remember '
          'step early hold west ground interest reach fast verb sing listen six table travel less morning ten '
          'simple several vowel toward war lay against pattern slow center love person money serve appear road '
          'map rain rule govern pull cold notice voice unit power town fine certain fly fall lead cry dark '
          'machine note wait plan figure star box noun field rest correct able pound done beauty drive stood '
          'contain front teach week final gave green oh quick develop ocean warm free minute strong special '
          'mind behind clear tail produce fact street inch multiply nothing course stay wheel full force blue '
          'object decide surface deep moon island foot system busy test record boat common gold possible plane '
          'stead dry wonder laugh thousand ago ran check game shape equate miss brought heat snow tire bring '
          'yes distant fill east paint language among grand ball yet wave drop heart am present heavy dance '
          'engine position arm wide sail material fraction forest sit race window store summer train sleep '
          'prove lone leg exercise wall catch mount wish sky board joy winter sat written wild instrument kept '
          'glass grass cow job edge sign visit past soft fun bright gas weather month million bear finish '
          'happy hope flower clothes strange gone jump baby eight village meet root buy raise solve metal '
          'whether push seven paragraph third shall held hair describe cook floor either result burn hill safe '
          'cat century consider type law bit coast copy phrase silent tall sand soil roll temperature finger '
          'industry value fight lie beat excite natural view sense capital will not chair danger fruit rich '
          'thick soldier process operate guess necessary sharp wing create neighbor wash bat rather crowd '
          'corn compare poem string bell depend meat rub tube famous dollar stream fear sight thin triangle '
          'planet hurry chief colony clock mine tie enter major fresh search send yellow gun allow print dead '
          'spot desert suit current lift rose continue block chart hat sell success company subtract event '
          'particular deal swim term opposite wife shoe shoulder spread arrange camp invent cotton born '
          'determine quart nine truck noise level chance gather shop stretch throw shine property column '
          'molecule select wrong gray repeat require broad prepare salt nose plural anger claim continent '
          'oxygen sugar death pretty skill women season solution magnet silver thank branch match suffix '
          'especially fig afraid huge sister steel discuss forward similar guide experience score apple '
          'bought led pitch coat mass card band rope slip win dream evening condition feed tool total basic '
          'smell valley nor double seat arrive master track parent shore division sheet substance favor '
          'connect post spend chord fat glad original share station dad bread charge proper bar offer segment '
          'slave duck instant market degree populate chick dear enemy reply drink occur support speech nature '
          'range steam motion path liquid log meant quotient teeth shell neck oxygen')


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

    def __init__(self, elements, p, max_l0, rng, scale=10, is_int=True, precision=0, unsigned=False,
                 lo=None, hi=None):
        super().__init__([f for f in (_num(e) for e in elements) if f is not None], p, max_l0, rng)
        self.is_int, self.precision = is_int, precision
        if lo is not None and hi is not None:
            self.min, self.max = lo, hi
        else:
            h = min(10 ** scale, _MAX)
            self.min, self.max = (0, min(2 * 10 ** scale, _MAX)) if unsigned else (-h, h)
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
        if v < self.min:
            v = self.min
        if v > self.max:
            v = self.max
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


class ShortTextSampler(ColumnSampler):
    """Small pool of 20-50 distinct strings with 5% case/whitespace near-variants."""

    def __init__(self, elements, p, max_l0, rng, pool_size=30):
        els = [str(e) for e in elements if e is not None]
        base = list(dict.fromkeys(els))
        while len(base) < pool_size:
            base.append(''.join(rng.choice(string.ascii_uppercase) for _ in range(rng.randint(3, 9))))
        base = base[:max(pool_size, min(len(base), 50))]
        super().__init__(base, p, max_l0, rng)

    def sample(self):
        r = self.rng
        v = r.choice(self.elements)
        if r.random() < 0.05:
            u = r.random()
            if u < 0.4:
                v = v.lower()
            elif u < 0.7:
                v = v.upper()
            else:
                v = ' ' + v + ' '
        return v


class LongTextSampler(ColumnSampler):
    """Random sentence of 100-400 chars assembled from a word pool."""

    def __init__(self, elements, p, max_l0, rng):
        super().__init__([str(e) for e in elements if e is not None], p, max_l0, rng)

    def _sentence(self):
        r = self.rng
        target = r.randint(100, 400)
        out = []
        n = 0
        while n < target:
            w = r.choice(_WORDS.split())
            out.append(w)
            n += len(w) + 1
        s = ' '.join(out)
        return s[:400]

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(self._sentence)


def _parse_date(s: str):
    s = re.sub(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', lambda m: m.group(1).title(), s.strip())
    for t in _TEMPLATES:
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


class DateSampler(ColumnSampler):
    """fuzz/date.py + utils/data_parser.py; domain 1920-01-01..2010-12-31 ISO."""

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
        self.full = (dt.datetime(1920, 1, 1), dt.datetime(2010, 12, 31))
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
    """fuzz/time.py; domain 00:00:00..03:00:00 formatted H:MM:SS."""

    def sample(self):
        r = self.rng
        if self.elements and r.random() >= self.p:
            e = str(r.choice(self.elements))
            parts = e.split(':')
            if len(parts) == 3 and all(x.isdigit() for x in parts) and r.random() < self.p:
                i = r.randrange(3)
                rngs = [list(range(4)), list(range(60)), list(range(60))]
                parts[i] = '%02d' % rngs[i][int(parts[i]) % len(rngs[i]) - 1]
                e = ':'.join(parts)
            return e
        return '%d:%02d:%02d' % (r.randrange(4), r.randrange(60), r.randrange(60))


class MoneySampler(ColumnSampler):
    """'$#,###,###.##' with 2 decimals; ties at rank 1 supported by a shared top value."""

    def __init__(self, elements, p, max_l0, rng, top=None, lo=0, hi=500000000):
        super().__init__([str(e) for e in elements if e is not None], p, max_l0, rng)
        self.top = top
        self.lo, self.hi = lo, hi

    def _fmt(self, amount):
        return '${:,.2f}'.format(amount)

    def sample(self):
        r = self.rng
        if self.top is not None and r.random() < 0.15:
            return self.top
        if self.elements and r.random() >= self.p:
            return r.choice(self.elements)
        return self._fresh_or_reuse(lambda: self._fmt(r.randint(self.lo, self.hi) + r.random()))


class BoolSampler(ColumnSampler):
    """fuzz/bool.py (Bool True/False, Bit 1/0)."""

    def __init__(self, elements, p, max_l0, rng, bit=False):
        super().__init__(elements, p, max_l0, rng)
        self.vals = (1, 0) if bit else (True, False)

    def sample(self):
        if not self.elements or self.rng.random() < self.p:
            return self.vals[0] if self.rng.random() < 0.5 else self.vals[1]
        return self.rng.choice(self.elements)


def make_column_sampler(column, elements: list, p: float, max_l0: float, rng, **kw) -> ColumnSampler:
    """Pick the fuzzer by declared type (fuzz/fuzz.py:40-80); unknown types fall back to String."""
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
                             unsigned='unsigned' in t, lo=kw.get('lo'), hi=kw.get('hi'))
    if any(k in t for k in ('char', 'text', 'blob')):
        return StringSampler(els, p, max_l0, rng, length=args[0] if args else 20)
    return StringSampler(els, p, max_l0, rng)


def _init_sampler(column, literal_pool: list, original_values, p: float, rng, n_pk: int,
                  max_l0: float = float('inf'), **kw) -> ColumnSampler:
    """Per-column initialisation of fuzz/fuzz.py:198-224."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, **kw)


def random_values_for_a_column(column_meta, literal_pool: list, n: int, rng, *, original_values: list = (),
                               p: float = 0.2, max_l0: float = float('inf')) -> list:
    """Initialise one column fuzzer (fuzz.py:198-224) and draw n values."""
    s = _init_sampler(column_meta, literal_pool, original_values, p, rng, 1 if column_meta.pk_pos else 0, max_l0)
    return [s.sample() for _ in range(n)]
