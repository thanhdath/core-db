"""Instance row generation by construction."""
import random

from .values import _init_sampler


TABLE_SIZES = {'course': 13, 'prof': 10, 'student': 38, 'RA': 35, 'registration': 101}

RANGES = {
    ('course', 'credit'): (2, 3),
    ('course', 'diff'): (1, 5),
    ('prof', 'popularity'): (2, 3),
    ('prof', 'teachingability'): (1, 5),
    ('student', 'intelligence'): (1, 5),
    ('registration', 'sat'): (1, 5),
    ('RA', 'capability'): (1, 5),
}
ENUMS = {
    ('prof', 'gender'): ['Male', 'Female'],
    ('student', 'type'): ['RPG', 'TPG', 'UG'],
    ('registration', 'grade'): ['A', 'B', 'C', 'D'],
    ('RA', 'salary'): ['low', 'med', 'high', 'free'],
}
BOUNDARY_TEXT = {
    ('course', 'name'): ['Machine Learning Theory', 'machine learning theory',
                         'Computer Network', 'computer network',
                         'Intro to BlockChain', 'intro to blockchain'],
    ('student', 'l_name'): ['Unsworth', 'unsworth', 'Antonio', 'antonio', 'Rechert', 'rechert'],
    ('student', 'f_name'): ['Rik', 'rik', 'Laughton', 'laughton', 'Willie', 'willie'],
    ('prof', 'first_name'): ['Ogdon', 'ogdon', 'Sauveur', 'sauveur'],
    ('prof', 'last_name'): ['Skyme', 'skyme', 'Zywicki', 'zywicki', 'Zhou', 'zhou'],
}
BOUNDARY_INT = {
    ('RA', 'capability'): [2, 3, 4],
}


def _existing_keys(schema, table: str) -> set:
    tm = schema.tables[table]
    pk = tm.primary_key
    if not pk:
        return set()
    cols = schema.original_values
    n = len(cols.get((table, pk[0]), []))
    return {tuple(cols[(table, c)][i] for c in pk) for i in range(n)}


def _existing_fk_values(schema, table: str, col: str) -> list:
    return [v for v in schema.original_values.get((table, col), []) if v is not None]


def _max_int(schema, table: str, col: str, default=0) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return max(vals) if vals else default


def _clamp(v, lo, hi):
    if v is None:
        return None
    try:
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v
    except TypeError:
        return v


def _clamp_col(table, col, vals):
    rng_ = RANGES.get((table, col))
    if rng_ is None:
        return vals
    lo, hi = rng_
    return [_clamp(v, lo, hi) for v in vals]


def _enum_col(table, col, vals):
    allowed = ENUMS.get((table, col))
    if allowed is None:
        return vals
    return [v if v in allowed else allowed[0] for v in vals]


def _text_dup_share(rng) -> float:
    return rng.uniform(0.2, 0.5)


def _null_share(rng, lo=0.05, hi=0.30) -> float:
    return rng.uniform(lo, hi)


def _inject_duplicates(vals: list, rng, share: float) -> list:
    """Replicate distinct source values so the measured duplicate share falls in [share, share+0.1]."""
    n = len(vals)
    if n < 2:
        return vals
    n_dup = max(1, int(n * share))
    n_dup = min(n_dup, n - 1)
    srcs = rng.sample(range(n), min(n_dup, n))
    out = list(vals)
    for j in range(n_dup):
        out[j] = vals[srcs[j]]
    return out


def _fresh_ids(schema, table, pk, n_new):
    existing = _existing_keys(schema, table)
    start = _max_int(schema, table, pk, 0) + 1
    ids = []
    i = start
    while len(ids) < n_new:
        if (i,) not in existing:
            ids.append(i)
        i += 1
    return ids


def _sample_text_col(schema, pool, rng, table, col, n_new, boundary_key=None):
    """Sample a text column: boundary literals first, then sampler values, then duplicate injection."""
    vals = []
    boundary = BOUNDARY_TEXT.get((table, col)) if boundary_key is None else BOUNDARY_TEXT.get(boundary_key)
    if boundary:
        for j in range(min(n_new, len(boundary))):
            vals.append(boundary[j])
    sampler = _init_sampler(
        next(c for c in schema.tables[table].columns if c.name == col),
        pool.get((table, col), []),
        schema.original_values.get((table, col), []), 0.2, rng, 1)
    while len(vals) < n_new:
        vals.append(sampler.sample())
    share = _text_dup_share(rng)
    return _inject_duplicates(vals, rng, share)


def _sample_int_col(schema, pool, rng, table, col, n_new, boundary=None):
    sampler = _init_sampler(
        next(c for c in schema.tables[table].columns if c.name == col),
        pool.get((table, col), []),
        schema.original_values.get((table, col), []), 0.2, rng, 1)
    vals = [sampler.sample() for _ in range(n_new)]
    if boundary:
        for j in range(min(n_new, len(boundary))):
            vals[j] = boundary[j]
    vals = _clamp_col(table, col, vals)
    if n_new >= 2:
        vals[-1] = vals[0]
    return vals


def _gen_student(schema, pool, rng, n_new: int) -> dict:
    tm = schema.tables['student']
    pk = tm.primary_key[0] if tm.primary_key else 'student_id'
    cols = {c.name: [] for c in tm.columns}
    cols[pk] = _fresh_ids(schema, 'student', pk, n_new)
    for c in tm.columns:
        if c.name == pk:
            continue
        t = (c.type_str or '').lower()
        if 'text' in t:
            cols[c.name] = _sample_text_col(schema, pool, rng, 'student', c.name, n_new)
        elif 'real' in t or 'float' in t or 'double' in t:
            vals = [round(rng.uniform(0.0, 4.0), 2) for _ in range(n_new)]
            if n_new >= 2:
                vals[-1] = vals[0]
            cols[c.name] = vals
        else:
            cols[c.name] = _sample_int_col(schema, pool, rng, 'student', c.name, n_new)
    return cols


def _gen_prof(schema, pool, rng, n_new: int) -> dict:
    tm = schema.tables['prof']
    pk = tm.primary_key[0] if tm.primary_key else 'prof_id'
    cols = {c.name: [] for c in tm.columns}
    cols[pk] = _fresh_ids(schema, 'prof', pk, n_new)
    for c in tm.columns:
        if c.name == pk:
            continue
        t = (c.type_str or '').lower()
        if 'text' in t:
            cols[c.name] = _sample_text_col(schema, pool, rng, 'prof', c.name, n_new)
        else:
            vals = _sample_int_col(schema, pool, rng, 'prof', c.name, n_new)
            vals = _enum_col('prof', c.name, vals)
            cols[c.name] = vals
    if n_new >= 6 and 'first_name' in cols:
        fn = cols['first_name']
        fn[0] = fn[1] = fn[2] = 'Ogdon'
        fn[3] = fn[4] = 'Sauveur'
        fn[5] = 'Merwyn'
    return cols


def _gen_course(schema, pool, rng, n_new: int) -> dict:
    tm = schema.tables['course']
    pk = tm.primary_key[0] if tm.primary_key else 'course_id'
    cols = {c.name: [] for c in tm.columns}
    cols[pk] = _fresh_ids(schema, 'course', pk, n_new)
    for c in tm.columns:
        if c.name == pk:
            continue
        t = (c.type_str or '').lower()
        if 'text' in t:
            cols[c.name] = _sample_text_col(schema, pool, rng, 'course', c.name, n_new)
        else:
            boundary = [5, 4, 3, 2] if c.name == 'diff' else None
            cols[c.name] = _sample_int_col(schema, pool, rng, 'course', c.name, n_new, boundary=boundary)
    if n_new >= 3 and 'name' in cols:
        nm = cols['name']
        nm[0] = nm[1] = nm[2] = 'Machine Learning Theory'
    return cols


def _gen_registration(schema, pool, rng, n_new: int, students: dict, courses: dict) -> dict:
    tm = schema.tables['registration']
    cols = {c.name: [] for c in tm.columns}
    stu_ids = _existing_fk_values(schema, 'registration', 'student_id') + list(students.get('student_id', []))
    crs_ids = _existing_fk_values(schema, 'registration', 'course_id') + list(courses.get('course_id', []))
    stu_ids = [v for v in stu_ids if v is not None]
    crs_ids = [v for v in crs_ids if v is not None]
    existing_pairs = set()
    n_ex = len(schema.original_values.get(('registration', 'course_id'), []))
    for i in range(n_ex):
        existing_pairs.add((schema.original_values[('registration', 'course_id')][i],
                            schema.original_values[('registration', 'student_id')][i]))
    childless_students = set(stu_ids[:max(1, len(stu_ids) // 8)]) if stu_ids else set()
    childless_courses = set(crs_ids[:max(1, len(crs_ids) // 8)]) if crs_ids else set()
    usable_students = [s for s in stu_ids if s not in childless_students] or stu_ids
    usable_courses = [c for c in crs_ids if c not in childless_courses] or crs_ids

    pairs = []
    seen = set()
    attempts = 0
    while len(pairs) < n_new and attempts < n_new * 50:
        attempts += 1
        c = rng.choice(usable_courses) if usable_courses else None
        s = rng.choice(usable_students) if usable_students else None
        if (c, s) in seen or (c, s) in existing_pairs:
            continue
        seen.add((c, s))
        pairs.append((c, s))
    while len(pairs) < n_new:
        c = rng.choice(usable_courses) if usable_courses else None
        s = rng.choice(usable_students) if usable_students else None
        pairs.append((c, s))

    cols['course_id'] = [p[0] for p in pairs]
    cols['student_id'] = [p[1] for p in pairs]

    grade_vals = []
    null_share = _null_share(rng)
    n_null = max(1, int(len(pairs) * null_share)) if pairs else 0
    grades = ['A', 'B', 'C', 'D']
    for j in range(len(pairs)):
        if j < n_null:
            grade_vals.append(None)
        else:
            grade_vals.append(rng.choice(grades))
    cols['grade'] = grade_vals

    sat_vals = [rng.choice([1, 2, 3, 4, 5]) for _ in range(len(pairs))]
    by_course = {}
    for idx, c in enumerate(cols['course_id']):
        by_course.setdefault(c, []).append(idx)
    for c, idxs in by_course.items():
        if len(idxs) >= 2:
            sat_vals[idxs[0]] = 1
            sat_vals[idxs[1]] = 5
    cols['sat'] = sat_vals

    if len(pairs) >= 2 and cols['course_id']:
        target = cols['course_id'][0]
        count = 0
        for idx in range(len(cols['course_id'])):
            if cols['course_id'][idx] == target:
                count += 1
                if count > 2:
                    cols['course_id'][idx] = usable_courses[-1] if usable_courses else target
    return cols


def _gen_ra(schema, pool, rng, n_new: int, students: dict, profs: dict) -> dict:
    tm = schema.tables['RA']
    cols = {c.name: [] for c in tm.columns}
    stu_ids = _existing_fk_values(schema, 'RA', 'student_id') + list(students.get('student_id', []))
    prof_ids = _existing_fk_values(schema, 'RA', 'prof_id') + list(profs.get('prof_id', []))
    stu_ids = [v for v in stu_ids if v is not None]
    prof_ids = [v for v in prof_ids if v is not None]
    existing_pairs = set()
    n_ex = len(schema.original_values.get(('RA', 'student_id'), []))
    for i in range(n_ex):
        existing_pairs.add((schema.original_values[('RA', 'student_id')][i],
                            schema.original_values[('RA', 'prof_id')][i]))
    childless_students = set(stu_ids[:max(1, len(stu_ids) // 8)]) if stu_ids else set()
    childless_profs = set(prof_ids[:max(1, len(prof_ids) // 8)]) if prof_ids else set()
    usable_students = [s for s in stu_ids if s not in childless_students] or stu_ids
    usable_profs = [p for p in prof_ids if p not in childless_profs] or prof_ids

    pairs = []
    seen = set()
    attempts = 0
    while len(pairs) < n_new and attempts < n_new * 50:
        attempts += 1
        s = rng.choice(usable_students) if usable_students else None
        p = rng.choice(usable_profs) if usable_profs else None
        if (s, p) in seen or (s, p) in existing_pairs:
            continue
        seen.add((s, p))
        pairs.append((s, p))
    while len(pairs) < n_new:
        s = rng.choice(usable_students) if usable_students else None
        p = rng.choice(usable_profs) if usable_profs else None
        pairs.append((s, p))

    cols['student_id'] = [p[0] for p in pairs]
    cols['prof_id'] = [p[1] for p in pairs]

    if len(pairs) >= 6 and usable_profs:
        p1 = usable_profs[0]
        p2 = usable_profs[1] if len(usable_profs) > 1 else p1
        p3 = usable_profs[2] if len(usable_profs) > 2 else p2
        s1 = usable_students[0] if usable_students else None
        s2 = usable_students[1] if len(usable_students) > 1 else s1
        s3 = usable_students[2] if len(usable_students) > 2 else s2
        cols['prof_id'][0] = p1
        cols['student_id'][0] = s1
        cols['prof_id'][1] = p2
        cols['student_id'][1] = s1
        cols['prof_id'][2] = p2
        cols['student_id'][2] = s2
        cols['prof_id'][3] = p3
        cols['student_id'][3] = s1
        cols['prof_id'][4] = p3
        cols['student_id'][4] = s2
        cols['prof_id'][5] = p3
        cols['student_id'][5] = s3

    cap_pool = [2, 3, 4, 1, 5]
    cap_vals = [rng.choice(cap_pool) for _ in range(len(pairs))]
    by_stu = {}
    for idx, s in enumerate(cols['student_id']):
        by_stu.setdefault(s, []).append(idx)
    for s, idxs in by_stu.items():
        if len(idxs) >= 2:
            cap_vals[idxs[0]] = 2
            cap_vals[idxs[1]] = 4
    cols['capability'] = cap_vals

    sal_pool = ['med', 'high', 'low', 'free']
    cols['salary'] = [rng.choice(sal_pool) for _ in range(len(pairs))]

    if len(pairs) >= 3 and cols['prof_id']:
        target = cols['prof_id'][0]
        count = 0
        for idx in range(len(cols['prof_id'])):
            if cols['prof_id'][idx] == target:
                count += 1
                if count > 3:
                    cols['prof_id'][idx] = usable_profs[-1] if usable_profs else target
    return cols


def _table_size(schema, table: str, rng, scale: float = 1.0) -> int:
    """Appended row count: honor table_sizes_per_instance (scaled)."""
    base = TABLE_SIZES.get(table, schema.original_sizes.get(table, 0))
    return max(0, int(round(base * scale)))


def generate_instance_rows(schema, pool: dict, rng, scale: float = 1.0) -> dict:
    """Generate appended rows for all tables in topological order."""
    order = [t for lvl in schema.table_order for t in lvl]
    for t in schema.tables:
        if t not in order:
            order.append(t)
    rows: dict = {}
    for t in order:
        n_new = _table_size(schema, t, rng, scale)
        if t == 'student':
            rows[t] = _gen_student(schema, pool, rng, n_new)
        elif t == 'prof':
            rows[t] = _gen_prof(schema, pool, rng, n_new)
        elif t == 'course':
            rows[t] = _gen_course(schema, pool, rng, n_new)
        elif t == 'registration':
            rows[t] = _gen_registration(schema, pool, rng, n_new, rows.get('student', {}), rows.get('course', {}))
        elif t == 'RA':
            rows[t] = _gen_ra(schema, pool, rng, n_new, rows.get('student', {}), rows.get('prof', {}))
        else:
            tm = schema.tables[t]
            cols = {}
            for c in tm.columns:
                key = (t, c.name)
                if key in schema.fks:
                    pt, pc = schema.fks[key]
                    pv = _existing_fk_values(schema, pt, pc) + list(rows.get(pt, {}).get(pc, []))
                    pv = [v for v in pv if v is not None]
                    cols[c.name] = [rng.choice(pv) if pv else None for _ in range(n_new)]
                else:
                    sampler = _init_sampler(c, pool.get(key, []),
                                            schema.original_values.get(key, []), 0.2, rng, 1)
                    cols[c.name] = [sampler.sample() for _ in range(n_new)]
            rows[t] = cols
    return rows
