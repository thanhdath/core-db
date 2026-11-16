"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from . import spec
from .values import _init_sampler

SPEC_SIZES = {
    'Course_Authors_and_Tutors': 15,
    'Subjects': 3,
    'Students': 15,
    'Courses': 15,
    'Student_Course_Enrolment': 20,
    'Student_Tests_Taken': 15,
}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _size_for(table: str, rng) -> int:
    base = SPEC_SIZES.get(table, 8)
    return max(0, int(round(base * rng.uniform(0.75, 1.25))))


def _fresh_int_keys(rng, start: int, n: int) -> list:
    """Sequential fresh integer PKs (never collide with compact rows)."""
    return list(range(start, start + n))


def _compact_column(schema, table, column):
    return schema.original_values.get((table, column), [])


def _build_generic_sampler(schema, table, column_name, pool, rng, p):
    import re
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == column_name)
    ov = list(_compact_column(schema, table, column_name))
    return _init_sampler(cm, pool.get((table, cm.name), []), ov, p, rng, len(tm.primary_key))


def _sample_column(schema, table, column_name, pool, rng, p, n):
    s = _build_generic_sampler(schema, table, column_name, pool, rng, p)
    return [s.sample() for _ in range(n)]


def _nullable_targets(schema):
    """Tables/columns where the NULL rule applies (targets listed in the spec plus nullable columns)."""
    out = set(spec.SPEC_NULL_TARGETS)
    return out


def _compact_null_share(schema, table, column):
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.1
    n_null = sum(1 for v in vals if v is None)
    return n_null / float(len(vals))


def _apply_null_rule(schema, table, column, values, rng):
    """At least one NULL and NULL share following the compact DB (10 % when unknown)."""
    if not values:
        return values
    share = _compact_null_share(schema, table, column)
    if share <= 0.0:
        share = 0.1
    n = len(values)
    k = max(1, int(round(n * share)))
    idx = list(range(n))
    rng.shuffle(idx)
    for j in idx[:k]:
        values[j] = None
    return values


def _pk_values(schema, table, rng, n):
    tm = schema.tables[table]
    if len(tm.primary_key) == 1:
        col = tm.primary_key[0]
        existing = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
        start = (max(existing) + 1) if existing else 1
        return _fresh_int_keys(rng, start, n)
    return None


def _build_subjects(schema, pool, rng):
    t = 'Subjects'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    keys = _pk_values(schema, t, rng, n)
    names = spec.name_pool(schema, t, 'subject_name')
    if names:
        names = list(names)
        sizes = spec.plan_group_sizes(rng, n)
        vals = spec.materialize_group_plan(rng, names, sizes)
        vals = spec.inject_boundary_literals(rng, vals, ['Computer Science'])
    else:
        vals = _sample_column(schema, t, 'subject_name', pool, rng, 0.2, n)
    return {tm.primary_key[0]: keys, 'subject_name': vals}


def _build_authors(schema, pool, rng):
    t = 'Course_Authors_and_Tutors'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    pk = tm.primary_key[0]
    keys = _pk_values(schema, t, rng, n)
    out = {pk: keys}
    cols = [c.name for c in tm.columns if c.name != pk]
    for c in cols:
        enum = spec.enum_values(schema, t, c)
        if enum is not None:
            out[c] = [rng.choice(enum) for _ in range(n)]
        else:
            p = 0.0 if c == 'address_line_1' else 0.2
            out[c] = _sample_column(schema, t, c, pool, rng, p, n)
    if 'address_line_1' in out:
        out['address_line_1'] = spec.shape_distinct_column(rng, out['address_line_1'])
    return out, tm


def _build_students(schema, pool, rng):
    t = 'Students'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    pk = tm.primary_key[0]
    keys = _pk_values(schema, t, rng, n)
    out = {pk: keys}
    for c in [cm.name for cm in tm.columns if cm.name != pk]:
        if c in ('date_of_registration', 'date_of_latest_logon'):
            continue
        if c == 'personal_name':
            pool_names = spec.name_pool(schema, t, c)
            vals = _sample_column(schema, t, c, pool, rng, 0.2, n)
            if pool_names:
                sizes = spec.plan_group_sizes(rng, n)
                vals = spec.materialize_group_plan(rng, list(pool_names) + vals, sizes)
            vals = spec.inject_boundary_literals(rng, vals, ['Karson'])
            vals = spec.shape_distinct_column(rng, vals)
            out[c] = vals
        elif c == 'login_name':
            vals = _sample_column(schema, t, c, pool, rng, 0.1, n)
            sizes = spec.plan_group_sizes(rng, n)
            out[c] = spec.materialize_group_plan(rng, vals, sizes)
        elif c == 'middle_name':
            vals = _sample_column(schema, t, c, pool, rng, 0.1, n)
            sizes = spec.plan_group_sizes(rng, n)
            out[c] = spec.materialize_group_plan(rng, vals, sizes)
        elif c == 'family_name':
            out[c] = spec.shape_distinct_column(rng, _sample_column(schema, t, c, pool, rng, 0.2, n))
        else:
            out[c] = _sample_column(schema, t, c, pool, rng, 0.2, n)
    reg = _sample_column(schema, t, 'date_of_registration', pool, rng, 0.2, n)
    out['date_of_registration'] = reg
    out['date_of_latest_logon'] = spec.after_series(rng, reg, n, min_days=1, max_days=900)
    out['date_of_latest_logon'] = spec.shape_distinct_column(rng, out['date_of_latest_logon'], share=0.2)
    return out, tm


def _build_courses(schema, pool, rng, authors, subjects):
    t = 'Courses'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    pk = tm.primary_key[0]
    keys = _pk_values(schema, t, rng, n)
    out = {pk: keys}
    author_keys = authors[list(schema.tables['Course_Authors_and_Tutors'].primary_key)[0]]
    subject_keys = subjects[list(schema.tables['Subjects'].primary_key)[0]]
    a_sizes = spec.plan_group_sizes(rng, n)
    author_vals = []
    if author_keys:
        plan_vals = list(author_keys)
        rng.shuffle(plan_vals)
        author_vals = spec.materialize_group_plan(rng, plan_vals, a_sizes)
    else:
        author_vals = [None] * n
    out['author_id'] = author_vals
    s_sizes = spec.plan_group_sizes(rng, n)
    if subject_keys:
        svals = spec.materialize_group_plan(rng, list(subject_keys), s_sizes)
    else:
        svals = [None] * n
    out['subject_id'] = svals
    names = _sample_column(schema, t, 'course_name', pool, rng, 0.2, n)
    extra = spec.CROSS_COLUMN_LITERALS.get((t, 'course_name'))
    if extra:
        names = spec.inject_boundary_literals(rng, names, list(extra))
    nsizes = spec.plan_group_sizes(rng, n)
    names = spec.materialize_group_plan(rng, names, nsizes)
    names = spec.shape_distinct_column(rng, names)
    out['course_name'] = names
    desc = _sample_column(schema, t, 'course_description', pool, rng, 0.2, n)
    cross = spec.CROSS_COLUMN_LITERALS.get((t, 'course_description'))
    if cross:
        desc = spec.inject_boundary_literals(rng, desc, list(cross))
    dsizes = spec.plan_group_sizes(rng, n)
    desc = spec.materialize_group_plan(rng, desc, dsizes)
    out['course_description'] = desc
    return out, tm


def _build_enrolments(schema, pool, rng, students, courses):
    t = 'Student_Course_Enrolment'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    pk = tm.primary_key[0]
    keys = _pk_values(schema, t, rng, n)
    out = {pk: keys}
    student_keys = students[list(schema.tables['Students'].primary_key)[0]]
    course_keys = courses[list(schema.tables['Courses'].primary_key)[0]]
    if student_keys:
        sizes = spec.plan_group_sizes(rng, n)
        s_vals = spec.materialize_group_plan(rng, list(student_keys), sizes)
    else:
        s_vals = [None] * n
    out['student_id'] = s_vals
    if course_keys:
        c_vals = spec.materialize_group_plan(rng, list(course_keys),
                                             spec.plan_group_sizes(rng, n))
    else:
        c_vals = [None] * n
    out['course_id'] = c_vals
    enr = _sample_column(schema, t, 'date_of_enrolment', pool, rng, 0.2, n)
    enr = spec.positional_series(n, dt.datetime(2017, 8, 1, 0, 0, 0), step_seconds=1800)
    out['date_of_enrolment'] = enr
    out['date_of_completion'] = spec.after_series(rng, enr, n, min_days=1, max_days=180)
    return out, tm


def _build_tests(schema, pool, rng, enrolments):
    t = 'Student_Tests_Taken'
    n = _size_for(t, rng)
    tm = schema.tables[t]
    reg_keys = enrolments[list(schema.tables['Student_Course_Enrolment'].primary_key)[0]]
    if reg_keys:
        sizes = spec.plan_group_sizes(rng, n)
        reg_vals = spec.materialize_group_plan(rng, list(reg_keys), sizes)
    else:
        reg_vals = [None] * n
    out = {'registration_id': reg_vals}
    enum = spec.enum_values(schema, t, 'test_result')
    if enum is not None:
        vals = [rng.choice(enum) for _ in range(n)]
        out['test_result'] = vals
    else:
        out['test_result'] = _sample_column(schema, t, 'test_result', pool, rng, 0.2, n)
    out['date_test_taken'] = _sample_column(schema, t, 'date_test_taken', pool, rng, 0.2, n)
    if not out['date_test_taken']:
        base = dt.datetime(2018, 3, 24, 0, 0, 0)
        out['date_test_taken'] = [spec.format_dt(base + dt.timedelta(seconds=97 * i)) for i in range(n)]
    return out, tm


def choose_table_sizes(schema, rng) -> dict:
    """Spec-driven small sizes (also acts as the fuzz rand_lin fallback if a table is unknown)."""
    return {t: _size_for(t, rng) for t in schema.tables}


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build the generated (appended) rows for one instance."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    authors, _ = _build_authors(schema, literal_pool, rng)
    subjects = _build_subjects(schema, literal_pool, rng)
    students, _ = _build_students(schema, literal_pool, rng)
    courses, _ = _build_courses(schema, literal_pool, rng, authors, subjects)
    enrolments, _ = _build_enrolments(schema, literal_pool, rng, students, courses)
    tests, _ = _build_tests(schema, literal_pool, rng, enrolments)
    inst = {
        'Course_Authors_and_Tutors': authors,
        'Subjects': subjects,
        'Students': students,
        'Courses': courses,
        'Student_Course_Enrolment': enrolments,
        'Student_Tests_Taken': tests,
    }
    nullable_targets = spec.SPEC_NULL_TARGETS
    for t, cols in inst.items():
        tm = schema.tables[t]
        for cm in tm.columns:
            if not cm.name in cols:
                continue
            if cm.pk_pos > 0 or cm.notnull:
                continue
            vals = cols[cm.name]
            if not vals:
                continue
            if (t, cm.name) in nullable_targets or rng.random() < 0.5:
                cols[cm.name] = _apply_null_rule(schema, t, cm.name, list(vals), rng)
    return inst
