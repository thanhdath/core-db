"""Specification constants (generation spec) implemented by construction in the samplers."""

TABLE_SIZES = {
    'Campuses': 10,
    'csu_fees': 10,
    'degrees': 40,
    'discipline_enrollments': 40,
    'enrollments': 40,
    'faculty': 10,
}

YEAR_BOUNDARY = {
    'Campuses.Year': [1934, 1935, 1936, 1938, 1939, 1940],
    'csu_fees.Year': [1995, 1996, 1997],
    'faculty.Year': [2001, 2002, 2003],
    'discipline_enrollments.Year': [2003, 2004, 2005],
}
YEAR_RANGE = (1900, 2010)

NUM_BOUNDARY = {
    'enrollments.FTE_AY': [199, 200, 201, 399, 400, 401],
    'enrollments.TotalEnrollment_AY': [199, 200, 201, 399, 400, 401],
    'Campuses.County': [199, 200, 201],
}

CAMPUS_LITERALS = ['San Francisco State University', 'Long Beach State University']
CAMPUS_CASE_VARIANTS = ['san francisco state university', 'long beach state university']
LOCATION_LIKE = ['Chico%']
LOCATION_VARIANTS = ['Chicp', 'Chico x', 'chico']
COUNTY_LITERALS = ['Orange', 'orange']

DUP_SHARE = (0.20, 0.50)

GROUP_SIZE_PLAN = [1, 1, 2, 2, 3, 3, 4]

NULL_TARGETS = {
    'csu_fees.Year', 'csu_fees.CampusFee', 'degrees.Degrees',
    'discipline_enrollments.Year', 'discipline_enrollments.Undergraduate',
    'discipline_enrollments.Graduate', 'enrollments.TotalEnrollment_AY',
    'enrollments.FTE_AY', 'faculty.Campus', 'faculty.Year', 'faculty.Faculty',
}

def _nonneg(v):
    return v is None or v >= 0


def _fte_le_total(row):
    f, t = row.get('FTE_AY'), row.get('TotalEnrollment_AY')
    return f is None or t is None or f <= t


FORMULAS = {
    ('Campuses', 'Id'): lambda r: r.get('Id') is None or r['Id'] > 0,
    ('csu_fees', 'CampusFee'): lambda r: _nonneg(r.get('CampusFee')),
    ('degrees', 'Degrees'): lambda r: _nonneg(r.get('Degrees')),
    ('discipline_enrollments', 'Undergraduate'): lambda r: _nonneg(r.get('Undergraduate')),
    ('discipline_enrollments', 'Graduate'): lambda r: _nonneg(r.get('Graduate')),
    ('enrollments', 'TotalEnrollment_AY'): lambda r: _nonneg(r.get('TotalEnrollment_AY')),
    ('enrollments', 'FTE_AY'): lambda r: _nonneg(r.get('FTE_AY')),
    ('faculty', 'Faculty'): lambda r: _nonneg(r.get('Faculty')),
}
ROW_FORMULAS = {
    'enrollments': [_fte_le_total],
}
