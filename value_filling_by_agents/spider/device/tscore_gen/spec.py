"""Specification-driven construction samplers (specification.json -> Python)."""
import random

SPEC = {
    'device': {
        'Device_ID': {'kind': 'int_pk', 'range': (1, 100000)},
        'Device': {'kind': 'text', 'pool': ['BlackBerry Storm 9530', 'Apple', 'Huawei', 'Xiaomi',
                                            'Samsung', 'Galaxy', 'Nokia', 'Pixel', 'Sony', 'Samsung Galaxy'],
                   'dup_share': 0.35, 'null_share': 0.0},
        'Carrier': {'kind': 'text', 'pool': ['MTS Mobility', 'Verizon Wireless', 'Telus Mobility',
                                             'Bell Mobility', 'Iusacell', 'Vodafone AU', 'MTS Mobility',
                                             'T-Mobile', 'Orange'],
                    'dup_share': 0.35, 'null_share': 0.08},
        'Package_Version': {'kind': 'version', 'pool': ['5.0.0.808', '5.0.0.328', '5.0.0.419',
                                                        '4.7.0.208', '5.0.0.742', '5.0.0.419'],
                            'dup_share': 0.30, 'null_share': 0.08},
        'Applications': {'kind': 'version', 'pool': ['5.0.0.419', '5.0.0.328', '4.7.0.151', '5.0.0.451'],
                         'dup_share': 0.30, 'null_share': 0.15},
        'Software_Platform': {'kind': 'enum', 'enum': ['Android', 'iOS'],
                              'dup_share': 0.30, 'null_share': 0.08},
    },
    'shop': {
        'Shop_ID': {'kind': 'int_pk', 'range': (1, 100000)},
        'Shop_Name': {'kind': 'text', 'pool': ['Dinas Device', 'Best Buy', 'Ferndale', 'Apple',
                                               'Pentre store', 'Tynewydd repair', 'Dinas store',
                                               'Naval repair', 'Dinas Device', 'Best Buy'],
                      'dup_share': 0.35, 'null_share': 0.08},
        'Location': {'kind': 'text', 'pool': ['Dinas', 'Cymmer', 'Blaenllechau', 'Pentre', 'Porth',
                                              'Penygraig', 'Gelli', 'Maerdy', 'Dinas'],
                     'dup_share': 0.35, 'null_share': 0.08},
        'Open_Date': {'kind': 'date', 'pool': ['1 January', '15 July', '8 November', '10 June',
                                               '24 February', '11 April', '13 January', '10 December'],
                      'dup_share': 0.10, 'null_share': 0.08},
        'Open_Year': {'kind': 'year', 'range': (2000, 2020), 'null_share': 0.08},
    },
    'stock': {
        'Shop_ID': {'kind': 'fk', 'null_share': 0.0},
        'Device_ID': {'kind': 'fk', 'null_share': 0.0},
        'Quantity': {'kind': 'quantity', 'range': (1, 500), 'null_share': 0.08},
    },
}

TABLE_SIZES = {'device': 8, 'shop': 12, 'stock': 16}

GROUP_SIZE_TARGET = [1, 2, 3]


def _pick(rng, pool):
    return pool[rng.randrange(len(pool))]


def _version(rng, pool):
    """A dotted version string, possibly a fresh variant of a pool member."""
    if rng.random() < 0.5:
        return _pick(rng, pool)
    v = _pick(rng, pool).split('.')
    v = [int(x) for x in v]
    if rng.random() < 0.5:
        v[-1] = max(0, v[-1] + rng.choice([-1, 1, 2]))
    else:
        v[-1] = max(0, v[-1] + rng.choice([-2, 2]))
    return '.'.join(str(x) for x in v)


def _date(rng, pool):
    """A day-month string; keep the pool's month and perturb the day."""
    if rng.random() < 0.5:
        return _pick(rng, pool)
    d = _pick(rng, pool)
    parts = d.split(' ')
    if len(parts) == 2 and parts[0].isdigit():
        day = max(1, min(28, int(parts[0]) + rng.choice([-1, 1, 2])))
        return '%d %s' % (day, parts[1])
    return d


def _text(rng, pool, dup_share):
    """Short text with near-duplicate variants (case, spacing, dropped char)."""
    if rng.random() < dup_share:
        return _pick(rng, pool)
    v = _pick(rng, pool)
    u = rng.random()
    if u < 0.2:
        return v + ' '
    if u < 0.4:
        return v.lower()
    if u < 0.6:
        return v.upper()
    if u < 0.8:
        return v[:-1] if len(v) > 1 else v
    return v[1:] if len(v) > 1 else v


def _enum(rng, enum):
    return enum[rng.randrange(len(enum))]


def _quantity(rng, lo, hi):
    """Positive integer with boundary values 1 and 2 and a step around."""
    u = rng.random()
    if u < 0.2:
        return 1
    if u < 0.4:
        return 2
    if u < 0.5:
        return 3
    return rng.randint(lo, hi)


def _year(rng, lo, hi):
    return rng.randint(lo, hi)


def assign_group_sizes(rng, n, target):
    """Assign n rows to group sizes drawn from target (1, 2, >=3)."""
    sizes = []
    remaining = n
    while remaining > 0:
        g = rng.choice(target)
        if g == 3:
            g = rng.randint(3, max(3, remaining))
        g = min(g, remaining)
        sizes.append(g)
        remaining -= g
    return sizes


def _group_assign(rng, n, values):
    """Assign values to n rows so that group sizes follow target (1, 2, >=3)."""
    sizes = assign_group_sizes(rng, n, GROUP_SIZE_TARGET)
    out = []
    for g in sizes:
        v = values[rng.randrange(len(values))]
        out.extend([v] * g)
    return out


def plant_nulls(rng, values, null_share):
    """Plant NULLs; at least one NULL row when non-nullable and share > 0."""
    if null_share <= 0 or not values:
        return values
    n = len(values)
    k = max(1, int(round(n * null_share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def build_column(rng, spec, n, null_share):
    """Build n values for one column from its spec."""
    kind = spec['kind']
    if kind == 'int_pk':
        vals = list(range(1, n + 1))
    elif kind == 'version':
        vals = _group_assign(rng, n, spec['pool'])
        vals = [_version(rng, spec['pool']) for _ in vals]
    elif kind == 'date':
        vals = _group_assign(rng, n, spec['pool'])
        vals = [_date(rng, spec['pool']) for _ in vals]
    elif kind == 'text':
        vals = _group_assign(rng, n, spec['pool'])
        vals = [_text(rng, spec['pool'], spec.get('dup_share', 0.3)) for _ in vals]
    elif kind == 'enum':
        vals = _group_assign(rng, n, spec['enum'])
        vals = [_enum(rng, spec['enum']) for _ in vals]
    elif kind == 'year':
        lo, hi = spec['range']
        vals = _group_assign(rng, n, [rng.randint(lo, hi) for _ in range(3)])
        vals = [_year(rng, lo, hi) for _ in vals]
    elif kind == 'quantity':
        lo, hi = spec['range']
        vals = _group_assign(rng, n, [rng.randint(lo, hi) for _ in range(3)])
        vals = [_quantity(rng, lo, hi) for _ in vals]
    elif kind == 'fk':
        vals = [None] * n
    else:
        vals = [None] * n
    return plant_nulls(rng, vals, null_share)
