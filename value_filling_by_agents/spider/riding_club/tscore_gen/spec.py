"""Specification constants (generation specification, per-column exceptions, semantic rules)."""

TABLE_SIZES = {'club': 6, 'coach': 5, 'player': 14, 'player_coach': 7, 'match_result': 6}

ENUMS = {
    ('player', 'Gender'): ['M', 'F'],
    ('coach', 'Gender'): ['M', 'F'],
    ('player', 'Rank'): ['1st', '2nd', '3rd', '4th'],
}

RANGES = {
    ('club', 'Start_year'): (1990, 2020),
    ('player_coach', 'Starting_year'): (1990, 2020),
    ('player', 'Votes'): (0, 20000),
    ('coach', 'Rank'): (1, 5),
    ('match_result', 'Rank'): (1, 6),
    ('match_result', 'Gold'): (0, 25),
    ('match_result', 'Big_Silver'): (0, 20),
    ('match_result', 'Small_Silver'): (0, 20),
    ('match_result', 'Bronze'): (0, 15),
    ('match_result', 'Points'): (0, 200),
}

DUP_SHARE = {
    ('player', 'Player_name'): 0.35,
    ('player', 'Residence'): 0.35,
    ('player', 'Occupation'): 0.35,
    ('player', 'Sponsor_name'): 0.35,
    ('player', 'Gender'): 0.30,
    ('coach', 'Coach_name'): 0.35,
}

GROUP_SIZE_COLUMNS = [
    ('player', 'Residence'),
    ('player', 'Occupation'),
    ('player', 'Sponsor_name'),
    ('club', 'Club_name'),
    ('match_result', 'Club_ID'),
]

NULL_SHARE = 0.08

NULL_TARGETS = [('coach', 'Club_ID')]

UNMATCHED = [
    (('player_coach', 'Player_ID'), ('player', 'Player_ID')),
    (('player_coach', 'Coach_ID'), ('coach', 'Coach_ID')),
    (('coach', 'Club_ID'), ('club', 'Club_ID')),
    (('match_result', 'Club_ID'), ('club', 'Club_ID')),
]
UNMATCHED_NO_NULL = {('player_coach', 'Player_ID')}

TIE_TABLE = 'match_result'
TIE_GROUP_COL = 'Club_ID'

AGG_DISTINCT_COLUMNS = [('player', 'Player_name'), ('player_coach', 'Player_ID')]

GENDER_BOTH = ('player', 'Gender')
