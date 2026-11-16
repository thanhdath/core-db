"""Specification implemented by construction (round 1)."""
import random

TABLE_SIZES = {'manufacturer': 7, 'furniture': 7, 'furniture_manufacte': 5}

NULL_TARGETS = [
    ('manufacturer', 'Open_Year'), ('manufacturer', 'Name'), ('manufacturer', 'Num_of_Factories'),
    ('manufacturer', 'Num_of_Shops'), ('furniture', 'Name'), ('furniture', 'Num_of_Component'),
    ('furniture', 'Market_Rate'), ('furniture_manufacte', 'Price_in_Dollar'),
]

COMPONENT_BOUNDARY = [5, 6, 7, 9, 10, 11]
COMPONENT_LITERALS = [6, 10]

_NAME_POOL = ['Billiard table', 'Chabudai', 'Bookcase', 'Hatstand', 'Bench', 'Four-poster bed',
              'Dining set', 'Wardrobe', 'Sideboard', 'Stool', 'Armchair', 'Desk']
_MANUF_POOL = ['Chevrolet House', 'IKEA', 'Ford Make', 'Jiaju', 'Chevrolet', 'Dodge', 'Tomorrow',
               'Nitori', 'Muji', 'Ashley', 'Ikea', 'Habitat']


def _fresh_int(rng, lo, hi):
    return rng.randint(lo, hi)


def _fresh_real(rng, lo, hi, nd=1):
    return round(rng.uniform(lo, hi), nd)


def _dup_share(rng, n):
    """Number of duplicate rows for a 20-50 % duplicate share."""
    lo = max(1, int(round(0.2 * n)))
    hi = max(lo, int(round(0.5 * n)))
    return rng.randint(lo, hi)


def _apply_duplicates(values, rng, share):
    """Make ``share`` values duplicates of another row's value (DISTINCT reduces count)."""
    n = len(values)
    if n < 2:
        return values
    k = min(share, n - 1)
    idx = list(range(n))
    rng.shuffle(idx)
    for j in range(k):
        src = idx[j]
        dst = idx[(j + 1) % n]
        values[dst] = values[src]
    return values


def _plant_nulls(values, rng, nullable=True):
    """Plant at least one NULL in a nullable column (sparse share)."""
    if not nullable or not values:
        return values
    if any(v is None for v in values):
        return values
    i = rng.randrange(len(values))
    values[i] = None
    return values


def _build_manufacturer(rng, n):
    ids = list(range(1, n + 1))
    years = [1980.0, 1990.0, 1991.0, 1992.0, 2000.0, 2001.0, 2008.0][:n]
    while len(years) < n:
        years.append(_fresh_real(rng, 1900.0, 2025.0))
    if n >= 2:
        years[-1] = years[-2]
    names = [_MANUF_POOL[i % len(_MANUF_POOL)] for i in range(n)]
    names = _apply_duplicates(names, rng, _dup_share(rng, n))
    factories = [_fresh_int(rng, 1, 100) for _ in range(n)]
    if n >= 2:
        factories[0] = 36
        factories[1] = 21
    shops = [_fresh_int(rng, 1, 100) for _ in range(n)]
    if n >= 3:
        shops[0] = 8
        shops[1] = 8
        shops[2] = 19
    return {'Manufacturer_ID': ids, 'Open_Year': years, 'Name': names,
            'Num_of_Factories': factories, 'Num_of_Shops': shops}


def _build_furniture(rng, n):
    ids = list(range(1, n + 1))
    names = [_NAME_POOL[i % len(_NAME_POOL)] for i in range(n)]
    names = _apply_duplicates(names, rng, _dup_share(rng, n))
    comps = [_fresh_int(rng, 1, 100) for _ in range(n)]
    for j, v in enumerate(COMPONENT_BOUNDARY):
        if j < n:
            comps[j] = v
    rates = [_fresh_real(rng, 0.0, 5000.0) for _ in range(n)]
    if n >= 4:
        rates[0] = 52.5
        rates[1] = 52.5
        rates[2] = 40.0
        rates[3] = 40.0
        rates[4] = 1.0 if n > 4 else rates[4]
    return {'Furniture_ID': ids, 'Name': names, 'Num_of_Component': comps, 'Market_Rate': rates}


def _build_furniture_manufacte(rng, n, manu_ids, furn_ids):
    """Child rows: FK values from parents; group sizes 1,2,>=3; MAX(price) tie at rank 1."""
    if not manu_ids or not furn_ids:
        return {'Manufacturer_ID': [], 'Furniture_ID': [], 'Price_in_Dollar': []}
    plan = []
    if len(manu_ids) >= 1:
        plan.append(manu_ids[0])
    if len(manu_ids) >= 2:
        plan += [manu_ids[1], manu_ids[1]]
    if len(manu_ids) >= 3:
        plan += [manu_ids[2], manu_ids[2], manu_ids[2]]
    while len(plan) < n:
        plan.append(rng.choice(manu_ids))
    plan = plan[:n]
    if len(manu_ids) >= 2:
        last = manu_ids[-1]
        plan = [m for m in plan if m != last] or plan
        while len(plan) < n:
            plan.append(rng.choice(manu_ids[:-1]))
        plan = plan[:n]
    fids = []
    used = set()
    for m in plan:
        cand = [f for f in furn_ids if (m, f) not in used]
        if not cand:
            cand = list(furn_ids)
        f = rng.choice(cand)
        used.add((m, f))
        fids.append(f)
    prices = [_fresh_real(rng, 0.0, 5000.0) for _ in range(n)]
    if n >= 2:
        prices[0] = 2124.0
        prices[1] = 2124.0
    return {'Manufacturer_ID': plan, 'Furniture_ID': fids, 'Price_in_Dollar': prices}


def build_spec_instance(schema, pool, rng):
    """Return generated rows per table (spec sizes, ties, group sizes, NULL rule)."""
    sizes = dict(TABLE_SIZES)
    manu = _build_manufacturer(rng, sizes['manufacturer'])
    furn = _build_furniture(rng, sizes['furniture'])
    fm = _build_furniture_manufacte(rng, sizes['furniture_manufacte'],
                                    manu['Manufacturer_ID'], furn['Furniture_ID'])
    inst = {'manufacturer': manu, 'furniture': furn, 'furniture_manufacte': fm}
    for t, c in NULL_TARGETS:
        if t in inst and c in inst[t]:
            _plant_nulls(inst[t][c], rng)
    return inst
