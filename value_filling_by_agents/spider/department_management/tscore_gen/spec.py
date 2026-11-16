"""Specification constants (value domains, boundaries, table sizes) implemented by construction."""

TABLE_SIZES = {'department': 15, 'head': 10, 'management': 5}

OBSERVED = {
    'department': {
        'Department_ID': [1, 2, 3, 4, 5, 6, 7, 8],
        'Name': ['State', 'Treasury', 'Defense', 'Justice', 'Interior', 'Agriculture', 'Commerce', 'Labor'],
        'Creation': ['1789', '1947', '1870', '1849', '1889', '1903', '1913', '1953'],
        'Ranking': [1, 2, 3, 4, 5, 6, 7, 8],
        'Budget_in_Billions': [9.96, 11.1, 439.3, 23.4, 10.7, 77.6, 6.2, 59.7],
        'Num_Employees': [30266.0, 115897.0, 3000000.0, 112557.0, 71436.0, 109832.0, 36000.0, 17347.0],
    },
    'head': {
        'head_ID': [1, 2, 3, 4, 5, 6, 7, 8],
        'name': ['Tiger Woods', 'Sergio Garcia', 'K. J. Choi', 'Dudley Hart', 'Jeff Maggert',
                 'Billy Mayfair', 'Stewart Cink', 'Nick Faldo'],
        'born_state': ['Alabama', 'California', 'Delaware', 'Florida', 'Connecticut'],
        'age': [67.0, 68.0, 69.0, 52.0, 53.0, 50.0, 56.0, 43.0],
    },
    'management': {
        'department_ID': [2, 7, 11, 15],
        'head_ID': [5, 6, 3, 10, 4],
        'temporary_acting': ['Yes', 'No'],
    },
}

BOUNDARY = {
    ('department', 'Department_ID'): [9, 10, 11, 14, 15, 16],
    ('department', 'Name'): ['Homeland Security', 'homeland security', 'Treasury', 'treasury'],
    ('department', 'Ranking'): [9, 10, 11, 14, 15, 16],
    ('department', 'Budget_in_Billions'): [-0.01, 0.0, 0.01],
    ('department', 'Num_Employees'): [55.0, 56.0, 57.0],
    ('head', 'born_state'): ['Alabama', 'alabama'],
    ('head', 'age'): [55.0, 56.0, 57.0],
    ('management', 'temporary_acting'): ['Yes', 'yes'],
}

def _rule_department_id(v):
    return v is None or v > 0


def _rule_ranking(v):
    return v is None or v > 0


def _rule_budget(v):
    return v is None or v >= 0


def _rule_num_employees(v):
    return v is None or v >= 0


def _rule_head_id(v):
    return v is None or v > 0


def _rule_age(v):
    return v is None or (0 < v < 120)


def _rule_temporary_acting(v):
    return v is None or v in ('Yes', 'No')


RULES = {
    ('department', 'Department_ID'): _rule_department_id,
    ('department', 'Ranking'): _rule_ranking,
    ('department', 'Budget_in_Billions'): _rule_budget,
    ('department', 'Num_Employees'): _rule_num_employees,
    ('head', 'head_ID'): _rule_head_id,
    ('head', 'age'): _rule_age,
    ('management', 'temporary_acting'): _rule_temporary_acting,
}

NULL_FLOOR_SHARE = 0.10

NAME_DUP_SHARE = 0.30
BORN_STATE_DUP_SHARE = 0.35
HEAD_NAME_DUP_SHARE = 0.30
