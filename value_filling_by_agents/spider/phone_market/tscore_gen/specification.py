"""Specification constants (tscore_gen/specification.json) implemented by construction."""

TABLE_SIZES = {'market': 6, 'phone': 5, 'phone_market': 6}

ENUMS = {
    ('phone', 'Carrier'): ['Sprint', 'TMobile', 'Verizon', 'ATT'],
}
ENUMS_INFERRED = {
    ('phone', 'Carrier'): ['Verizon', 'ATT'],
}

BOUNDARIES = {
    ('phone', 'Memory_in_G'): [-30, -29, -28, 31, 32, 33, 63, 64, 65],
    ('market', 'Num_of_shops'): [49, 50, 51],
}
MEMORY_SECONDARY = {
    ('phone', 'Memory_in_G'): [16, 32, 64, 128],
}
MEMORY_SECONDARY_SHARE = 0.30

AGGREGATE_BOUNDARY = {
    'column': ('phone_market', 'Num_of_stock'),
    'aggregate': 'SUM',
    'values': [1998, 1999, 2000, 2001],
    'scope': 'generated',
}

GROUP_SIZE_COLUMNS = [('phone', 'Memory_in_G'), ('phone', 'Name')]
GROUP_SIZE_PRIMARY_KEYS = [('phone', 'Phone_ID')]

UNMATCHED_PARENT_COLUMNS = [('phone', 'Phone_ID'), ('market', 'Market_ID')]

DUPLICATE_SHARE = {('phone', 'Name'): (0.20, 0.50)}

TIE_COLUMNS = [('phone', 'Name'), ('phone', 'Price'), ('market', 'District'), ('phone', 'Carrier')]

DIFFERENT_VALUE_COLUMNS = [('phone', 'Price')]

FORMULAS = {
    ('phone', 'Phone_ID'): ('>', 0),
    ('phone', 'Memory_in_G'): ('in', (-30, -29, -28, 31, 32, 33, 63, 64, 65, 16, 128)),
    ('phone', 'Carrier'): ('in', ('Sprint', 'TMobile', 'Verizon', 'ATT')),
    ('phone', 'Price'): ('>=', 0),
    ('market', 'Market_ID'): ('>', 0),
    ('market', 'Num_of_employees'): ('>=', 0),
    ('market', 'Num_of_shops'): ('>=', 0),
    ('market', 'Ranking'): ('>=', 1),
    ('phone_market', 'Num_of_stock'): ('>=', 0),
}

INFERRED_FORMULAS = {
    ('phone', 'Memory_in_G'): ('in', (16, 32, 64, 128)),
}

INT_PRIMARY_KEYS = {
    'phone': 'Phone_ID',
    'market': 'Market_ID',
}

DEPENDENCIES = [
    {'child': ('phone_market', 'Market_ID'), 'parent_table': 'market', 'parent_column': 'Market_ID'},
    {'child': ('phone_market', 'Phone_ID'), 'parent_table': 'phone', 'parent_column': 'Phone_ID',
     'render': 'text'},
]

INT_QUANTITY_RANGE = (0, 100000)
INT_MEASURE_RANGE = (1, 1000)
REAL_PRICE_RANGE = (0.0, 5000.0)
REAL_MEASURE_RANGE = (0.0, 1000.0)
NULL_SHARE = 0.05
FRESH_VALUE_SHARE = 0.20
