"""The generation specification, encoded as data (no SQL is ever evaluated)."""

COMPACT_SIZES = {'location': 8, 'position': 4, 'employee': 25}
GEN_SIZE_RANGE = (0, 230)
PARENT_LEVEL_MULT = 4
PARENT_LEVEL_CAP = 2500

NULL_SHARE = {
    ('employee', 'gender'): 0.04,
    ('employee', 'performance'): 0.08,
    ('employee', 'hiredate'): 0.00,
    ('employee', 'lastname'): 0.00,
    ('employee', 'firstname'): 0.00,
    ('employee', 'salary'): 0.00,
    ('employee', 'positionID'): 0.00,
    ('employee', 'locationID'): 0.00,
    ('location', 'locationcity'): 0.00,
    ('location', 'address'): 0.00,
    ('location', 'state'): 0.00,
    ('location', 'zipcode'): 0.00,
    ('location', 'officephone'): 0.00,
    ('position', 'positiontitle'): 0.00,
    ('position', 'educationrequired'): 0.00,
    ('position', 'minsalary'): 0.00,
    ('position', 'maxsalary'): 0.00,
}
FORCE_NULL = {('employee', 'hiredate'), ('employee', 'performance'), ('employee', 'gender')}

ENUMS = {
    ('position', 'positiontitle'): ['Account Representative', 'Manager', 'Trainee', 'Regional Manager'],
    ('position', 'educationrequired'): ['4 year degree', '2 year degree', '6 year degree'],
    ('employee', 'gender'): ['F', 'M'],
    ('employee', 'performance'): ['Average', 'Good', 'Poor'],
}

BOUNDARY_VALUES = {
    ('position', 'positiontitle'): ['Account Representative', 'account representative',
                                    'Trainee', 'trainee', 'Manager', 'manager',
                                    'Regional Manager', 'regional manager'],
    ('location', 'locationcity'): ['New York City', 'new york city', 'Boston', 'boston'],
    ('location', 'state'): ['CA', 'ca', 'CO', 'co', 'UT', 'ut', 'NY', 'ny'],
    ('employee', 'gender'): ['M', 'm'],
    ('employee', 'performance'): ['', 'x'],
}
LIKE_VARIANTS = {
    ('position', 'positiontitle'): ['Manages', 'Manager x', 'manager'],
    ('location', 'address'): ['450 Peachtree Rd x', 'x450 Peachtree Rd'],
}
SALARY_BOUNDARY = [19999, 20000, 20001, 69999, 70000, 70001]

TIE_AGG_COUNT_TITLE = 'count_title'
TIE_AGG_COUNT_STATE = 'count_state'
TIE_AGG_COUNT_ADDRESS = 'count_address'
TIE_SALARY_CENTS = 'salary_cents'
TIE_EDU_LENGTH = 'edu_length'
TIE_ANY = 'any'

TIE_TARGETS = {
    ('position', 'positiontitle'): TIE_AGG_COUNT_TITLE,
    ('location', 'state'): TIE_AGG_COUNT_STATE,
    ('location', 'address'): TIE_AGG_COUNT_ADDRESS,
    ('employee', 'salary'): TIE_SALARY_CENTS,
    ('position', 'educationrequired'): TIE_EDU_LENGTH,
    ('employee', 'firstname'): TIE_ANY,
    ('employee', 'lastname'): TIE_ANY,
}

DUP_SHARE = {
    ('position', 'positiontitle'): 0.30,
    ('location', 'locationcity'): 0.30,
    ('location', 'state'): 0.30,
}

GROUP_SIZE_TARGETS = {
    ('location', 'address'): 'text',
    ('position', 'positionID'): 'int_pk',
    ('location', 'state'): 'int_text',
    ('employee', 'locationID'): 'int_fk',
    ('location', 'zipcode'): 'int_typed',
}
TEXT_GROUP_COLUMNS = {('location', 'address')}

UNMATCHED_JOIN = {
    ('position', 'positionID'): ('employee', 'positionID'),
    ('employee', 'positionID'): ('position', 'positionID'),
    ('location', 'locationID'): ('employee', 'locationID'),
}

def _salary_ok(v):
    if v is None:
        return True
    try:
        return float(str(v).replace('US$', '').replace(',', '')) >= 0
    except (TypeError, ValueError):
        return False


def _zip_ok(v):
    if v is None:
        return True
    if not isinstance(v, int):
        return False
    return 1000 <= v <= 99999


def _pk_ok(v):
    return v is None or (isinstance(v, int) and v > 0)


def _range_ok(lo, hi):
    def f(v):
        if v is None:
            return True
        try:
            n = float(str(v).replace('US$', '').replace(',', ''))
        except (TypeError, ValueError):
            return False
        return lo <= n <= hi
    return f


FORMULAS = {
    ('location', 'locationID'): _pk_ok,
    ('location', 'zipcode'): _zip_ok,
    ('position', 'positionID'): _pk_ok,
    ('employee', 'salary'): _range_ok(18000, 250000),
    ('position', 'minsalary'): _range_ok(0, 100000),
    ('position', 'maxsalary'): _range_ok(25000, 250000),
}

SALARY_RANGE = (18000, 250000)
MINSALARY_RANGE = (18000, 100000)
MAXSALARY_RANGE = (25000, 250000)

DATE_FORMAT = '%m/%d/%y'
DATE_RANGE = ((1970, 1, 1), (2025, 12, 31))
