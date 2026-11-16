"""Per-column samplers built by construction from the spec."""
import datetime as dt
import random

FRESH_SHARE = 0.2


def _fresh_int(rng, lo, hi, pool):
    """Fresh random integer in [lo, hi], with a small chance of the pool."""
    if pool and rng.random() < 0.3:
        return rng.choice(pool)
    return rng.randint(lo, hi)


def _perturb_int(v, rng):
    u = rng.random()
    if u < 0.2:
        return v + 1
    if u < 0.4:
        return v - 1
    if u < 0.6:
        return v + 2
    if u < 0.8:
        return v - 2
    return v


def _perturb_text(v, rng):
    if not v:
        return v
    u = rng.random()
    if u < 0.2:
        return v + ' '
    if u < 0.4:
        return v.lower()
    if u < 0.6:
        return v.upper()
    if u < 0.8:
        return v[:-1]
    return v[1:]


def _n_fresh(n: int) -> int:
    """Number of rows reserved for fresh (unseen) values."""
    return max(1, int(round(FRESH_SHARE * n))) if n > 0 else 0


def _boundary_values(lo, hi, boundaries):
    """L-1, L, L+1 for each boundary plus lo/hi, clamped to [lo, hi], deduped, order kept."""
    out = []
    seen = set()

    def add(v):
        if lo <= v <= hi and v not in seen:
            seen.add(v)
            out.append(v)

    for b in boundaries:
        for d in (-1, 0, 1):
            add(b + d)
    add(lo)
    add(hi)
    return out


def sample_int_range(rng, n, lo, hi, pool, boundaries):
    """Sample n ints in [lo, hi]; boundary values first so truncation keeps them."""
    out = _boundary_values(lo, hi, boundaries)
    n_fresh = _n_fresh(n)
    fresh = []
    for _ in range(n_fresh):
        if pool:
            fresh.append(_perturb_int(rng.choice(pool), rng))
        else:
            fresh.append(_fresh_int(rng, lo, hi, pool))
    out.extend(fresh)
    while len(out) < n:
        out.append(_fresh_int(rng, lo, hi, pool))
    return out[:n]


def sample_int_boundary(rng, n, lo, hi, pool, boundaries):
    """Sample n ints with boundary values (L-1, L, L+1) first, then fresh values."""
    out = _boundary_values(lo, hi, boundaries)
    n_fresh = _n_fresh(n)
    for _ in range(n_fresh):
        if pool:
            out.append(_perturb_int(rng.choice(pool), rng))
        else:
            out.append(_fresh_int(rng, lo, hi, pool))
    while len(out) < n:
        out.append(_fresh_int(rng, lo, hi, pool))
    return out[:n]


def _dup_multiset(rng, n, values, duplicate_share):
    """Construct a multiset of n values with duplicate share in [0.2, 0.5]."""
    if not values:
        return [None] * n
    if n <= 1:
        return [rng.choice(values)]
    lo_d = max(1, int(-(-0.5 * n // 1)))
    hi_d = max(lo_d, int(0.8 * n))
    d = rng.randint(lo_d, hi_d)
    d = min(d, len(values), n)
    if d < 1:
        d = 1
    pool = rng.sample(values, d) if d <= len(values) else list(values)
    counts = [1] * len(pool)
    rem = n - len(pool)
    for _ in range(rem):
        counts[rng.randrange(len(pool))] += 1
    out = []
    for v, c in zip(pool, counts):
        out.extend([v] * c)
    rng.shuffle(out)
    return out


def _group_sizes(values, values_pool, rng):
    """Force group sizes 1, 2 and >= 3 (needs n >= 6)."""
    if len(values) < 6 or len(values_pool) < 3:
        return values
    out = list(values)
    out[0] = values_pool[0]
    out[1] = values_pool[1]
    out[2] = values_pool[1]
    out[3] = values_pool[2]
    out[4] = values_pool[2]
    out[5] = values_pool[2]
    return out


def sample_enum(rng, n, values, duplicate_share=0.0, group_sizes=False, order_ties=False,
                near_variants=None):
    """Sample n values from an enum; duplicate share constructed explicitly."""
    if not values:
        return [None] * n
    if duplicate_share > 0:
        out = _dup_multiset(rng, n, values, duplicate_share)
    else:
        out = [rng.choice(values) for _ in range(n)]
    if order_ties and len(out) >= 2:
        out[0] = out[1]
    if group_sizes:
        out = _group_sizes(out, values, rng)
    if near_variants and n > 0:
        out[rng.randrange(n)] = rng.choice(near_variants)
    return out


def sample_text(rng, n, values, duplicate_share=0.0, near_variants=True, pool_size=3):
    """Sample n text values; if duplicate_share > 0 construct the multiset."""
    if not values:
        return [None] * n
    if duplicate_share > 0:
        out = _dup_multiset(rng, n, values, duplicate_share)
    else:
        out = [rng.choice(values) for _ in range(n)]
    if near_variants:
        for i in range(n):
            if rng.random() < 0.1:
                out[i] = _perturb_text(out[i], rng)
    return out


def sample_date(rng, n, fmt, values):
    """Sample n dates in fmt; draw from the pool (observed +/-1 day) when present."""
    if values:
        out = [rng.choice(values) for _ in range(n)]
    else:
        out = []
        for _ in range(n):
            d = dt.datetime(2000, 1, 1) + dt.timedelta(days=rng.randint(0, 3650))
            out.append(d.strftime(fmt))
    for v in out:
        if v is not None and not _date_ok(v):
            raise ValueError('generated date %r does not match %%Y/%%m/%%d' % (v,))
    return out


def _date_ok(v: str) -> bool:
    """True if v matches [0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]."""
    import re
    return bool(re.fullmatch(r'[0-9]{4}/[0-9]{2}/[0-9]{2}', str(v)))


def sample_primary_key(rng, n, start, existing):
    """Sequential primary keys starting at start, never in existing."""
    out = []
    v = start
    while len(out) < n:
        if v not in existing:
            out.append(v)
        v += 1
    return out


def sample_fk(rng, n, parent_pool, allow_null=True, null_share=0.0, reserve_unmatched=False):
    """Sample FK values from the parent pool."""
    if not parent_pool:
        if not allow_null:
            raise ValueError('empty parent pool for NOT NULL foreign key')
        return [None] * n
    pool = list(parent_pool)
    if reserve_unmatched and len(pool) >= 2:
        pool = pool[:-1]
    out = [rng.choice(pool) for _ in range(n)]
    if allow_null and n > 0:
        if null_share > 0.0:
            k = max(1, int(round(null_share * n)))
        else:
            k = 1
        k = min(k, n - 1) if n > 1 else 1
        for i in rng.sample(range(n), k):
            out[i] = None
    return out
