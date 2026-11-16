"""Specification constants (value domains, enumerations, ranges, table sizes)."""

LG_IDS = ['NHL', 'WHA', 'NHA', 'WCHL', 'PCHA']
CONF_IDS = ['CC', 'WA', 'WC', 'EC']
DIV_IDS = ['AM', 'CA', 'ED', 'WD', 'WW', 'EW', 'PT', 'AD']
HOF_CATEGORIES = ['Player', 'Builder', 'Referee/Linesman']
AWARDS_COACHES = ['First Team All-Star', 'Second Team All-Star', 'Jack Adams', 'Baldwin', 'Schmertz']
AWARDS_PLAYERS_POS = ['C', 'LW', 'RW', 'D', 'G', 'F', 'W']
AWARDS_PLAYERS_AWARDS = ['First Team All-Star', 'Second Team All-Star', 'Hart', 'All-Rookie', 'Calder',
                         'King Clancy', 'Lady Byng', 'Crozier', 'Vezina', 'Norris', 'Art Ross', 'Maurice Richard']
RP = ['R', 'P']
SHOOT_CATCH = ['L', 'R', 'B']
ABBREV_TYPES = ['Conference', 'Division', 'Playoffs', 'Round']
PLAYOFFS = ['LCS', 'WCS', 'NHAF', 'SC', 'F', 'NHLF', 'PF', 'ND', 'QF', 'SF', 'DSF', 'SCSF', 'WP', 'Pre']
ROUNDS = ['SCF', 'F', 'SF', 'SCSF', 'WP', 'QF', 'Pre', 'DSF', 'QF', 'R1', 'R2', 'R3', 'Final']
NOTES_COACHES = ['interim', 'co-coach with Barry Smith', 'co-coach with Dave Lewis']
NOTES_AWARDS = ['tie', 'shared', 'Most Gentlemanly', 'Rookie', 'Best Goaltender', 'Scoring', 'MVP',
                'Best Defenceman']
NOTES_SERIES = ['EX', 'TG', 'ND', 'DEF']
NOTES_MISC = ['posthumous']

YEAR_MIN, YEAR_MAX = 1909, 2011
HOF_YEAR_MIN, HOF_YEAR_MAX = 1945, 2011
AWARDS_PLAYERS_YEAR_MIN, AWARDS_PLAYERS_YEAR_MAX = 1917, 2011
HEIGHT_MIN, HEIGHT_MAX = 60, 90
WEIGHT_MIN, WEIGHT_MAX = 100, 300
RANK_MIN, RANK_MAX = 1, 10
MONTH_MIN, MONTH_MAX = 1, 12
DAY_MIN, DAY_MAX = 1, 31
COUNT_MIN, COUNT_MAX = 0, 100
NUMERIC_TEXT_MIN, NUMERIC_TEXT_MAX = 0, 400

BOUNDARY = {
    ('Master', 'playerID'): ['', 'x', 'cleghsp01', 'CLEGHSP01', 'valiqst01', 'VALIQST01'],
    ('Master', 'coachID'): ['', 'x', 'USA', 'usa', 'Toronto', 'toronto'],
    ('Master', 'firstName'): ['Stanley', 'stanley', 'Scotty', 'scotty'],
    ('Master', 'birthCountry'): ['Toronto', 'toronto', 'USA', 'usa'],
    ('Master', 'height'): ['71', '72', '73', '74', '75', '76'],
    ('Teams', 'year'): [1923, 1924, 1925, 1994, 1995, 1996],
    ('Coaches', 'year'): [1921, 1922, 1923, 1997, 1998, 1999],
    ('Goalies', 'playerID'): ['roypa01', 'ROYPA01', 'valiqst01', 'VALIQST01'],
    ('Goalies', 'year'): [1991, 1992, 1993, 2004, 2005, 2006],
    ('Scoring', 'playerID'): ['roypa01', 'ROYPA01', 'adamsja01', 'ADAMSJA01'],
    ('Scoring', 'year'): [1919, 1920, 1921, 1991, 1992, 1993],
}

TABLE_SIZES = {
    'Teams': 40, 'Master': 200, 'Coaches': 60, 'HOF': 30, 'AwardsMisc': 20,
    'AwardsPlayers': 80, 'AwardsCoaches': 20, 'Goalies': 120, 'GoaliesSC': 20,
    'GoaliesShootout': 40, 'Scoring': 200, 'ScoringSC': 30, 'ScoringShootout': 60,
    'ScoringSup': 20, 'CombinedShutouts': 20, 'SeriesPost': 40, 'TeamSplits': 40,
    'TeamVsTeam': 200, 'TeamsHalf': 20, 'TeamsPost': 40, 'TeamsSC': 20, 'abbrev': 20,
}

NULL_TARGETS = [
    ('Master', 'playerID'), ('Master', 'coachID'), ('Master', 'firstName'),
    ('Master', 'height'), ('Master', 'birthCountry'), ('Goalies', 'SHO'),
    ('Scoring', 'playerID'),
]

FK_PARENT_NULL_CAP = 0.20

GROUP_SIZE_TARGETS = [
    ('Master', 'playerID'), ('Master', 'firstName'), ('Goalies', 'playerID'),
]

TIE_TARGETS = [
    ('Goalies', 'playerID', 'SUM(SHO)', 'sum'),
    ('Master', 'birthCountry', 'COUNT(*)', 'count'),
    ('Goalies', 'SHO', 'COALESCE(SHO,0)', 'coalesce'),
]

UNMATCHED_PARENT = [
    ('Master', 'playerID'), ('Master', 'coachID'), ('Teams', 'year'),
    ('Teams', 'tmID'), ('Coaches', 'coachID'), ('HOF', 'hofID'),
]

DUPLICATE_TARGETS = [
    ('Master', 'playerID'), ('Master', 'coachID'), ('Master', 'firstName'),
]

HEIGHT_SLASH_FORM = '7/1'

DEATH_AFTER_BIRTH = True

FIRST_NAMES = ['Antti', 'Bruce', 'George', 'Reg', 'Justin', 'Clarence', 'Gerry', 'Sid', 'Stanley',
               'Scotty', 'Wayne', 'Mario', 'Gordie', 'Bobby', 'Maurice', 'Jean', 'Ted', 'Doug',
               'Phil', 'Mark', 'Steve', 'Mike', 'Paul', 'Dave', 'Bill', 'Jack', 'Frank', 'Joe']
LAST_NAMES = ['Aalto', 'Abbey', 'Abbott', 'Abdelkader', 'Abel', 'Abgrall', 'Abid', 'Abrahamsson',
              'Adams', 'Allen', 'Anderson', 'Armstrong', 'Bailey', 'Beliveau', 'Bourque', 'Brodeur',
              'Clarke', 'Crosby', 'Dryden', 'Esposito', 'Gretzky', 'Hull', 'Howe', 'Lemieux',
              'Lidstrom', 'Messier', 'Orr', 'Richard', 'Roy', 'Sakic', 'Shanahan', 'Yzerman']
CITIES = ['Toronto', 'Montreal', 'Boston', 'Chicago', 'Detroit', 'New York', 'Philadelphia',
          'Pittsburgh', 'Vancouver', 'Calgary', 'Edmonton', 'Ottawa', 'Winnipeg', 'Quebec',
          'Lappeenranta', 'Sault Ste. Marie', 'Melville', 'Synenham', 'Muskegon']
COUNTRIES = ['Canada', 'USA', 'Finland', 'Sweden', 'Russia', 'Switzerland', 'Ireland',
             'Brunei Darussalam', 'Czech Republic', 'Germany', 'Slovakia', 'Latvia']
STATES = ['ON', 'MB', 'MI', 'SK', 'QC', 'AB', 'NL', 'BC', 'MN', 'PA', 'FL', 'NY']
TEAM_NAMES = ['Cobalt Silver Kings', 'Haileybury Hockey Club', 'Les Canadiens',
              'Montreal Shamrocks', 'Montreal Wanderers', 'Ottawa Senators',
              'Renfrew Creamery Kings', 'Montreal Canadiens', 'Edmonton Oilers',
              'Florida Panthers', 'Los Angeles Kings', 'Philadelphia Flyers',
              'Boston Bruins', 'Chicago Blackhawks', 'Detroit Red Wings', 'Toronto Maple Leafs']
TEAM_IDS = ['COB', 'HAI', 'LES', 'MOS', 'MOW', 'OT1', 'REN', 'MOC', 'MTL', 'MTW', 'TBS', 'TOB',
            'QU1', 'VA1', 'SEA', 'TOA', 'VML', 'PO1', 'CHI', 'DET', 'STL', 'KCS', 'DTC', 'DTF',
            'CBS', 'PHI', 'BOS', 'NYR', 'TOR', 'MTL', 'VAN', 'LAK', 'ANA', 'CIN', 'COL', 'PHO',
            'WAS', 'NEW', 'OTT', 'FLO', 'TBL', 'BUF', 'ATL', 'CAL', 'EDM', 'PIT', 'NYA', 'CLF',
            'PHB', 'LAS', 'OAK', 'QUN', 'TOT', 'OT1', 'OTS', 'MTM', 'VIC', 'TRS', 'MOC', 'EDE']
FRANCH_IDS = ['BKN', 'MTL', 'TBS', 'MOS', 'MTW', 'STE', 'REN', 'PO1', 'CHI', 'DET', 'BOS', 'NYR']
PLAYER_IDS = ['aaltoan01', 'abbeybr01', 'abbotge01', 'abbotre01', 'abdelju01', 'abelcl01',
              'abelge01', 'abelsi01', 'adamsbi01', 'adamsja01', 'anderer02', 'anderjo03',
              'andrell01', 'arbouam01', 'arbouty01', 'barboal01', 'cleghsp01', 'valiqst01',
              'roypa01', 'benedcl01', 'clancki01', 'holmeha01', 'lehmahu01', 'lindsbe01',
              'moranpa01', 'murrato01', 'reidch01', 'chabolo01', 'bibeapa01', 'plantja01',
              'smithga01', 'hallgl01', 'aubryse01', 'binklle01', 'esposto01', 'grantbe01',
              'gardibe01', 'hodgech01', 'wakeler01', 'gamblbr01', 'parenbe01', 'lowro01',
              'broderi01', 'aebisda01', 'andercr01', 'aubinje01', 'auldal01', 'bacasja01',
              'bachmri01', 'backsni01', 'belfoed01', 'adamske01', 'afanadm01', 'afinoma01',
              'alexeni01', 'alfreda01', 'allisja01', 'amontto01', 'anisiar01', 'actonke01',
              'adamsgr01', 'allismi01', 'archida01', 'bassebo01', 'bennibr01', 'bodgedo01',
              'bradlbr01']
COACH_IDS = ['patrile01c', 'irvindi01c', 'gormato01c', 'adamsja01c', 'hartce01c', 'rossar01c',
             'duttore01c', 'thomppa01c', 'abelsi01c', 'agnewga01c', 'allenke01c', 'allisda01c',
             'anderji01c', 'anderjo01c', 'angotlo01c']
HOF_IDS = ['abelsi01h', 'adamsch01h', 'adamsja01h', 'adamswe01h', 'ahearbu01h', 'ahearfr01h',
           'allanmo01h', 'allenke01h', 'wirtzar01h', 'chadwbi01h', 'torrebi01h', 'johnsbo02c',
           'pulfobo01']
MISC_NAMES = ['1960 U.S. Olympic Hockey Team', '1998 U.S. Olympic Women\'s Hockey Team',
              'Al Arbour', 'Alex Delvecchio', 'Art Berglund', 'Art Ross', 'Arthur Wirtz',
              'Bill Chadwick', 'Bunny Ahearne', 'Frank Ahearn', 'Montagu Allan', 'Keith Allen']
MISC_IDS = ['arboual01', 'delveal01', 'rossar01', 'wirtzar01h', 'chadwbi01h', 'torrebi01h',
            'johnsbo02c', 'pulfobo01']
ABBREV_CODES = ['CC', 'EC', 'WA', 'WC', 'AD', 'AM', 'AT', 'CA', 'ED', 'WD', 'WW', 'EW', 'PT',
                'ND', 'SC', 'F', 'QF', 'SF', 'DSF', 'SCSF', 'WP', 'Pre', 'LCS', 'WCS', 'NHAF',
                'NHLF', 'PF', 'R1', 'R2', 'R3']
ABBREV_FULLNAMES = ['Campbell Conference', 'Eastern Conference', 'Wales Conference',
                    'Western Conference', 'Adams Division', 'American Division',
                    'Atlantic Division', 'Canadian Division', 'Edmonton Division',
                    'Western Division', 'World Division', 'Eastern Division',
                    'Pacific Division', 'Norris Division', 'Smythe Division',
                    'Patrick Division']
