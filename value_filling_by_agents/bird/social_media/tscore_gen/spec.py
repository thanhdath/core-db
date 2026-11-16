"""The generation specification, encoded as data (no SQL is ever evaluated)."""

TABLE_SIZES = {'location': 40, 'user': 60, 'twitter': 200}

ENUMS = {
    ('user', 'Gender'): ['Male', 'Female', 'Unisex', 'Unknown'],
    ('twitter', 'Weekday'): ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                             'Friday', 'Saturday', 'Sunday'],
    ('twitter', 'IsReshare'): ['TRUE', 'FALSE'],
}

INT_RANGES = {
    ('twitter', 'Hour'): (0, 23),
    ('twitter', 'Day'): (1, 31),
    ('twitter', 'Klout'): (0, 100),
    ('twitter', 'Reach'): (0, 10000),
    ('twitter', 'RetweetCount'): (0, 10000),
    ('twitter', 'Likes'): (0, 10000),
}

REAL_RANGES = {
    ('twitter', 'Sentiment'): (-5.0, 5.0),
}

SENTIMENT_SCALE = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 1.333333373, 2.0, 3.0, 4.0]

BOUNDARY_VALUES = {
    ('twitter', 'Likes'): [99, 100, 101],
    ('twitter', 'RetweetCount'): [29, 30, 31],
    ('twitter', 'Sentiment'): [-0.0001, 0.0, 0.0001],
    ('twitter', 'Weekday'): ['Monday', 'monday'],
    ('twitter', 'IsReshare'): ['TRUE', 'true'],
    ('user', 'Gender'): ['Male', 'male'],
}

TEXT_BOUNDARY_VALUES = {
    ('location', 'Country'): ['Argentina', 'argentina'],
    ('location', 'State'): ['Santa', 'santa', 'Santa Fe', 'santa fe',
                            'Connecticut', 'connecticut'],
    ('location', 'City'): ['Bangkok', 'bangkok', 'Buenos Aires', 'buenos aires'],
}

DUPLICATE_SHARE = {
    ('twitter', 'text'): (0.20, 0.50),
    ('location', 'StateCode'): (0.20, 0.50),
}

TIE_VALUES = {
    ('twitter', 'Reach'): 3,
    ('twitter', 'Lang'): 4,
    ('location', 'Country'): 3,
    ('location', 'City'): 3,
    ('user', 'Gender'): 2,
    ('twitter', 'UserID'): 1,
}

NULL_SHARE = {
    ('twitter', 'Likes'): 0.15,
    ('twitter', 'UserID'): 0.10,
    ('twitter', 'Klout'): 0.15,
    ('twitter', 'LocationID'): 0.10,
    ('location', 'State'): 0.10,
    ('location', 'StateCode'): 0.10,
    ('location', 'City'): 0.10,
    ('user', 'Gender'): 0.10,
}

FK_NULL_SHARE = 0.08

LIKE_LITERALS = {
    ('twitter', 'text'): ['One of our favorite stories is @FINRA_News%'],
}

TEXT_PK_PREFIX = {'twitter': 'tw', 'user': 'us'}

DIFFERENT_VALUES = {
    ('twitter', 'Likes'): 'UserID',
    ('twitter', 'Sentiment'): 'UserID',
    ('twitter', 'Klout'): 'UserID',
    ('twitter', 'Day'): 'UserID',
    ('twitter', 'IsReshare'): None,
}
