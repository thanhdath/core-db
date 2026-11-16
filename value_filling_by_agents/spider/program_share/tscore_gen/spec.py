"""Specification constants (per-column exceptions, semantic rules, table sizes)."""

TABLE_SIZES = {'program': 5, 'channel': 8, 'broadcast': 10, 'broadcast_share': 9}

PROGRAM_ID_MIN = 1
LAUNCH_RANGE = (1990.0, 2025.0)
CHANNEL_ID_MIN = 1
PERCENT_RANGE = (0.0, 100.0)
TIME_OF_DAY_VALUES = ['Morning', 'Noon', 'Night', 'morning', 'night']
DATE_POOL = ['01,May', '02,May', '03,May', '04,April', '10,Jun', '11,May', '13,May',
             '05,May', '06,Jun', '07,April', '08,May', '09,Jun', '12,April']

DUPLICATE_SHARE = (0.2, 0.5)

GROUP_SIZE_TARGETS = (1, 2, 3)

TIE_RANKS = (1, 10, 1000)

NULL_TARGETS = [
    ('program', 'Name'), ('program', 'Origin'), ('program', 'Owner'), ('program', 'Launch'),
    ('channel', 'Name'), ('channel', 'Owner'), ('channel', 'Share_in_percent'),
    ('channel', 'Rating_in_percent'),
    ('broadcast', 'Time_of_day'),
    ('broadcast_share', 'Date'), ('broadcast_share', 'Share_in_percent'),
]

FRESH_VALUE_SHARE = 0.3
NUM_PERTURB = (1, -1, 2, -2)
