"""The generation specification, encoded as data (no SQL is ever evaluated)."""

TABLE_SIZES = {
    'department': 20, 'classroom': 30, 'course': 200, 'instructor': 50,
    'student': 2000, 'section': 100, 'teaches': 100, 'takes': 30000,
    'advisor': 2000, 'prereq': 100, 'time_slot': 20,
}
EXTRA_ROWS = {
    'department': (0, 6), 'classroom': (0, 8), 'course': (0, 20), 'instructor': (0, 10),
    'student': (0, 40), 'section': (0, 20), 'teaches': (0, 20), 'takes': (0, 60),
    'advisor': (0, 40), 'prereq': (0, 20), 'time_slot': (0, 8),
}

SEMESTERS = ['Fall', 'Winter', 'Spring', 'Summer']
GRADES = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D', 'F']
DAYS = ['M', 'T', 'W', 'R', 'F']
TIME_SLOT_IDS = list('ABCDEFGHIJKLMNOP')
CREDITS = [3, 4]

RANGES = {
    ('department', 'budget'): (1.0, 1000000.0, 2),
    ('instructor', 'salary'): (29001.0, 150000.0, 2),
    ('student', 'tot_cred'): (0, 160, 0),
    ('classroom', 'capacity'): (10, 120, 0),
    ('section', 'year'): (2001, 2010, 0),
    ('time_slot', 'start_hr'): (8, 16, 0),
    ('time_slot', 'start_min'): (0, 50, 0),
    ('time_slot', 'end_hr'): (8, 16, 0),
    ('time_slot', 'end_min'): (0, 50, 0),
}
MINUTES = [0, 30, 45, 50]

CHECK_BOUNDARIES = {
    ('section', 'year'): [1702, 1703, 2008, 2009, 2010, 2011, 2098, 2099],
    ('department', 'budget'): [0.01, 1.0],
    ('instructor', 'salary'): [29000.01, 29001.0],
    ('student', 'tot_cred'): [0, 1],
    ('course', 'credits'): [1, 2],
}

NULLABLE = [
    ('course', 'dept_name'), ('instructor', 'dept_name'), ('student', 'dept_name'),
    ('section', 'building'), ('section', 'room_number'), ('section', 'time_slot_id'),
    ('advisor', 'i_ID'), ('takes', 'grade'), ('time_slot', 'end_hr'), ('time_slot', 'end_min'),
]
NULL_SHARE = (0.02, 0.05)

COMPOSITE_NULL_FKS = [
    ('section', ('building', 'room_number')),
]

BOUNDARY_VALUES = {
    ('department', 'dept_name'): ['Physics', 'physics', 'Comp. Sci.', 'comp. sci.',
                                  'Statistics', 'statistics'],
    ('instructor', 'dept_name'): ['Comp. Sci.', 'comp. sci.', 'Statistics', 'statistics'],
    ('course', 'dept_name'): ['Physics', 'physics'],
    ('course', 'title'): ['Differential Geometry', 'differential geometry',
                          'International Finance', 'international finance'],
    ('section', 'semester'): ['Fall', 'Spring'],
    ('section', 'year'): [2008, 2009, 2010, 2011, 2099],
}
BOUNDARY_P = 0.15

LIKE_VARIANTS = {
    ('instructor', 'name'): ['Soisalon', 'Soisaloo', 'Soisalon x', 'soisalon'],
}
LIKE_P = 0.10

GROUP_SIZE_COLUMNS = [('department', 'dept_name'), ('prereq', 'course_id')]

def check_formulas(table: str, row: dict) -> bool:
    """Return False only if a formula is definitely violated (NULL operands pass)."""
    if table == 'department':
        b = row.get('budget')
        if b is not None and not (b > 0):
            return False
    if table == 'course':
        c = row.get('credits')
        if c is not None and not (c > 0):
            return False
    if table == 'instructor':
        s = row.get('salary')
        if s is not None and not (s > 29000):
            return False
    if table == 'section':
        sem = row.get('semester')
        if sem is not None and sem not in SEMESTERS:
            return False
        y = row.get('year')
        if y is not None and not (1701 < y < 2100):
            return False
    if table == 'student':
        t = row.get('tot_cred')
        if t is not None and not (t >= 0):
            return False
    if table == 'time_slot':
        sh, sm = row.get('start_hr'), row.get('start_min')
        eh, em = row.get('end_hr'), row.get('end_min')
        if sh is not None and not (0 <= sh < 24):
            return False
        if sm is not None and not (0 <= sm < 60):
            return False
        if eh is not None and not (0 <= eh < 24):
            return False
        if em is not None and not (0 <= em < 60):
            return False
        if None not in (sh, sm, eh, em):
            if not (eh > sh or (eh == sh and em > sm)):
                return False
    return True
