"""Generation specification, implemented by construction (no SQL evaluation)."""

ENUMS = {
    ('Batting_Style', 'Batting_hand'): ['Left-hand bat', 'Right-hand bat'],
    ('Bowling_Style', 'Bowling_skill'): [
        'Right-arm medium', 'Right-arm offbreak', 'Right-arm fast-medium', 'Legbreak googly',
        'Right-arm medium-fast', 'Left-arm fast-medium', 'Slow left-arm orthodox',
        'Slow left-arm chinaman'],
    ('Extra_Type', 'Extra_Name'): ['legbyes', 'wides', 'byes', 'noballs', 'penalty'],
    ('Out_Type', 'Out_Name'): ['caught', 'bowled', 'run out', 'lbw', 'retired hurt', 'stumped',
                               'caught and bowled', 'hit wicket'],
    ('Outcome', 'Outcome_Type'): ['Result', 'No Result', 'Superover'],
    ('Rolee', 'Role_Desc'): ['Captain', 'Keeper', 'Player', 'CaptainKeeper'],
    ('Toss_Decision', 'Toss_Name'): ['field', 'bat'],
    ('Win_By', 'Win_Type'): ['runs', 'wickets', 'NO Result', 'Tie'],
}

ENUM_CASE_VARIANTS = {
    ('Batting_Style', 'Batting_hand'): ['left-hand bat', 'right-hand bat'],
    ('Bowling_Style', 'Bowling_skill'): [' Legbreak', ' legbreak', 'Legbreak', 'legbreak', ' Legb', ' legb'],
    ('Win_By', 'Win_Type'): ['WICKETS', 'RUNS'],
    ('Toss_Decision', 'Toss_Name'): ['FIELD', 'BAT'],
    ('Rolee', 'Role_Desc'): ['captain'],
}

RANGES = {
    ('Player', 'Batting_hand'): (1, 2),
    ('Player', 'Bowling_skill'): (1, 14),
    ('Match', 'Toss_Decide'): (1, 2),
    ('Match', 'Outcome_type'): (1, 3),
    ('Match', 'Win_Type'): (1, 4),
    ('Batsman_Scored', 'Runs_Scored'): (0, 6),
    ('Extra_Runs', 'Extra_Runs'): (0, 5),
    ('Ball_by_Ball', 'Over_Id'): (1, 20),
    ('Ball_by_Ball', 'Ball_Id'): (1, 9),
    ('Ball_by_Ball', 'Innings_No'): (1, 4),
    ('Wicket_Taken', 'Innings_No'): (1, 4),
    ('Extra_Runs', 'Innings_No'): (1, 4),
    ('Batsman_Scored', 'Innings_No'): (1, 4),
    ('Match', 'Win_Margin'): (0, 200),
    ('Season', 'Season_Year'): (2007, 2016),
}

DATE_RANGES = {
    ('Player', 'DOB'): ('1960-01-01', '2000-12-31'),
    ('Match', 'Match_Date'): ('2007-12-31', '2016-01-01'),
}

NULL_TARGETS = [
    ('Player', 'Bowling_skill'), ('Match', 'Win_Margin'), ('Match', 'Match_Winner'),
    ('Match', 'Man_of_the_Match'), ('Wicket_Taken', 'Fielders'), ('Player_Match', 'Team_Id'),
    ('Ball_by_Ball', 'Team_Batting'), ('Ball_by_Ball', 'Team_Bowling'),
    ('Ball_by_Ball', 'Striker_Batting_Position'), ('Ball_by_Ball', 'Striker'),
    ('Ball_by_Ball', 'Non_Striker'), ('Ball_by_Ball', 'Bowler'),
    ('Batsman_Scored', 'Runs_Scored'), ('Extra_Runs', 'Extra_Type_Id'),
    ('Extra_Runs', 'Extra_Runs'), ('Wicket_Taken', 'Player_Out'), ('Wicket_Taken', 'Kind_Out'),
]

TEXT_TARGETS = {
    ('Player', 'Player_Name'): ['Gurkeerat Singh', 'gurkeerat singh', 'Yuvraj Singh',
                                'yuvraj singh', 'CH Gayle', 'ch gayle'],
    ('Team', 'Team_Name'): ['Mumbai Indians', 'mumbai indians', 'Pune Warriors', 'pune warriors',
                            'Royal Challengers Bangalore', 'royal challengers bangalore'],
    ('Country', 'Country_Name'): ['South Africa', 'south africa', 'India', 'india',
                                  'Australia', 'australia'],
    ('Venue', 'Venue_Name'): ['Newlands', 'newlands', 'MA Chidambaram Stadium',
                              'ma chidambaram stadium', 'Wankhede Stadium', 'wankhede stadium'],
}

INT_TARGETS = {
    ('Match', 'Match_Id'): [336038, 336039, 336040, 548334, 548335, 548336],
    ('Match', 'Match_Winner'): [6, 7, 8],
    ('Player', 'Player_Id'): [1, 2, 3],
    ('Team', 'Team_Id'): [0, 1, 2, 7, 8, 9],
    ('Match', 'Season_Id'): [0, 1, 2, 8, 9, 10],
    ('Match', 'Team_1'): [9, 10, 11],
    ('Match', 'Team_2'): [9, 10, 11],
    ('Season', 'Season_Id'): [0, 1, 2, 6, 7, 8],
    ('Season', 'Season_Year'): [2007, 2008, 2009, 2010, 2011, 2012],
}

DATE_TARGETS = {
    ('Match', 'Match_Date'): ['2007-12-31', '2008-01-01', '2008-12-31', '2009-01-01',
                              '2008-04-30', '2008-05-01', '2008-05-31', '2008-06-01',
                              '2015-04-19', '2015-04-18'],
    ('Player', 'DOB'): ['1984-12-31', '1985-01-01', '1985-12-31', '1986-01-01',
                        '1969-12-31', '1970-01-01', '1970-12-31', '1971-01-01'],
}

TABLE_SIZES = {
    'Batting_Style': 2, 'Bowling_Style': 14, 'Country': 12, 'City': 29, 'Venue': 35,
    'Team': 13, 'Season': 9, 'Toss_Decision': 2, 'Win_By': 4, 'Out_Type': 9, 'Outcome': 3,
    'Extra_Type': 5, 'Rolee': 4, 'Player': 200, 'Umpire': 52, 'Match': 200,
    'Player_Match': 800, 'Ball_by_Ball': 1200, 'Batsman_Scored': 1200, 'Extra_Runs': 300,
    'Wicket_Taken': 300,
}

REFERENCE_TABLES = {'Batting_Style', 'Bowling_Style', 'Country', 'City', 'Venue', 'Team',
                    'Season', 'Toss_Decision', 'Win_By', 'Out_Type', 'Outcome', 'Extra_Type',
                    'Rolee'}


def enum_values(table: str, column: str) -> list:
    """Enumerated domain plus required case variants (deduplicated, order kept)."""
    base = list(ENUMS.get((table, column), []))
    for v in ENUM_CASE_VARIANTS.get((table, column), []):
        if v not in base:
            base.append(v)
    return base


def int_range(table: str, column: str):
    return RANGES.get((table, column))


def date_range(table: str, column: str):
    return DATE_RANGES.get((table, column))


def is_null_target(table: str, column: str) -> bool:
    return (table, column) in NULL_TARGETS


def text_targets(table: str, column: str) -> list:
    return TEXT_TARGETS.get((table, column), [])


def int_targets(table: str, column: str) -> list:
    return INT_TARGETS.get((table, column), [])


def date_targets(table: str, column: str) -> list:
    return DATE_TARGETS.get((table, column), [])


def table_size(table: str) -> int:
    return TABLE_SIZES.get(table, 0)
