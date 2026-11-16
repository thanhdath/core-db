"""Specification tables: per-column domains, enums, formats, boundaries, NULL shares."""
import re

ENUMS = {
    ('aircraft', 'Description'): [
        'Light utility helicopter', 'Turboshaft utility helicopter',
        'Tandem rotor helicopter', 'Heavy-lift helicopter'],
}

_WEIGHT_RE = re.compile(r'^\s*([\d,]+)\s*([A-Za-z]+)\s*\(\s*([\d,]+)\s*([A-Za-z]+)\s*\)\s*$')
_PCT_RE = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*%\s*$')

FORMATS = {
    ('aircraft', 'Max_Gross_Weight'): 'weight',
    ('aircraft', 'Total_disk_area'): 'weight',
    ('aircraft', 'Max_disk_Loading'): 'weight',
    ('airport', '%_Change_2007'): 'percent',
}


def parse_weight(s):
    """'1,370 lb (635 kg)' -> (1370.0, 'lb', 635.0, 'kg') or None."""
    if not isinstance(s, str):
        return None
    m = _WEIGHT_RE.match(s)
    if not m:
        return None
    try:
        return (float(m.group(1).replace(',', '')), m.group(2),
                float(m.group(3).replace(',', '')), m.group(4))
    except ValueError:
        return None


def format_weight(a, ua, b, ub):
    """Inverse of parse_weight with thousands separators."""
    def f(x):
        if float(x).is_integer():
            return '{:,}'.format(int(x))
        return '{:,.1f}'.format(x)
    return '%s %s (%s %s)' % (f(a), ua, f(b), ub)


def parse_percent(s):
    if not isinstance(s, str):
        return None
    m = _PCT_RE.match(s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def format_percent(x):
    return ('%.1f%%' % x)


NUMERIC_BOUNDARIES = {
    ('airport', 'Total_Passengers'): [9999999.0, 10000000.0, 10000001.0],
}

LIKE_LITERALS = {
    ('airport', 'Airport_Name'): ['London', 'Londoo', 'London x', 'london'],
}

TEXT_BOUNDARIES = {
    ('match', 'Country'): ['Australia', 'australia'],
}

NULL_SHARE_OVERRIDE = {
    ('airport', 'International_Passengers'): (0.05, 0.30),
}

GROUP_SIZE_COLUMNS = [
    ('aircraft', 'Aircraft'),
    ('pilot', 'Age'),
]

DISTINCT_COLUMNS = [
    ('aircraft', 'Aircraft'),
    ('pilot', 'Name'),
    ('match', 'Location'),
]

AGE_RANGE = (18, 70)

TABLE_SIZES_PER_INSTANCE = {
    'pilot': 12,
    'aircraft': 5,
    'airport': 10,
    'match': 7,
    'airport_aircraft': 4,
}

UNMATCHED_JOIN_FKS = [
    ('match', 'Winning_Pilot'),
    ('match', 'Winning_Aircraft'),
]
