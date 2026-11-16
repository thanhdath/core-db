"""The generation specification, encoded as data (no SQL is ever evaluated)."""
import re

YEAR_MIN, YEAR_MAX = 2006, 2011
YEAR_LITERALS = [2006, 2007, 2008, 2009, 2010, 2011]

AUDIENCE_MIN = 1
AUDIENCE_OBSERVED = [152, 155, 160, 161]

ARTWORK_TYPES = ['Program Music/Variety Show', 'Presenter Music/Variety Show',
                 'Program Talent Show', 'Presenter Talent Show']
ARTWORK_TYPE_NEAR = ['program talent show', 'Program Talent Show ']

RESULT_VALUES = ['Nominated', 'Won']
RESULT_NEAR = ['nominated', 'Nominated ']

LOCATION_VALUES = ['United States']

TABLE_SIZES = {'festival_detail': 6, 'artwork': 9, 'nomination': 6}

GROUP_PLANS = {
    ('festival_detail', 'Festival_Name'): [1, 2, 3],
    ('nomination', 'Festival_ID'): [1, 2, 3],
    ('artwork', 'Type'): [1, 2, 3],
}

DUPLICATE_SHARE = 0.35

TIE_COLUMNS = [('festival_detail', 'Num_of_Audience'),
               ('festival_detail', 'Chair_Name'),
               ('festival_detail', 'Location'),
               ('festival_detail', 'Year'),
               ('festival_detail', 'Festival_ID')]

DIFFERENT_VALUE_COLUMNS = [('festival_detail', 'Num_of_Audience')]

COMPARISON_LITERALS = {
    ('festival_detail', 'Year'): YEAR_LITERALS,
    ('artwork', 'Type'): ARTWORK_TYPES + ARTWORK_TYPE_NEAR,
    ('nomination', 'Result'): RESULT_VALUES + RESULT_NEAR,
}

NULL_TARGETS = [('nomination', 'Festival_ID'), ('nomination', 'Result')]

DEPENDENCIES = [
    {'child_column': 'nomination.Artwork_ID', 'parent_table': 'artwork',
     'parent_column': 'Artwork_ID', 'copied_columns': []},
    {'child_column': 'nomination.Festival_ID', 'parent_table': 'festival_detail',
     'parent_column': 'Festival_ID', 'copied_columns': []},
]

UNMATCHED_PARENT = {'artwork': 'Artwork_ID', 'festival_detail': 'Festival_ID'}


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def type_pool() -> list:
    """Explicit enum pool for artwork.Type (canonical values first)."""
    return list(ARTWORK_TYPES)


def result_pool() -> list:
    """Explicit enum pool for nomination.Result."""
    return list(RESULT_VALUES)


def year_pool() -> list:
    """Year domain with boundary literals and one step on each side."""
    return list(range(YEAR_MIN - 1, YEAR_MAX + 2))


def audience_pool() -> list:
    """Positive audience values around the observed range (ties at the top)."""
    return [AUDIENCE_OBSERVED[0], AUDIENCE_OBSERVED[1], AUDIENCE_OBSERVED[2],
            AUDIENCE_OBSERVED[3], AUDIENCE_OBSERVED[3], AUDIENCE_OBSERVED[3] + 1]


def is_enum_column(table: str, column: str) -> bool:
    return (table, column) in (('artwork', 'Type'), ('nomination', 'Result'))


def enum_values(table: str, column: str) -> list:
    if (table, column) == ('artwork', 'Type'):
        return type_pool()
    if (table, column) == ('nomination', 'Result'):
        return result_pool()
    return []


def near_variants(value: str) -> list:
    """Case / whitespace near-variants of an equality literal."""
    out = []
    low = str(value).lower()
    if low != value:
        out.append(low)
    if str(value).strip() != value:
        out.append(str(value).strip())
    out.append(str(value) + ' ')
    return out
