"""Specification constants (generation specification, round 1)."""
TABLE_SIZES = {
    'Student': 34,
    'Restaurant': 8,
    'Restaurant_Type': 8,
    'Type_Of_Restaurant': 8,
    'Visits_Restaurant': 8,
}

AGE_MIN, AGE_MAX = 16, 30
SEX_VALUES = ('F', 'M', 'U')
RATING_MIN, RATING_MAX = 1, 5
SPENT_MIN = 0.0

SEMANTIC_COLUMNS = {
    ('Student', 'Sex'),
    ('Student', 'Age'),
    ('Restaurant', 'Rating'),
    ('Visits_Restaurant', 'Spent'),
}

NULL_SHARE = 0.08

NULL_TARGETS = {
    ('Student', 'Major'),
    ('Student', 'Advisor'),
    ('Student', 'LName'),
    ('Student', 'Fname'),
    ('Student', 'city_code'),
    ('Restaurant', 'ResName'),
    ('Restaurant', 'Address'),
    ('Restaurant', 'Rating'),
    ('Restaurant_Type', 'ResTypeName'),
    ('Restaurant_Type', 'ResTypeDescription'),
    ('Type_Of_Restaurant', 'ResID'),
    ('Type_Of_Restaurant', 'ResTypeID'),
    ('Visits_Restaurant', 'StuID'),
    ('Visits_Restaurant', 'ResID'),
    ('Visits_Restaurant', 'Time'),
    ('Visits_Restaurant', 'Spent'),
}
NULL_TARGETS -= SEMANTIC_COLUMNS

LNAME_BOUNDARY = 'Smith'
FNAME_BOUNDARY = 'Linda'
RESTYPE_BOUNDARY = 'Sandwich'
RESNAME_BOUNDARY = 'Subway'

DUP_SHARE = 0.35

GROUP_SIZES = (1, 2, 3)

TIE_RANK1 = 2

GROUP_SIZE_COLUMNS = {
    ('Restaurant', 'ResName'),
    ('Student', 'Sex'),
    ('Type_Of_Restaurant', 'ResTypeID'),
}

TIE_RANK1_COLUMNS = {
    ('Student', 'Major'),
    ('Student', 'Advisor'),
}

BOUNDARY_COLUMNS = {
    ('Student', 'LName'): LNAME_BOUNDARY,
    ('Student', 'Fname'): FNAME_BOUNDARY,
    ('Restaurant_Type', 'ResTypeName'): RESTYPE_BOUNDARY,
    ('Restaurant', 'ResName'): RESNAME_BOUNDARY,
}

DISTINCT_COLUMNS = {
    ('Student', 'LName'),
    ('Student', 'Fname'),
    ('Restaurant_Type', 'ResTypeName'),
    ('Student', 'city_code'),
    ('Restaurant', 'Address'),
}

UNMATCHED_JOIN_TARGETS = {
    ('Type_Of_Restaurant', 'ResID'): ('Restaurant', 'ResID'),
    ('Type_Of_Restaurant', 'ResTypeID'): ('Restaurant_Type', 'ResTypeID'),
    ('Visits_Restaurant', 'StuID'): ('Student', 'StuID'),
    ('Visits_Restaurant', 'ResID'): ('Restaurant', 'ResID'),
}
