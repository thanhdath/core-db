"""Specification-driven samplers (round 1)."""
import datetime as dt

ENUMS = {
    ('Course_Authors_and_Tutors', 'author_tutor_ATB'): ('A', 'T', 'B'),
    ('Course_Authors_and_Tutors', 'gender_mf'): ('0', '1'),
    ('Student_Tests_Taken', 'test_result'): ('Pass', 'Fail'),
}

NAME_POOLS = {
    ('Students', 'personal_name'): ['Karson', 'Cathrine', 'Julio', 'Wilson', 'Mariela'],
    ('Subjects', 'subject_name'): ['Computer Science', 'Arts', 'Language'],
}

CROSS_COLUMN_LITERALS = {
    ('Courses', 'course_description'): ('database', 'advanced database'),
    ('Courses', 'course_name'): ('database', 'advanced database'),
}

SPEC_NULL_TARGETS = {('Student_Course_Enrolment', 'student_id'),
                     ('Student_Course_Enrolment', 'course_id'),
                     ('Student_Tests_Taken', 'registration_id')}

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def enum_values(schema, table, column):
    """Return the enum tuple for (table, column), or None."""
    keys = [k for k in ENUMS if k[0].lower() == table.lower() and k[1].lower() == column.lower()]
    return ENUMS[keys[0]] if keys else None


def name_pool(schema, table, column):
    """Return the curated name pool for (table, column), or None."""
    keys = [k for k in NAME_POOLS if k[0].lower() == table.lower() and k[1].lower() == column.lower()]
    return NAME_POOLS[keys[0]] if keys else None


def near_case_variants(value):
    """Case near-variants used by comparison_boundary / like_near_variant."""
    out = []
    if value.lower() != value:
        out.append(value.lower())
    if value.upper() != value:
        out.append(value.upper())
    if value[:1].islower():
        out.append(value[:1].upper() + value[1:])
    elif value[:1].isupper():
        out.append(value[:1].lower() + value[1:])
    return [v for v in dict.fromkeys(out) if v != value]


def duplicate_share(rng):
    """Duplicate share inside 20-50 %."""
    return rng.uniform(0.20, 0.50)


def plan_group_sizes(rng, n, allow_three=True):
    """Return a list of group sizes covering 1, 2 and >= 3 (if n large enough)."""
    if n <= 0:
        return []
    sizes, total = [], 0
    want = [1, 2] + ([3] if allow_three else [])
    rng.shuffle(want)
    for s in want:
        if total + s <= n:
            sizes.append(s)
            total += s
    while total < n:
        s = rng.choice([1, 1, 2, 3, 4])
        s = min(s, n - total)
        sizes.append(s)
        total += s
    rng.shuffle(sizes)
    return sizes


def materialize_group_plan(rng, values, sizes):
    """Assign `values` (a value pool per distinct output) so groups get the planned sizes."""
    if not values:
        return []
    if not sizes:
        return []
    pool = list(dict.fromkeys(values))
    order = []
    if len(pool) <= len(sizes):
        order = list(pool)
        rng.shuffle(order)
    out = []
    for k, s in enumerate(sizes):
        v = order[k] if k < len(order) else rng.choice(pool)
        out.extend([v] * s)
    rng.shuffle(out)
    return out


def shape_distinct_column(rng, values, share=None):
    """Force `share` of duplicate non-NULL values into a column that is a DISTINCT target."""
    share = duplicate_share(rng) if share is None else share
    if len(values) < 2:
        return values
    n_dup = max(1, int(round(len(values) * share)))
    idx = list(range(len(values)))
    rng.shuffle(idx)
    sources = [values[i] for i in idx[:n_dup]]
    targets = idx[n_dup:]
    for i, k in enumerate(targets):
        if rng.random() < share:
            values[k] = sources[i % len(sources)]
    return values


def inject_boundary_literals(rng, values, literals):
    """Ensure every literal appears exactly and a near case-variant of it appears, if possible."""
    if not literals:
        return values
    n = len(values)
    if n == 0:
        return values
    for lit in literals:
        idx = list(range(n))
        rng.shuffle(idx)
        values[idx[0]] = lit
        variants = near_case_variants(lit)
        if variants:
            values[idx[1 % n]] = variants[0]
    return values


def positional_series(n, start, step_seconds=3600):
    """Strictly increasing timestamps (used for ties_for_order_limit ASC targets)."""
    t = start
    out = []
    for _ in range(n):
        out.append(t.strftime(DATETIME_FORMAT))
        t += dt.timedelta(seconds=step_seconds)
    return out


def parse_dt(s):
    """Best-effort parse of a compact timestamp."""
    if isinstance(s, dt.datetime):
        return s
    try:
        return dt.datetime.strptime(str(s)[:19], DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def format_dt(d):
    return d.strftime(DATETIME_FORMAT)


def after_series(rng, base_values, n, min_days=1, max_days=400):
    """Return n datetimes each strictly >= its matching base value."""
    out = []
    for i in range(n):
        base = parse_dt(base_values[i]) if i < len(base_values) else None
        if base is None:
            base = dt.datetime(2015, 1, 1) + dt.timedelta(seconds=rng.randint(0, 2 * 365 * 86400))
        delta = dt.timedelta(days=rng.randint(min_days, max_days), seconds=rng.randint(0, 86399))
        out.append(format_dt(base + delta))
    return out


def plan_parent_histogram(rng, n_children, n_parents, target_fk=None, need_max_group=True):
    """Split n_children over n_parents so counts cover 1, 2, >= 3 (and one > 2)."""
    if n_parents <= 0 or n_children <= 0:
        return [0] * n_parents
    counts = [0] * n_parents
    rng.shuffle_order = None
    order = list(range(n_parents))
    rng.shuffle(order)
    minimal = [1, 2, 3] if need_max_group else [1, 2]
    used = 0
    for k, s in enumerate(minimal):
        if k < n_parents and used + s <= n_children:
            counts[order[k]] = s
            used += s
    rest = n_children - used
    while rest > 0:
        j = rng.choice(order)
        step = min(rest, rng.choice([1, 1, 2, 3]))
        counts[j] += step
        rest -= step
    return counts
