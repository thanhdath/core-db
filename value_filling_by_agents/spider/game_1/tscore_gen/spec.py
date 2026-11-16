"""Specification tables (value domains, enums, ranges, boundary literals, sizes)."""

TABLE_SIZES = {'Student': 34, 'Video_Games': 6, 'Plays_Games': 10, 'SportsInfo': 14}

ENUMS = {
    ('Student', 'Sex'): ['F', 'M'],
    ('Student', 'Major'): [50, 100, 520, 540, 550, 600],
    ('Video_Games', 'GType'): ['Collectible card game', 'Walking Simulator', 'Role-playing game',
                               'Grand strategy', 'Frist-person shooter',
                               'Massively multiplayer online game'],
    ('SportsInfo', 'OnScholarship'): ['Y', 'N'],
}

RANGES = {
    ('Student', 'Age'): (15, 30),
    ('Plays_Games', 'Hours_Played'): (0, 2000),
    ('SportsInfo', 'HoursPerWeek'): (0, 200),
    ('SportsInfo', 'GamesPlayed'): (0, 200),
}

BOUNDARY_NUM = {
    ('Plays_Games', 'Hours_Played'): [999, 1000, 1001],
    ('Student', 'Major'): [599, 600, 601],
    ('SportsInfo', 'HoursPerWeek'): [9, 10, 11],
}
BOUNDARY_TEXT = {
    ('SportsInfo', 'SportName'): ['Football', 'football', 'll', 'LL'],
    ('Student', 'Sex'): ['F', 'f', 'M', 'm'],
    ('SportsInfo', 'OnScholarship'): ['Y', 'y'],
    ('Student', 'Fname'): ['Linda', 'linda'],
    ('Student', 'LName'): ['Smith', 'smith'],
}

DISTINCT_COLS = [('Student', 'StuID'), ('Video_Games', 'GType'), ('Video_Games', 'GName')]

GROUP_COLS = [('Student', 'StuID'), ('SportsInfo', 'StuID'), ('Plays_Games', 'GameID'),
              ('Video_Games', 'GType'), ('Video_Games', 'GameID'), ('Video_Games', 'GName')]

TIE_COLS = [('Plays_Games', 'Hours_Played'), ('Video_Games', 'GType')]

NULL_TARGETS = [('SportsInfo', 'StuID'), ('Plays_Games', 'StuID'), ('Plays_Games', 'GameID')]

CITY_CODES = ['BAL', 'HKG', 'WAS', 'CHI', 'YYZ', 'PIT', 'HOU', 'PHL', 'NYC', 'LAX', 'SFO', 'BOS']

SHORT_TEXT = [('Student', 'LName'), ('Student', 'Fname')]

QUANTITY = [('Student', 'Advisor')]
