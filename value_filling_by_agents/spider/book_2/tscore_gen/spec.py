"""Specification constants implemented by construction (tscore_gen/specification.json)."""
TABLE_SIZES = {'book': 8, 'publication': 10}

BOUNDARY_VALUES = {
    ('publication', 'Price'): [4999999.0, 5000000.0, 5000001.0, 5000002.0],
}

TEXT_LITERALS = {
    ('publication', 'Publisher'): ['Wiley', 'wiley', 'Person', 'person', 'n', 'N'],
}

DUPLICATE_SHARE_COLUMNS = {
    ('publication', 'Publisher'): (0.20, 0.50),
    ('book', 'Writer'): (0.20, 0.50),
    ('book', 'Title'): (0.20, 0.50),
}

AGGREGATE_BOUNDARY = {
    ('publication', 'Publisher'): {'counts': [0, 1, 2], 'absent_value': 'Pearson'},
}

GROUP_SIZE_TARGETS = {
    ('publication', 'Publication_Date'): {'sizes': [1, 2, 3], 'tie_at_rank': 1, 'direction': 'DESC'},
}

DATE_TEMPLATE = '%B %Y'

NON_NEGATIVE = {
    ('publication', 'Price'): True,
    ('publication', 'Publication_ID'): True,
    ('book', 'Book_ID'): True,
    ('book', 'Issues'): True,
}
POSITIVE = {
    ('publication', 'Publication_ID'): True,
    ('book', 'Book_ID'): True,
}

NULL_AT_LEAST_ONE = True

PRICE_TIE_MIN = 2
PRICE_TIE_MAX = 2

PRICE_DIFF_GROUP_MIN_ROWS = 2
