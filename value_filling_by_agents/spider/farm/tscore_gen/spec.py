"""Specification tables (generation specification, by construction)."""

ENUMS = {
    ('city', 'Status'): ['Town', 'Village'],
}

BOUNDARY = {
    ('city', 'Population'): [499, 500, 501, 1499, 1500, 1501],
    ('farm', 'Total_Horses'): [4998.9, 4999.0, 4999.1, 4999.9, 5000.0, 5000.1],
}

TIES = {
    ('city', 'Population'): {'ranks': [1, 10, 100], 'direction': 'DESC'},
    ('city', 'Census_Ranking'): {'ranks': [1], 'direction': 'ASC and DESC'},
    ('farm', 'Total_Horses'): {'ranks': [10], 'direction': 'ASC'},
}

DUPLICATES = {
    ('city', 'Official_Name'): (0.20, 0.50),
    ('city', 'Census_Ranking'): (0.20, 0.50),
    ('city', 'Status'): (0.20, 0.50),
    ('farm_competition', 'Theme'): (0.20, 0.50),
}

GROUP_SIZES = {
    ('city', 'Official_Name'): '1, 2 and >= 3',
    ('city', 'Status'): '1, 2 and >= 3',
    ('farm_competition', 'Host_city_ID'): '1, 2 and >= 3',
}

UNMATCHED = {
    ('city', 'City_ID'): {'parent_rows_without_children': True, 'child_rows_with_null_fk': True},
    ('farm_competition', 'Host_city_ID'): {'parent_rows_without_children': True, 'child_rows_with_null_fk': True},
    ('farm_competition', 'Competition_ID'): {'parent_rows_without_children': True, 'child_rows_with_null_fk': False},
    ('farm', 'Farm_ID'): {'parent_rows_without_children': True, 'child_rows_with_null_fk': False},
    ('competition_record', 'Farm_ID'): {'parent_rows_without_children': True, 'child_rows_with_null_fk': False},
}

AGGREGATE_BOUNDARY = {
    ('farm_competition', 'Host_city_ID'): {'aggregate': ['COUNT(*)', 'COUNT(farm_competition.host_city_id)'],
                                           'values': [0, 1, 2]},
    ('farm_competition', 'Competition_ID'): {'aggregate': ['COUNT(farm_competition.competition_id)',
                                                           'COUNT(DISTINCT farm_competition.competition_id)'],
                                             'values': [0, 1, 2]},
}

ROWS_DIFFERENT = {
    ('city', 'Population'): {'qualifying_rows': '>= 2 per group with different values'},
}

NULL_IN_COUNT = {
    ('farm', 'Farm_ID'): 'none (NOT NULL column)',
}

YEAR_DOMAIN = (1900, 2100)
YEAR_COLUMNS = {('farm', 'Year'), ('farm_competition', 'Year')}

def _status_enum(r):
    return r.get('Status') in ('Town', 'Village')


def _positive(col):
    def f(r):
        v = r.get(col)
        return v is None or v > 0
    return f


def _nonneg(col):
    def f(r):
        v = r.get(col)
        return v is None or v >= 0
    return f


def _working_le_total(r):
    w, t = r.get('Working_Horses'), r.get('Total_Horses')
    if w is None or t is None:
        return True
    return 0 <= w <= t


def _cattle_lower_bound(r):
    """Total_Cattle >= Oxen + Bulls + Cows (lower bound, not an identity)."""
    tc = r.get('Total_Cattle')
    parts = [r.get('Oxen'), r.get('Bulls'), r.get('Cows')]
    if tc is None or any(p is None for p in parts):
        return True
    return tc >= sum(parts)


def _year_range(r):
    y = r.get('Year')
    return y is None or 1900 <= y <= 2100


def _rank_positive(r):
    v = r.get('Rank')
    return v is None or v > 0


RULES = {
    ('city', 'Status'): _status_enum,
    ('city', 'Population'): _positive('Population'),
    ('city', 'Area_km_2'): _positive('Area_km_2'),
    ('farm', 'Total_Horses'): _positive('Total_Horses'),
    ('farm', 'Working_Horses'): _working_le_total,
    ('farm', 'Total_Cattle'): _cattle_lower_bound,
    ('farm', 'Oxen'): _nonneg('Oxen'),
    ('farm', 'Bulls'): _nonneg('Bulls'),
    ('farm', 'Cows'): _nonneg('Cows'),
    ('farm', 'Pigs'): _nonneg('Pigs'),
    ('farm', 'Sheep_and_Goats'): _nonneg('Sheep_and_Goats'),
    ('farm_competition', 'Year'): _year_range,
    ('competition_record', 'Rank'): _rank_positive,
}

TABLE_SIZES = {'city': 120, 'farm': 12, 'farm_competition': 6, 'competition_record': 12}

NULL_SHARE_MIN = 0.05
NULL_SHARE_MAX = 0.10
FK_NONNULL_MIN = 0.90

FRESH_SHARE = 0.30
