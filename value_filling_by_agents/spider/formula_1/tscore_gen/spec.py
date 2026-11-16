"""Specification constants (generation specification, round 2)."""

ENUMS = {
    ('circuits', 'country'): ['Spain', 'Malaysia', 'UK', 'Belgium', 'France'],
    ('constructors', 'nationality'): ['Japanese'],
    ('drivers', 'nationality'): ['German'],
    ('results', 'statusId'): [1, 2, 3, 4, 5, 6, 7, 8, 10, 11],
    ('results', 'position'): ['1', '2', '3', '4', '5', '6', '7', '8', 'R', 'D', 'E', 'F', 'W'],
    ('status', 'status'): ['Finished', 'Disqualified', 'Accident', 'Collision',
                           'Engine', 'Gearbox', 'Transmission', 'Clutch'],
    ('constructorResults', 'status'): [None, 'D'],
}

BOUNDARY = {
    ('races', 'year'): [1998, 1999, 2000, 2001, 2008, 2009, 2010],
    ('driverStandings', 'position'): [1, 2],
    ('driverStandings', 'positionText'): ['1', '2'],
    ('races', 'name'): ['Australian Grand Prix', 'australian grand prix'],
}

RANGES = {
    ('circuits', 'lat'): (-90.0, 90.0),
    ('circuits', 'lng'): (-180.0, 180.0),
    ('races', 'year'): (1950, 2017),
    ('races', 'round'): (1, 21),
    ('results', 'positionOrder'): (1, 39),
    ('results', 'grid'): (0, 35),
    ('results', 'points'): (0.0, 25.0),
    ('driverStandings', 'points'): (0.0, 200.0),
    ('driverStandings', 'position'): (1, 108),
    ('driverStandings', 'wins'): (0, 10),
    ('constructorStandings', 'points'): (0.0, 200.0),
    ('constructorStandings', 'position'): (1, 22),
    ('constructorStandings', 'wins'): (0, 10),
    ('constructorResults', 'points'): (0.0, 25.0),
    ('qualifying', 'position'): (1, 28),
    ('qualifying', 'number'): (1, 99),
    ('pitStops', 'stop'): (1, 5),
    ('pitStops', 'lap'): (1, 200),
    ('pitStops', 'milliseconds'): (1, 120000),
    ('lapTimes', 'lap'): (1, 200),
    ('lapTimes', 'milliseconds'): (1, 200000),
    ('lapTimes', 'position'): (1, 30),
}

HARD_RANGES = {
    ('results', 'laps'): (0, 200),
    ('results', 'milliseconds'): (1, 10000000),
}

NULL_SHARE = {
    ('results', 'fastestLapSpeed'): 0.20,
    ('races', 'date'): 0.10,
    ('constructorResults', 'status'): 0.50,
}
DEFAULT_NULL_SHARE = 0.10

LIKE_PATTERNS = {
    ('races', 'date'): '2017-%',
}

GROUP_SIZE_TARGETS = {
    ('results', 'driverId'): [1, 2, 3, 4, 5, 6, 7, 8, 9],
    ('drivers', 'surname'): [1, 2, 3, 4, 5, 6, 7, 8, 9],
}
AGGREGATE_BOUNDARY = {
    ('drivers', 'driverId'): [4, 5, 6, 7, 8],
    ('results', 'resultId'): [4, 5, 6],
}
DISTINCT_DUP_SHARE = {
    ('drivers', 'driverId'): 0.30,
    ('qualifying', 'driverId'): 0.30,
}
TIE_COLUMNS = {
    ('races', 'year'): 'DESC',
    ('races', 'date'): 'DESC',
    ('drivers', 'surname'): 'ASC',
}
TIE_CHILD_COLUMNS = {
    ('results', 'raceId'): 'DESC',
    ('results', 'driverId'): 'DESC',
}

UNMATCHED = {
    ('races', 'raceId'): [('results', 'raceId'), ('qualifying', 'raceId'),
                          ('driverStandings', 'raceId'), ('constructorStandings', 'raceId'),
                          ('constructorResults', 'raceId'), ('pitStops', 'raceId'),
                          ('lapTimes', 'raceId')],
    ('drivers', 'driverId'): [('results', 'driverId'), ('pitStops', 'driverId'),
                              ('driverStandings', 'driverId'), ('qualifying', 'driverId'),
                              ('lapTimes', 'driverId')],
    ('constructors', 'constructorId'): [('results', 'constructorId'), ('qualifying', 'constructorId'),
                                        ('constructorStandings', 'constructorId'),
                                        ('constructorResults', 'constructorId')],
    ('status', 'statusId'): [('results', 'statusId')],
}

RESERVED_PARENTS = {
    'races': 'raceId',
    'drivers': 'driverId',
    'constructors': 'constructorId',
    'status': 'statusId',
}

TABLE_SIZES = {
    'circuits': 8, 'races': 8, 'drivers': 8, 'status': 8, 'seasons': 8,
    'constructors': 8, 'constructorStandings': 8, 'results': 8, 'driverStandings': 8,
    'constructorResults': 8, 'qualifying': 8, 'pitStops': 8, 'lapTimes': 8,
}

DATE_MIN, DATE_MAX = '1950-01-01', '2017-12-31'
DOB_MIN, DOB_MAX = '1900-01-01', '2000-12-31'
