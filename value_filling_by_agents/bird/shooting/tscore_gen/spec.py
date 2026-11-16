"""Specification constants (generation specification, round 1)."""

TABLE_SIZES = {'incidents': 40, 'officers': 60, 'subjects': 40}

ENUMS = {
    ('incidents', 'subject_statuses'): ['Deceased', 'Shoot and Miss', 'Injured', 'Other',
                                        'Deceased Injured', '1 Deceased 1 Injured', '2 Injured'],
    ('incidents', 'subject_weapon'): ['Vehicle', 'Shotgun', 'Handgun', 'Toy Handun', 'Knife',
                                      'Unarmed', 'Rifle', 'Rock'],
    ('officers', 'gender'): ['M', 'F'],
    ('officers', 'race'): ['L', 'W', 'B', 'A'],
    ('subjects', 'gender'): ['M', 'F'],
    ('subjects', 'race'): ['L', 'B', 'W', 'A'],
}

BOUNDARY = {
    ('incidents', 'date'): ['2006-12-31', '2007-01-01', '2007-12-31', '2008-01-01', '2008-12-31',
                            '2009-01-01', '2015-05-31', '2015-06-01', '2015-06-02', '2015-06-29',
                            '2015-06-30', '2015-07-01'],
    ('incidents', 'subject_weapon'): ['Vehicle', 'vehicle'],
    ('incidents', 'subject_statuses'): ['Shoot and Miss', 'shoot and miss'],
    ('subjects', 'gender'): ['F', 'f'],
    ('subjects', 'race'): ['B', 'b', 'W', 'w'],
    ('officers', 'race'): ['W', 'w'],
    ('officers', 'gender'): ['M', 'm'],
}

TIE_COLUMNS = {
    ('incidents', 'subject_weapon'),
    ('subjects', 'gender'),
    ('subjects', 'race'),
    ('subjects', 'last_name'),
}

DUP_COLUMNS = {
    ('incidents', 'subject_weapon'),
    ('subjects', 'gender'),
    ('subjects', 'race'),
    ('subjects', 'last_name'),
}

NULL_TARGETS = {
    ('officers', 'race'): 0.011,
    ('officers', 'first_name'): 0.008,
    ('subjects', 'first_name'): 0.081,
}

UNMATCHED_JOIN_COLUMNS = {
    ('incidents', 'case_number'), ('subjects', 'case_number'), ('officers', 'case_number'),
}

DATE_MIN_YEAR = 2004
DATE_MAX_YEAR = 2016

SURNAMES = ['Patino', 'Fillingim', 'Padilla', 'Poston', 'Mondy', 'Armstrong', 'Woods', 'Culp',
            'Curry', 'Chavez', 'Salinas', 'Smith', 'Dews', 'Spearman', 'Watkins', 'Garcia',
            'Tollerton', 'Cardenas', 'Ruben', 'Nguyen', 'Ragsdale', 'Cole', 'Jaquez', 'Tahbone',
            'Luster', 'Gilstrap', 'Evans', 'Mims', 'Rittenhouse', 'Delesantos', 'Robles']
GIVEN_NAMES = ['Michael', 'Brian', 'Gilbert', 'Jerry', 'Jesse', 'Barrick', 'Mark', 'Douglas',
               'James', 'Gabriel', 'Nick', 'Antonio', 'Damion', 'Caleb', 'David', 'Tony',
               'Aaron', 'Steven', 'Fredirick', 'Buu', 'Barry', 'Bobby', 'Christopher', 'Jacqueline',
               'Desmond', 'Bryan', 'Carlton', 'Amanda', 'Juan']

LOCATIONS = ['7400 Bonnie View Road', '8218 Willoughby Boulevard', '4800 Columbia Ave',
             '2400 Walnut Hill Lane', '3847 Timberglen Road, #3116', '9850 Whitehurst Drive',
             '200 S Madison Avenue', '5423 Peterson Lane #259']
