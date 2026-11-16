"""Specification constants (value domains, enumerations, boundaries, NULL shares)."""

IHSAA_CLASS = ['A', 'AA', 'AAA']
IHSAA_FOOTBALL_CLASS = ['A', 'AA', 'AAA', 'AAAA']

ENROLLMENT_RANGE = (1, 1000)
YEAR_RANGE = (1995, 2010)
YEAR_BOUNDARY = [2002, 2003, 2004]
BUDGETED_RANGE = (0, 200000)
INVESTED_RANGE = (0, 200000)
PERCENT_BUDGETED_RANGE = (0.0, 5.0)
PERCENT_INVESTED_RANGE = (0.0, 5.0)
TEXT_PERCENT_RANGE = (0.0, 300.0)
AMOUNT_RANGE = (0.0, 20.0)

BUDGETED_BOUNDARY = [99, 100, 101]
INVESTED_BOUNDARY = [9, 10, 11]
AMOUNT_BOUNDARY = [8.49, 8.5, 8.51, 8.99, 9.0, 9.01, 9.99, 10.0, 10.01]
AMOUNT_SUM_BOUNDARY = [9, 10, 11]

SCHOOL_NAME_POOL = ['Bremen', 'Culver Community', 'Glenn', 'Jimtown', 'Knox Community',
                    'LaVille', 'New Prairie', 'Triton', 'Plymouth', 'Warsaw', 'Rochester',
                    'NorthWood', 'Fairfield', 'Westview', 'Prairie Heights', 'Central Noble']
LOCATION_POOL = ['Bremen', 'Culver', 'Walkerton', 'Elkhart', 'Knox', 'Lakeville',
                 'New Carlisle', 'Bourbon', 'Plymouth', 'Warsaw', 'Rochester', 'Nappanee']
MASCOT_POOL = ['Lions', 'Cavaliers', 'Falcons', 'Jimmies', 'Redskins', 'Lancers',
               'Cougars', 'Trojans', 'Warriors', 'Panthers', 'Wildcats', 'Eagles']
COUNTY_POOL = ['50 Marshall', '71 St. Joseph', '20 Elkhart', '75 Starke',
               '46 LaPorte', '43 Kosciusko', '25 Fulton', '17 DeKalb']
DONATOR_POOL = ['Monte Plata', 'San Jose de Ocoa', 'Distrito Nacional', 'Valverde',
                'San Cristobal', 'Santo Domingo Este', 'Santiago', 'Duarte',
                'La Vega', 'Moca', 'Bani', 'Azua']

NULL_SHARE = 0.05

TABLE_SIZES = {'School': 8, 'budget': 8, 'endowment': 11}

GROUP_SIZE_TARGETS = [1, 2, 3]

UNMATCHED_BUDGET_SCHOOL_INDEX = 0
MATCHED_ENDOWMENT_SCHOOL_INDEX = 1
