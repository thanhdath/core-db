"""Specification-driven value domains (generation specification, by construction)."""
import re

CHIP_MODELS = ['X3 Advanced', 'X3 Basic', 'X30 high-end', 'X30 low-end', 'X30 mid-range',
               'X3i', 'X5', 'X5 high end']
LAUNCH_YEARS = [2002.0, 2003.0, 2004.0, 2005.0]
LAUNCH_BOUNDARY = [2001.0, 2002.0, 2003.0, 2004.0, 2005.0, 2006.0]
RAM_VALUES = [32.0, 64.0]
ROM_VALUES = [32.0, 48.0, 64.0, 128.0, 256.0]
SLOTS_ENUM = ['1CFII,1SD', '1SD']
WIFI_ENUM = ['No', '802.11b']
BLUETOOTH_ENUM = ['No', '1.1', 'Yes', '1.2']

GRAPHICS_MODES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
CHAR_CELLS = ['80 \u00d7 32', '40 \u00d7 32', '20 \u00d7 32', '80 \u00d7 25', '40 \u00d7 25']
PIXELS = ['640 \u00d7 256', '320 \u00d7 256', '160 \u00d7 256', '640 \u00d7 200', '320 \u00d7 200']
HW_COLOURS = [2.0, 4.0, 8.0]
USED_KB = [8.0, 10.0, 16.0, 20.0]
USED_KB_LITERALS = [10.0, 15.0]
MAPS = ['3000\u20137FFF', '4000\u20137FFF', '5800\u20137FFF', '6000\u20137FFF']
TYPE_ENUM = ['Graphics', 'Text']

COMPANIES = ['Sony Mobile Communications', 'LG Electronics', 'Nokia Corporation',
             'Samsung Electronics Co Ltd', 'HTC Corporation', 'Huawei Technologies Co.Ltd.']
COMPANY_BOUNDARY = ['Nokia Corporation', 'nokia corporation', 'Noion', 'noion', 'Nokia Cor',
                    'nokia cor', 'Nokia n', 'nokia n', 'orporat', 'ORPORAT']
HW_MODELS = ['GT-I9100', 'GT-I9300', 'LG-P760', 'Lumia 920, Lumia 820, Lumia 620', 'Nokia 700',
             'U8815 Asura', 'XPERIA T, XPERIA J', 'Z520e']
ACCRED_TYPES = ['Full', 'Provisional']
ACCRED_TYPE_VARIANTS = ['Full', '%Full%', 'Full%', 'Fulm', 'Fullx', 'full', 'Full x']
ACCRED_LEVELS = ['joyn Hot Fixes', 'joyn', '2', '3', '4']
DATES = ['Approved (awarded 15.11.12)', 'Approved (awarded 19.11.12)', 'Approved (awarded 05.12.12)',
         'Approved (awarded 23.10.12)', 'Approved (valid until 14.09.13)',
         'Approved (valid until 06.04.13)', 'Approved (valid until 03.05.13)']


def case_variant(v, rng) -> str:
    """Case change / truncation / one-char substitution / appended suffix."""
    v = str(v)
    u = rng.random()
    if u < 0.25:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.5 and len(v) > 1:
        k = rng.randint(1, max(1, len(v) - 1))
        return v[:k]
    if u < 0.75 and v:
        i = rng.randrange(len(v))
        c = rng.choice('abcdefghijklmnopqrstuvwxyz')
        return v[:i] + c + v[i + 1:]
    return v + rng.choice(['x', ' ', '1', 'z'])


def near_variant(v, rng) -> str:
    """Case / whitespace / typo variant of a pool value."""
    v = str(v)
    u = rng.random()
    if u < 0.4:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.6:
        return ' ' + v + ' '
    if u < 0.8 and len(v) > 2:
        i = rng.randrange(len(v))
        return v[:i] + v[i + 1:]
    return case_variant(v, rng)


def like_variant(v, rng) -> str:
    """A value that matches a LIKE pattern but differs from the exact literal."""
    v = str(v)
    u = rng.random()
    if u < 0.3:
        return v + rng.choice(['x', ' ', '1'])
    if u < 0.5:
        return v[:-1] + rng.choice('abcdefghijklmnopqrstuvwxyz') if len(v) > 1 else v + 'x'
    if u < 0.7:
        return v.lower()
    return v + ' ' + rng.choice(['x', 'y'])


def one_step_outside(vals: list, rng) -> float:
    """min-1 or max+1 of the observed distinct values."""
    lo, hi = min(vals), max(vals)
    return lo - 1.0 if rng.random() < 0.5 else hi + 1.0


def as_int_if_integral(v: float):
    return int(v) if float(v).is_integer() else v


def _unique_candidates(pool: list, n: int, rng, suffix_fmt: str) -> list:
    """n unique values: the pool first, then suffixed variants until n distinct exist."""
    out = [str(v) for v in pool]
    k = 1
    while len(set(out)) < n:
        out.append(suffix_fmt % (rng.choice(pool), k))
        k += 1
    rng.shuffle(out)
    return out[:n]


def chip_model_names(n: int, rng, existing: set = frozenset()) -> list:
    """Unique per row: pool of 8 observed names plus suffixed variants, fresh against compact PKs."""
    out = _unique_candidates(CHIP_MODELS, n + len(existing), rng, '%s %d')
    seen, keep = set(existing), []
    for v in out:
        if v not in seen:
            seen.add(v)
            keep.append(v)
    k = 1
    while len(keep) < n:
        v = '%s %d' % (rng.choice(CHIP_MODELS), k)
        k += 1
        if v not in seen:
            seen.add(v)
            keep.append(v)
    return keep[:n]


def launch_years(n: int, rng) -> list:
    """Boundary values at 2001..2006; at least two rows share the min (tie at rank 1 ASC)."""
    vals = [2002.0, 2002.0]
    while len(vals) < n:
        u = rng.random()
        if u < 0.2:
            vals.append(rng.choice(LAUNCH_BOUNDARY))
        else:
            vals.append(rng.choice(LAUNCH_YEARS))
    rng.shuffle(vals)
    return [as_int_if_integral(v) for v in vals[:n]]


def ram_values(n: int, rng) -> list:
    """At least two distinct values (32, 64); at least two rows share the minimum."""
    vals = [32.0, 32.0]
    while len(vals) < n:
        u = rng.random()
        if u < 0.2:
            vals.append(one_step_outside(RAM_VALUES, rng))
        else:
            vals.append(rng.choice(RAM_VALUES))
    rng.shuffle(vals)
    return [as_int_if_integral(v) for v in vals[:n]]


def rom_values(n: int, rng) -> list:
    """At least two distinct values; at least two rows share the minimum."""
    vals = [32.0, 32.0]
    while len(vals) < n:
        u = rng.random()
        if u < 0.2:
            vals.append(one_step_outside(ROM_VALUES, rng))
        else:
            vals.append(rng.choice(ROM_VALUES))
    rng.shuffle(vals)
    return [as_int_if_integral(v) for v in vals[:n]]


def enum_values(n: int, enum: list, rng, case_p: float = 0.1) -> list:
    """Uniform enum sample with a case variant with probability case_p."""
    out = []
    for _ in range(n):
        v = str(rng.choice(enum))
        if rng.random() < case_p:
            v = v.upper() if rng.random() < 0.5 else v.lower()
        out.append(v)
    return out


def duplicate_share_values(n: int, pool: list, rng, case_p: float = 0.1) -> list:
    """20-50% duplicate share on DISTINCT: draw from a small subset of the pool."""
    k = max(1, int(round(len(pool) * rng.uniform(0.5, 0.8))))
    sub = rng.sample(pool, min(k, len(pool)))
    out = []
    for _ in range(n):
        v = str(rng.choice(sub))
        if rng.random() < case_p:
            v = case_variant(v, rng)
        out.append(v)
    return out


def graphics_modes(n: int, rng, existing: set = frozenset()) -> list:
    """Unique per row: pool 0..6 plus increments, fresh against compact PKs."""
    out = list(GRAPHICS_MODES)
    k = 7.0
    while len(out) < n + len(existing):
        out.append(k)
        k += 1.0
    rng.shuffle(out)
    seen, keep = set(existing), []
    for v in out:
        if v not in seen:
            seen.add(v)
            keep.append(v)
    while len(keep) < n:
        v = k
        k += 1.0
        if v not in seen:
            seen.add(v)
            keep.append(v)
    return [as_int_if_integral(v) for v in keep[:n]]


def type_values(n: int, rng) -> list:
    """Graphics / graphics (case variant) with 20-50% duplicate share."""
    out = []
    for _ in range(n):
        v = str(rng.choice(TYPE_ENUM))
        if rng.random() < 0.3:
            v = v.lower()
        out.append(v)
    return out


def used_kb_values(n: int, rng) -> list:
    """Observed values plus literals 10 and 15; boundary min-1 / max+1 with p 0.2."""
    pool = USED_KB + USED_KB_LITERALS
    out = []
    for _ in range(n):
        if rng.random() < 0.2:
            out.append(one_step_outside(USED_KB, rng))
        else:
            out.append(rng.choice(pool))
    return [as_int_if_integral(v) for v in out]


def hw_model_names(n: int, rng, existing: set = frozenset()) -> list:
    """Unique per row: pool of 8 observed names plus suffixed variants, fresh against compact PKs."""
    out = _unique_candidates(HW_MODELS, n + len(existing), rng, '%s-%d')
    seen, keep = set(existing), []
    for v in out:
        if v not in seen:
            seen.add(v)
            keep.append(v)
    k = 1
    while len(keep) < n:
        v = '%s-%d' % (rng.choice(HW_MODELS), k)
        k += 1
        if v not in seen:
            seen.add(v)
            keep.append(v)
    return keep[:n]


def company_values(n: int, rng) -> list:
    """Boundary variants (Nokia Corporation, Noion, Nokia Cor, ...) with 20-50% duplicates."""
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.5:
            out.append(str(rng.choice(COMPANY_BOUNDARY)))
        else:
            out.append(str(rng.choice(COMPANIES)))
    return out


def accreditation_types(n: int, rng) -> list:
    """Full / Provisional plus LIKE near-variants (Fulm, Fullx, full, Full x, Full%)."""
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.4:
            out.append(str(rng.choice(ACCRED_TYPE_VARIANTS)))
        elif u < 0.6:
            out.append(like_variant('Full', rng))
        else:
            out.append(str(rng.choice(ACCRED_TYPES)))
    return out


def accreditation_levels(n: int, rng) -> list:
    """Group sizes 1, 2 and >= 3; at least two rows share the maximum (tie at rank 1 DESC)."""
    if n <= 0:
        return []
    vals = ['joyn', 'joyn']
    if n >= 3:
        vals.append('joyn Hot Fixes')
    while len(vals) < n:
        vals.append(str(rng.choice(ACCRED_LEVELS)))
    rng.shuffle(vals)
    return vals[:n]


def date_values(n: int, rng) -> list:
    """Observed date strings; one day earlier/later with p 0.2."""
    out = []
    for _ in range(n):
        v = str(rng.choice(DATES))
        if rng.random() < 0.2:
            m = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', v)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                d = d + 1 if rng.random() < 0.5 else d - 1
                if d < 1:
                    d = 1
                if d > 28:
                    d = 28
                v = v[:m.start()] + '%02d.%02d.%02d' % (d, mo, y) + v[m.end():]
        out.append(v)
    return out
