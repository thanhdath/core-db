"""The generation specification, encoded as data (no SQL is ever evaluated)."""

CITY_POOL = ['Palo Alto', 'san francisco', 'San Francisco', 'yolo', 'Bay', 'oakland',
             'berkeley', 'santa cruz', 'los gatos', 'mountain view', 'sunnyvale', 'fremont']
COUNTY_POOL = ['yolo county', 'santa cruz county', 'SANTA CRUZ', 'santa cruz', 'yolo',
               'bay area', 'alameda county', 'san mateo county', 'contra costa county']
REGION_POOL = ['bay area', 'Bay Area', 'north bay', 'south bay', 'peninsula', 'east bay']
FOOD_POOL = ['chinese', 'french', 'italian', 'japanese', 'mexican', 'indian', 'thai',
             'korean', 'greek', 'jamerican']
NAME_POOL = ['jamerican cuisine', 'buttercup kitchen', 'denny', 'buttercup hen',
             'golden gate grill', 'bay breeze cafe', 'sunset diner', 'harbor house',
             'palo alto bistro', 'mission taqueria']
STREET_POOL = ['Main St', 'El Camino Real', 'University Ave', 'Market St', 'Mission St',
               'Bay Rd', 'Oak Ave', 'Castro St', 'High St', 'Park Blvd']

BOUNDARY = {
    ('RESTAURANT', 'FOOD_TYPE'): ['chinese', 'CHINESE', 'french', 'FRENCH', 'italian',
                                  'ITALIAN', 'Italian', 'French', 'Chinese', 'frenc', 'FRENC'],
    ('GEOGRAPHIC', 'CITY_NAME'): ['Palo Alto', 'palo alto', 'san francisco', 'SAN FRANCISCO',
                                  'paloalto', 'PALOALTO', 'San Francisco', 'yolo', 'YOLO',
                                  'Bay', 'bay', 'BAY'],
    ('RESTAURANT', 'CITY_NAME'): ['san francisco', 'SAN FRANCISCO'],
    ('GEOGRAPHIC', 'COUNTY'): ['yolo county', 'YOLO COUNTY', 'santa cruz county',
                               'SANTA CRUZ COUNTY', 'SANTA CRUZ', 'santa cruz', 'yolo',
                               'YOLO', 'bay area', 'BAY AREA', 'a cruz coun', 'A CRUZ COUN'],
    ('LOCATION', 'CITY_NAME'): ['san francisco', 'SAN FRANCISCO', 'palo alto', 'PALO ALTO',
                                'alo', 'ALO', ' franci', ' FRANCI', 'san frisco', 'SAN FRISCO'],
    ('RESTAURANT', 'NAME'): ['jamerican cuisine', 'JAMERICAN CUISINE', 'buttercup kitchen',
                             'BUTTERCUP KITCHEN', 'denny', 'DENNY', 'buttercup hen',
                             'BUTTERCUP HEN', 'p kitche', 'P KITCHE', 'jamericae', 'JAMERICAE'],
    ('GEOGRAPHIC', 'REGION'): ['bay area', 'BAY AREA', 'Bay Area', 'by area', 'BY AREA'],
}

LIKE_PATTERNS = {
    ('RESTAURANT', 'FOOD_TYPE'): ['chinese', 'CHINESE', 'french', 'FRENCH', 'italian', 'ITALIAN'],
    ('GEOGRAPHIC', 'COUNTY'): ['santa cruz county', 'San%', 'Santa Cruz', '%yolo%',
                               'yolo county', '%bay%'],
    ('RESTAURANT', 'NAME'): ['jamerican cuisine', 'buttercup kitchen', 'denny', 'buttercup hen'],
}

NULL_TARGETS = [('GEOGRAPHIC', 'COUNTY'), ('GEOGRAPHIC', 'REGION'),
                ('RESTAURANT', 'NAME'), ('RESTAURANT', 'FOOD_TYPE'),
                ('RESTAURANT', 'CITY_NAME'), ('RESTAURANT', 'RATING'),
                ('LOCATION', 'HOUSE_NUMBER'), ('LOCATION', 'STREET_NAME'),
                ('LOCATION', 'CITY_NAME')]

DISTINCT_DUPLICATE_SHARE = {('GEOGRAPHIC', 'CITY_NAME'): 0.35}

TABLE_SIZES = {'GEOGRAPHIC': 20, 'RESTAURANT': 40, 'LOCATION': 40}

def _rating_ok(v):
    return v is None or (0.0 <= float(v) <= 5.0)


def _house_ok(v):
    return v is None or int(v) > 0


FORMULAS = {('RESTAURANT', 'RATING'): _rating_ok,
            ('LOCATION', 'HOUSE_NUMBER'): _house_ok}

DEFAULT_NULL_SHARE = 0.07
