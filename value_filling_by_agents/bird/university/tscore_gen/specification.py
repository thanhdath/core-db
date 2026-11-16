"""Specification constants coded by construction (derived from generation specification JSON)."""
import json
import os

YEAR_LO, YEAR_HI = 2005, 2016
SCORE_LO, SCORE_HI = 0, 100
PCT_LO, PCT_HI = 0, 100
NUM_STUDENTS_LO, NUM_STUDENTS_HI = 1, 100000
RATIO_LO, RATIO_HI = 1.0, 30.0
RATIO_PRECISION = 1

NULL_SHARE = {
    ('university_ranking_year', 'score'): 0.004,
    ('university_year', 'pct_female_students'): 0.088,
    ('university_year', 'pct_international_students'): 0.10,
}
DEFAULT_FK_NULL_SHARE = 0.05

BOUNDARY_VALUES = {
    ('university', 'id'): [39, 40, 41, 123, 124, 125],
    ('university_year', 'university_id'): [0, 1, 2, 39, 40, 41],
    ('university_ranking_year', 'university_id'): [78, 79, 80, 123, 124, 125],
    ('ranking_criteria', 'id'): [5, 6, 7, 16, 17, 18],
    ('ranking_criteria', 'ranking_system_id'): [2, 3, 4],
    ('ranking_system', 'id'): [2, 3, 4],
    ('university_year', 'num_students'): [399, 400, 401, 999, 1000, 1001],
    ('university_year', 'year'): [2010, 2011, 2012, 2013, 2014],
    ('university_year', 'pct_international_students'): [9, 10, 11, 12],
    ('university_ranking_year', 'ranking_criteria_id'): [5, 6, 7],
}

BOUNDARY_TEXT = {
    ('university', 'university_name'): ['Harvard University', 'Chosun University', 'University of Ottawa'],
    ('ranking_criteria', 'criteria_name'): ['Teaching', 'Quality of Education Rank', 'Influence Rank'],
    ('country', 'country_name'): ['United States of America', 'Australia', 'Turkey'],
}

TEXT_NAME_POOL_SIZE = 200

TABLE_SIZE_MIN, TABLE_SIZE_MAX = 0, 230
LEVEL_CAP = 2500


def load(path: str) -> dict:
    """Load tscore_gen/specification.json if present, else {} (defaults above are used)."""
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}
