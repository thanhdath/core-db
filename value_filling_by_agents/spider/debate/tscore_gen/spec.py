"""Specification-driven value domains (generation specification, by construction)."""
import re

INT_QUANTITY_RANGE = (1, 500)
INT_AGE_RANGE = (30, 60)
AGE_SEMANTIC_RANGE = (18, 100)
DATE_RANGE = ((2005, 1, 1), (2020, 12, 31))
FRESH_VALUE_SHARE = 0.2
NEAR_DUPLICATE_SHARE = 0.10

PARTY_ENUM = ['Republican', 'Democratic', 'Independent Democrat', 'Anti-Lecompton Democrat']

NAME_DUPLICATE_SHARE = (0.20, 0.50)
PARTY_DUPLICATE_SHARE = (0.20, 0.50)
AGE_BOUNDARY_VALUES = [34, 35, 36, 37]
AUDIENCE_BOUNDARY_VALUES = [177, 178, 179, 199, 200, 201]
GROUP_SIZE_TARGETS = (1, 2, 3)
HAVING_MIN = 2

TABLE_SIZES = {'people': 10, 'debate': 6, 'debate_people': 5}

NULL_TARGETS = []
NOT_NULL_COLUMNS = [('debate_people', 'Negative')]

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December']


def is_nullable(table: str, column: str, column_meta) -> bool:
    """NULL rule: NOT NULL / primary-key columns never get NULL."""
    if column_meta is not None and (column_meta.notnull or column_meta.pk_pos > 0):
        return False
    if (table, column) in NOT_NULL_COLUMNS:
        return False
    return True


def null_target(table: str, column: str) -> bool:
    """True only for columns explicitly listed in the specification's null_targets."""
    return (table, column) in NULL_TARGETS


def format_date(y: int, m: int, d: int) -> str:
    """'Month D, YYYY' (e.g. 'October 21, 2011')."""
    return '%s %d, %d' % (_MONTHS[m - 1], d, y)


def parse_date(s: str):
    """Parse 'Month D, YYYY' -> (y, m, d) or None."""
    m = re.fullmatch(r'\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*', str(s))
    if not m:
        return None
    mon = m.group(1).title()
    if mon not in _MONTHS:
        return None
    return int(m.group(3)), _MONTHS.index(mon) + 1, int(m.group(2))


def near_variant(s: str, rng) -> str:
    """Near-duplicate variant: case / spacing / punctuation perturbation."""
    if not s:
        return s
    u = rng.random()
    if u < 0.34:
        return s.upper() if rng.random() < 0.5 else s.lower()
    if u < 0.67:
        return s + ' '
    return s.replace(' ', '  ', 1) if ' ' in s else s + '.'


def fresh_variant(s: str, rng) -> str:
    """Fresh near-variant not seen in the original pool (prefix/suffix/dropped char)."""
    if not s:
        return s
    u = rng.random()
    if u < 0.25:
        return s + rng.choice([' Jr.', ' Sr.', ' II', ' (new)'])
    if u < 0.5:
        return rng.choice(['Dr. ', 'Hon. ', 'Mr. ']) + s
    if u < 0.75 and len(s) > 2:
        i = rng.randrange(len(s))
        return s[:i] + s[i + 1:]
    return s + rng.choice('abcdefghijklmnopqrstuvwxyz')


def group_size_plan(n: int, rng) -> list:
    """Group sizes covering 1, 2 and >= 3 (specification group_sizes targets)."""
    plan = [1, 2, 3]
    rest = n - sum(plan)
    while rest > 0:
        k = min(rest, rng.choice([1, 2, 3, 4]))
        plan.append(k)
        rest -= k
    rng.shuffle(plan)
    return plan


def joint_plan(n: int, share: tuple, rng) -> list:
    """Group-size plan whose duplicate share lies in `share` (duplicates_for_distinct + group_sizes)."""
    if n <= 0:
        return []
    lo, hi = share
    plan = [1, 2, 3]
    rest = n - sum(plan)
    while rest > 0:
        k = min(rest, rng.choice([1, 2, 3, 4]))
        plan.append(k)
        rest -= k
    def share_of(p):
        return (n - len(p)) / float(n) if n else 0.0
    guard = 0
    while share_of(plan) < lo and guard < 200:
        if len(plan) <= 3:
            break
        plan.sort()
        a = plan.pop(0)
        b = plan.pop(0)
        plan.append(a + b)
        guard += 1
    guard = 0
    while share_of(plan) > hi and guard < 200:
        plan.sort()
        big = plan.pop()
        if big <= 1:
            break
        cut = max(1, big // 2)
        plan.extend([cut, big - cut])
        guard += 1
    if 1 not in plan:
        plan.append(1)
    if 2 not in plan:
        plan.append(2)
    if not any(g >= 3 for g in plan):
        plan.append(3)
    total = sum(plan)
    while total > n and len(plan) > 1:
        plan.sort()
        big = plan.pop()
        if big - 1 > 0:
            plan.append(big - 1)
        total -= 1
    while total < n:
        plan.append(1)
        total += 1
    rng.shuffle(plan)
    return plan


def boundary_plan(n: int, values: list, rng) -> list:
    """Return n values that include every boundary value at least once (comparison_boundary)."""
    out = list(values)
    while len(out) < n:
        out.append(rng.choice(values))
    rng.shuffle(out)
    return out[:n]


def duplicate_plan(n: int, share: tuple, rng) -> list:
    """Return a list of n values where the duplicate share lies in `share`."""
    lo, hi = share
    target = int(round(n * rng.uniform(lo, hi)))
    target = max(1, min(n - 1, target)) if n > 1 else 0
    return [target]
