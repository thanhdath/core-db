"""The generation specification as data (implemented by construction in the samplers)."""

TABLE_SIZES = {'airports': 120, 'airlines': 100, 'routes': 400}

NULL_TARGETS = [('airlines', 'icao'), ('routes', 'alid'), ('routes', 'dst_apid'),
                ('routes', 'src_apid'), ('routes', 'codeshare')]

COUNTRY_VARIANTS = ['China', 'china', 'United States', 'united states', 'Canada', 'canada',
                    'Italy', 'italy', 'Iceland', 'iceland', 'Argentina', 'argentina']

COUNTRY_POOL = COUNTRY_VARIANTS + ['Cuba', 'cuba', 'Brazil', 'France', 'Germany', 'Japan',
                                   'Australia', 'Russia', 'Thailand', 'South Africa',
                                   'United Kingdom', 'Papua New Guinea', 'Greenland', 'Benin',
                                   'Burkina Faso', 'Ghana', 'Algeria', 'Mexico', 'India', 'Spain']

ACTIVE_VALUES = ['Y', 'N', 'y']

CODESHARE_VALUES = [None, 'Y']

GROUP_SIZE_TARGETS = [('airports', 'apid'), ('airports', 'country'), ('airports', 'name'),
                      ('airlines', 'alid'), ('airlines', 'country'), ('airlines', 'name')]

DUPLICATE_TARGETS = [('airports', 'country'), ('airports', 'name'), ('airports', 'city'),
                     ('airlines', 'country')]

TIE_TARGETS = [('airports', 'name'), ('airlines', 'alid'), ('airlines', 'country'), ('airlines', 'name')]

ELEVATION_MIN, ELEVATION_MAX = -1500, 9000
ELEVATION_TIE_ROWS = 3

X_MIN, X_MAX = -180.0, 180.0
Y_MIN, Y_MAX = -90.0, 90.0

FRESH_SHARE = 0.3

FK_NULL_P = 0.01
