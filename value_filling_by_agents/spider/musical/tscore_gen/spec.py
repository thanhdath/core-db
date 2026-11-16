"""Specification constants (generation specification, per-column exceptions)."""

ENUMS = {
    ('musical', 'Award'): ['Tony Award', 'Drama Desk Award'],
    ('musical', 'Result'): ['Nominated', 'Won'],
}

RANGES = {
    ('musical', 'Musical_ID'): (1, 7),
    ('musical', 'Year'): (1900, 2100),
    ('actor', 'Actor_ID'): (1, 9),
    ('actor', 'age'): (1, 60),
}

BOUNDARY_VALUES = {
    ('musical', 'Award'): ['Tony Award', 'tony award', 'Drama Desk Award', 'drama desk award',
                           'Cleavant Derricks', 'cleavant derricks', ' Aw', ' aw', ' Awa', ' awa',
                           'Tonyard', 'tonyard'],
    ('actor', 'age'): [-1, 0, 1],
}

NULL_SHARE = {
    ('actor', 'Musical_ID'): 0.20,
    ('musical', 'Nominee'): 0.20,
}

GROUP_SIZE_COLUMNS = [
    ('actor', 'Musical_ID'),
    ('musical', 'Musical_ID'),
    ('musical', 'Name'),
    ('musical', 'Nominee'),
    ('musical', 'Result'),
    ('musical', 'Year'),
]

DUP_SHARE = 0.35
DUP_COLUMNS = [
    ('actor', 'Musical_ID'),
    ('musical', 'Name'),
    ('musical', 'Nominee'),
    ('musical', 'Result'),
    ('actor', 'Name'),
    ('actor', 'Character'),
]

ORDER_TIES = [
    ('musical', 'Award', 'DESC'),
    ('musical', 'Name', 'ASC'),
    ('musical', 'Nominee', 'DESC'),
    ('musical', 'Result', 'ASC'),
    ('musical', 'Year', 'ASC'),
    ('musical', 'Year', 'DESC'),
    ('actor', 'age', 'DESC'),
]

AGG_BOUNDARY = [2, 3, 4]

LOGICAL_FKS = {
    ('actor', 'Musical_ID'): ('musical', 'Musical_ID'),
}

UNMATCHED_FK_NONNULL = [
    ('actor', 'Musical_ID'),
]

TABLE_SIZES = {'musical': 7, 'actor': 9}

NEAR_VARIANT_P = 0.10
