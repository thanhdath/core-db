"""Specification constants (generation specification, per-column exceptions)."""

POPULATION_BOUNDARY = [19999, 20000, 20001]
POPULATION_RANGE = (1, 100000)
POPULATION_TIE_TOP = 2
CRIME_RATE_BOUNDARY = [99.0, 100.0, 101.0]
CRIME_RATE_RANGE = (0.0, 200.0)
CRIME_RATE_DUP_SHARE = 0.35
POLICE_OFFICERS_RANGE = (1, 1000)
POLICE_OFFICERS_TIE_TOP = 2
POLICE_OFFICERS_DISTINCT = 2
CASE_BURDEN_RANGE = (0, 1000)
LOCATION_ENUM = ['East', 'West', 'North']
LOCATION_BOUNDARY = ['West', 'East']
LOCATION_GROUP_SIZES = [1, 2, 3]
POLICE_FORCE_TIE_TOP = 2
NAME_DUP_SHARE = 0.35

CITY_COUNTY_DUP_SHARE = 0.35
CITY_COUNTY_BOUNDARY = True
CITY_NAME_DUP_SHARE = 0.35
CITY_WHITE_TIE_RANK = 5
CITY_BLACK_LITERALS = [10.0]
RACE_RANGE = (0.0, 100.0)

TABLE_SIZES = {'county_public_safety': 6, 'city': 8}

NULL_ROWS_PER_COLUMN = 1
NULL_TARGETS = [
    'county_public_safety.Name', 'county_public_safety.Population',
    'county_public_safety.Police_officers', 'county_public_safety.Residents_per_officer',
    'county_public_safety.Case_burden', 'county_public_safety.Crime_rate',
    'county_public_safety.Police_force', 'county_public_safety.Location',
    'city.County_ID', 'city.Name', 'city.White', 'city.Black', 'city.Amerindian',
    'city.Asian', 'city.Multiracial', 'city.Hispanic',
]


def residents_per_officer(population: int, officers: int) -> int:
    """round-half-up(Population / Police_officers), matching SQLite round() on the evidence rows."""
    if not officers:
        return 0
    x = population / officers
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)
