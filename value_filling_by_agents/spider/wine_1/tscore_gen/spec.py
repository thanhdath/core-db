"""Specification tables: value domains, enumerations, ranges, boundary literals, NULL targets."""

ENUMS = {
    ('grapes', 'Color'): ['Red', 'White', 'red'],
    ('appellations', 'isAVA'): ['Yes', 'No'],
    ('appellations', 'State'): ['California', 'california'],
    ('wine', 'State'): ['California', 'california'],
}

RANGES = {
    ('wine', 'Year'): (1900, 2100),
    ('wine', 'Price'): (0, 10000),
    ('wine', 'Score'): (50, 100),
    ('wine', 'Cases'): (0, 10000),
}

BOUNDARY = {
    ('wine', 'Year'): [1999, 2000, 2001, 2007, 2008, 2009, 2010, 2011],
    ('wine', 'Score'): [89, 90, 91],
}

BOUNDARY_TEXT = {
    ('wine', 'Appelation'): ['St. Helena', 'st. helena'],
    ('appellations', 'Appelation'): ['St. Helena', 'st. helena'],
    ('grapes', 'Grape'): ['Zinfandel', 'zinfandel'],
    ('wine', 'Grape'): ['Zinfandel', 'zinfandel'],
    ('appellations', 'Area'): ['Central Coast', 'central coast'],
    ('appellations', 'State'): ['California', 'california'],
    ('grapes', 'Color'): ['Red', 'red'],
}

NULL_TARGETS = [
    ('wine', 'Appelation'), ('wine', 'Grape'), ('wine', 'Winery'), ('wine', 'State'),
    ('wine', 'Name'), ('wine', 'Year'), ('wine', 'Price'), ('wine', 'Score'), ('wine', 'Cases'),
    ('wine', 'Drink'),
    ('appellations', 'County'), ('appellations', 'Area'), ('appellations', 'isAVA'),
    ('grapes', 'Color'),
]

FK_CHILD_NULL_MIN_ONE = [
    ('wine', 'Appelation'), ('wine', 'Grape'),
]

DUPLICATE_COLUMNS = [
    ('wine', 'Winery'), ('wine', 'Name'),
]

TIE_COLUMNS = [
    ('wine', 'Year'), ('appellations', 'County'), ('wine', 'Price'), ('wine', 'Name'),
    ('appellations', 'Appelation'), ('grapes', 'Grape'),
]

GROUP_SIZE_COLUMNS = [
    ('wine', 'Name'), ('appellations', 'Appelation'), ('grapes', 'Grape'),
]

AGGREGATE_COLUMNS = [
    ('wine', 'Winery'),
]

DIFFERENT_VALUE_COLUMNS = [
    ('wine', 'Year'), ('wine', 'Cases'), ('wine', 'Score'),
]

TABLE_SIZES = {'grapes': 20, 'appellations': 57, 'wine': 500}

NULL_SHARE = 0.0

UNIQUE_TEXT_COLUMNS = [
    ('grapes', 'Grape'), ('appellations', 'Appelation'),
]

FK_CHILD_BOUNDARY = {
    ('wine', 'Appelation'): ['St. Helena', 'st. helena'],
    ('wine', 'Grape'): ['Zinfandel', 'zinfandel'],
}
