"""Specification implemented by construction (no SQL evaluation)."""
import datetime as dt
import re
import string

STATUS_ENUM = ['Operating', 'Opening', 'Closed', 'SBNO']
STATUS_NEAR_VARIANTS = ['opening', 'operating']
STATUS_ORDER = ['Operating', 'Opening', 'Closed', 'SBNO', 'opening', 'operating']

COUNTRY_NAMES = ['Austria', 'Finland', 'Sweden', 'Norway', 'Denmark', 'Iceland',
                 'Germany', 'France', 'Italy', 'Spain', 'Poland', 'Portugal']
LANGUAGES = ['German', 'Finnish Swedish', 'Swedish', 'Norwegian', 'Danish', 'English',
             'French', 'Italian', 'Spanish', 'Polish', 'Portuguese']

PARK_NAMES = ['Kemah Boardwalk', 'Happy Valley', 'Mt. Olympus', 'Waldameer', 'Grona Lund',
              'Holiday World', 'Cedar Point', 'Six Flags', 'Europa Park', 'Alton Towers',
              'Blackpool Pleasure Beach', 'PortAventura', 'Tivoli Gardens', 'Liseberg']

COASTER_NAMES = ['Boardwalk Bullet', 'Dauling Dragon', 'Hades 360', 'Ravine Flyer II',
                 'Twister', 'The Voyage', 'Steel Dragon', 'Iron Shark', 'Blue Streak',
                 'Comet', 'Cyclone', 'Wildcat', 'Thunderbolt', 'Rattler', 'Goliath',
                 'Maverick', 'Millennium Force', 'Behemoth', 'Leviathan', 'Banshee']

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December']

_ALPHA = string.ascii_letters


def rand_name(rng, lo=3, hi=20):
    """Random short alphabetic string 3-20 chars (text_name rule)."""
    k = rng.randint(lo, hi)
    return ''.join(rng.choice(_ALPHA) for _ in range(k))


def rand_date_text(rng, lo_year=1990, hi_year=2020):
    """'Month D, YYYY' or 'YYYY' sampled from 1990-01-01 .."""
    lo = dt.date(lo_year, 1, 1)
    hi = dt.date(hi_year, 12, 31)
    d = lo + dt.timedelta(days=rng.randint(0, (hi - lo).days))
    if rng.random() < 0.5:
        return '%s %d, %d' % (_MONTHS[d.month - 1], d.day, d.year)
    return '%d' % d.year


def rand_numeric_string(rng, lo=10.0, hi=200.0):
    """Numeric string in [10.0, 200.0] with one decimal (text_numeric_string rule)."""
    return '%.1f' % rng.uniform(lo, hi)


def rand_real_measure(rng, lo=10.0, hi=10000.0):
    """Positive real with one decimal (real_measure rule)."""
    return round(rng.uniform(lo, hi), 1)


def rand_int_quantity(rng, lo=1, hi=1000):
    """Positive integer in [1, 1000] (integer_quantity rule)."""
    return rng.randint(lo, hi)


def rand_int_area_population(rng, lo=1000, hi=100000000):
    """Positive integer in [1000, 1e8] (integer_area_population rule)."""
    return rng.randint(lo, hi)


def near_duplicate(rng, s):
    """Case / whitespace near-duplicate variant of a string (text_name rule)."""
    u = rng.random()
    if u < 0.4:
        return s.upper() if rng.random() < 0.5 else s.lower()
    if u < 0.7:
        return ' ' + s
    return s + ' '


def boundary_values_int(c):
    """L, L-1, L+1 for an integer literal (boundary_numeric rule)."""
    return [c, c - 1, c + 1]


def boundary_values_real(c, step=0.1):
    """L, L-step, L+step for a real literal (boundary_numeric rule)."""
    return [round(c, 4), round(c - step, 4), round(c + step, 4)]


def null_share_for(column, schema):
    """NULL share of a nullable column: follow the compact database's share, >= 1 row."""
    if column.notnull or column.pk_pos > 0:
        return 0.0
    vals = schema.original_values.get((column.table, column.name), [])
    if not vals:
        return 0.1
    n_null = sum(1 for v in vals if v is None)
    share = n_null / float(len(vals))
    return max(share, 0.1)


def plant_nulls(values, share, rng, force_one=True):
    """Replace a share of values by None; guarantee at least one NULL (NULL rule)."""
    n = len(values)
    if n == 0 or share <= 0.0:
        return values
    k = int(round(share * n))
    if force_one:
        k = max(k, 1)
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def status_values_for_groups(rng, n):
    """Status values with group sizes 1, 2, 3 and >=4, 20-50% duplicates, two values tied at top count and two tied
    at second count, and the comparison-boundary literals 'Opening'/'Operating' (+ near variants)."""
    base = (['Operating'] * 4 + ['Opening'] * 3 + ['Closed'] * 2 + ['SBNO'] * 1)
    vals = list(base)
    while len(vals) < n:
        vals.append(rng.choice(STATUS_ENUM))
    vals = vals[:n]
    must = ['Operating', 'Opening']
    for m in must:
        if m not in vals:
            vals[rng.randrange(n)] = m
    if n >= 6:
        for v in STATUS_NEAR_VARIANTS:
            if v not in vals:
                vals[rng.randrange(n)] = v
    from collections import Counter
    cnt = Counter(vals)
    ordered = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) >= 2:
        top = ordered[0][1]
        second = ordered[1][0]
        need = top - cnt[second]
        if need > 0:
            for _ in range(need):
                low = min(cnt, key=lambda k: (cnt[k], k))
                if low == second or cnt[low] <= 0:
                    break
                i = vals.index(low)
                vals[i] = second
                cnt[low] -= 1
                cnt[second] += 1
    rng.shuffle(vals)
    return vals


def country_id_values(rng, n, parent_ids):
    """Country_ID values for the country table: groups of size 1, 2 and >=3, 20-50% duplicates, at least one parent
    row without children (handled by the caller via the FK pool)."""
    return list(range(1, n + 1))


def country_name_values(rng, n):
    """Country Name values: group sizes 1, 2, >=3, 20-50% duplicates, aggregate boundary (groups of size 0,1,2)."""
    vals = []
    pool = list(COUNTRY_NAMES)
    rng.shuffle(pool)
    vals += [pool[0]] * 1 + [pool[1]] * 2 + [pool[2]] * 3
    while len(vals) < n:
        vals.append(rng.choice(pool))
    vals = vals[:n]
    if n >= 2 and len(set(vals)) == n:
        vals[-1] = vals[0]
    rng.shuffle(vals)
    return vals


def coaster_country_id_values(rng, n, parent_ids):
    """Child FK values: groups of size 0,1,2 and >=3, 20-50% duplicates, two rows sharing the maximum Country_ID (tie
    at rank 1 DESC), and at least one NULL (NULL rule handled by caller)."""
    if not parent_ids:
        return [None] * n
    pids = sorted(parent_ids)
    vals = []
    if len(pids) >= 3:
        vals += [pids[0]] * 1 + [pids[1]] * 2 + [pids[2]] * 3
    else:
        vals += [pids[0]] * 2
    while len(vals) < n:
        vals.append(rng.choice(pids))
    vals = vals[:n]
    mx = max(pids)
    if vals.count(mx) < 2:
        for i in range(n):
            if vals[i] != mx:
                vals[i] = mx
                if vals.count(mx) >= 2:
                    break
    rng.shuffle(vals)
    return vals


def length_values(rng, n):
    """Length: two rows share the maximum and two share the minimum (tie at rank 1 and 100, ASC and DESC); >=2
    distinct values per group."""
    vals = [rand_real_measure(rng) for _ in range(n)]
    if n >= 4:
        mx = max(vals)
        mn = min(vals)
        vals[0] = mx
        vals[1] = mx
        vals[2] = mn
        vals[3] = mn
    return vals


def speed_values(rng, n):
    """Speed (TEXT numeric): 20-50% duplicates, group sizes 1,2,>=3, >=2 distinct values per group."""
    vals = [rand_numeric_string(rng) for _ in range(n)]
    if n >= 3:
        vals[0] = vals[1]
        if n >= 4:
            vals[2] = vals[3]
    return vals


def height_values(rng, n):
    """Height: two rows share the maximum (tie at rank 1 DESC)."""
    vals = [rand_real_measure(rng) for _ in range(n)]
    if n >= 2:
        mx = max(vals)
        vals[0] = mx
        vals[1] = mx
    return vals


def opened_values(rng, n):
    """Opened: two rows share the maximum date (tie at rank 1 DESC)."""
    vals = [rand_date_text(rng) for _ in range(n)]
    if n >= 2:
        mx = max(vals)
        vals[0] = mx
        vals[1] = mx
    return vals


def coaster_name_values(rng, n):
    """Coaster Name: distinct-ish names with 5% near-duplicate variants."""
    vals = []
    for _ in range(n):
        if vals and rng.random() < 0.05:
            vals.append(near_duplicate(rng, rng.choice(vals)))
        else:
            vals.append(rng.choice(COASTER_NAMES) if rng.random() < 0.5 else rand_name(rng))
    return vals


def park_values(rng, n):
    """Park: enum-ish names."""
    return [rng.choice(PARK_NAMES) if rng.random() < 0.7 else rand_name(rng) for _ in range(n)]


def languages_values(rng, n):
    """Languages: enum list, includes 'German' (literal pool)."""
    vals = [rng.choice(LANGUAGES) for _ in range(n)]
    if n >= 1 and 'German' not in vals:
        vals[0] = 'German'
    return vals
