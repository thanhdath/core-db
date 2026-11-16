"""The generation specification, encoded as data (implemented by construction in the samplers)."""

MAJOR_DOMAIN = [50, 100, 520, 540, 550, 600]
MAJOR_BOUNDARY = [-1, 0, 1, 599, 601]
MAJOR_GROUP_SIZES = [1, 2, 3, 4, 5]
MAJOR_AGG_VALUES = [2, 3, 4, 5]
MAJOR_TIE_RANK = 1

ADVISOR_BOUNDARY = [2191, 2192, 2193, 8740, 8741, 8742]
ADVISOR_NEAR = ['%2192', '%2193']
ADVISOR_BOUNDARY_SHARE = 0.15

CITY_BOUNDARY = ['NYC', 'nyc', 'PIT', 'pit', 'N', 'n', 'Y', 'y']
CITY_POOL = ['BAL', 'HKG', 'WAS', 'CHI', 'YYZ', 'PIT', 'HOU', 'PHL']
CITY_BOUNDARY_SHARE = 0.15

SEX_DOMAIN = ['F', 'M']
SEX_BOUNDARY = ['F', 'f']

AGE_MIN, AGE_MAX = 16, 26

CYCLE_DOMAIN = ['Spring', 'Fall']
CYCLE_BOUNDARY = ['Spring', 'spring', 'rin', 'RIN']
CYCLE_BOUNDARY_SHARE = 0.25

DATE_FORMAT = '%m/%d/%Y'
DATE_YEARS = (2010, 2016)

NULL_SHARE_MIN = 0.05
NULL_SHARE_MAX = 0.30
NULL_SHARE_TARGET = 0.15
NULL_COLUMNS = [
    ('Voting_record', 'StuID'),
    ('Voting_record', 'President_Vote'),
    ('Voting_record', 'Vice_President_Vote'),
    ('Voting_record', 'Secretary_Vote'),
    ('Voting_record', 'Treasurer_Vote'),
    ('Voting_record', 'Class_President_Vote'),
    ('Voting_record', 'Class_Senator_Vote'),
]

DUP_SHARE_MIN = 0.20
DUP_SHARE_MAX = 0.50
DUP_SHARE_TARGET = 0.30
DUP_COLUMNS = [
    ('Student', 'Major'),
    ('Student', 'Advisor'),
    ('Student', 'city_code'),
    ('Student', 'LName'),
    ('Student', 'Fname'),
    ('Voting_record', 'Registration_Date'),
]

UNMATCHED_CHILD_NULL_MIN = 1
UNMATCHED_PARENT_MIN = 1

STUDENT_ROWS = 34
VOTING_ROWS = 10
