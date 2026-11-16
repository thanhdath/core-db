"""Static interpretation of the generation specification (tscore_gen/specification.json)."""
import json
import os

_DEFAULT_SIZES = {'geographic': 40, 'generalinfo': 200, 'location': 200}

FOOD_TYPES = ['american', 'mexican', 'italian', 'chinese', 'japanese', 'indian', 'thai', 'french',
              'greek', 'afghani', 'african', 'asian', 'arabic', 'armenian', 'european', 'diner',
              '24 hour diner', 'all ethnic', 'pizza', 'seafood', 'vegetarian', 'mediterranean',
              'korean', 'vietnamese', 'spanish', 'german', 'irish', 'hamburgers']
REGIONS = ['bay area', 'napa valley', 'unknown', 'monterey', 'los angeles area',
           'yosemite and mono lake area', 'sacramento area', 'northern california']
COUNTIES = ['alameda county', 'contra costa county', 'santa clara county', 'napa county',
            'santa cruz county', 'san mateo county', 'marin county', 'sonoma county',
            'solano county', 'san francisco county', 'san joaquin county', 'sacramento county']
CITIES = ['san francisco', 'san carlos', 'sunnyvale', 'san rafael', 'san jose', 'concord',
          'vacaville', 'cupertino', 'alameda', 'alamo', 'albany', 'alviso', 'american canyon',
          'angwin', 'antioch', 'aptos', 'berkeley', 'dublin', 'belmont', 'hayward', 'oakland',
          'fremont', 'milpitas', 'livermore', 'richmond', 'santa cruz']
STREETS = ['church st', 'el camino real', 'broadway', 'e. el camino real', 'w. el camino real',
           'san fernando', 'mt diablo st', 'alamo drive', '11th st', 'appian way', 'railroad',
           'alpine rd', 'main st', 'oak ave', 'pine st', 'market st', 'mission st', 'union st']
LABELS = ["sparky's diner", 'kabul afghan cuisine', 'helmand restaurant', 'afghani house',
          'bamyan afghan restaurant', 'kabul palace', 'kandahar', 'bakers square restaurant & pie shop',
          'baskin robbins', 'chevy\'s', 'denny\'s', 'ihop', 'olive garden', 'red robin',
          'panda express', 'subway', 'starbucks', 'taco bell', 'the cheesecake factory']

_BOUNDARY = {
    ('geographic', 'city'): ['san francisco', 'SAN FRANCISCO', 'dublin', 'DUBLIN', 'belmont',
                             'BELMONT', 'berkeley', 'BERKELEY'],
    ('generalinfo', 'city'): ['san francisco', 'SAN FRANCISCO', 'santa cruz', 'SANTA CRUZ',
                              'hayward', 'HAYWARD', 'dublin', 'DUBLIN'],
    ('location', 'city'): ['san francisco', 'SAN FRANCISCO', 'santa cruz', 'SANTA CRUZ',
                           'hayward', 'HAYWARD', 'oakland', 'OAKLAND'],
    ('generalinfo', 'food_type'): ['american food', 'AMERICAN FOOD', 'african', 'AFRICAN',
                                   'asian', 'ASIAN', 'mexican', 'MEXICAN'],
    ('geographic', 'region'): ['Napa Valley', 'napa valley', ' Va', ' va', 'NValley', 'nvalley',
                               'Napa Vally', 'napa vally'],
    ('location', 'street_name'): ['11th st', '11TH ST', 'appian way', 'APPIAN WAY', 'railroad',
                                  'RAILROAD', 'alpine rd', 'ALPINE RD'],
    ('generalinfo', 'label'): ['bakers square restaurant & pie shop',
                               'BAKERS SQUARE RESTAURANT & PIE SHOP', 'akers sq', 'AKERS SQ',
                               'bakers square restauant & pie shop',
                               'BAKERS SQUARE RESTAUANT & PIE SHOP', 'e restaurant & ',
                               'E RESTAURANT & '],
    ('geographic', 'county'): ['san mateo county', 'SAN MATEO COUNTY', 'contra costa county',
                               'CONTRA COSTA COUNTY'],
}
_BOUNDARY_NUM = {
    ('generalinfo', 'id_restaurant'): [384, 385, 386],
    ('location', 'id_restaurant'): [384, 385, 386],
    ('location', 'street_num'): [999, 1000, 1001, 1999, 2000, 2001],
}

_SEMANTIC = {
    ('geographic', 'city'): 'not_null',
    ('generalinfo', 'id_restaurant'): 'pk_positive',
    ('generalinfo', 'review'): 'range',
    ('location', 'id_restaurant'): 'fk_positive',
    ('location', 'street_num'): 'integer_range',
}

_NULL_SHARE = {
    ('generalinfo', 'review'): 0.02,
    ('location', 'city'): 0.15,
    ('location', 'street_name'): 0.02,
    ('location', 'street_num'): 0.048,
    ('geographic', 'county'): 0.02,
    ('geographic', 'region'): 0.02,
    ('generalinfo', 'label'): 0.02,
    ('generalinfo', 'food_type'): 0.02,
    ('generalinfo', 'city'): 0.02,
}

_DUPS = {('generalinfo', 'label'), ('location', 'street_name')}

_TIES = {
    ('generalinfo', 'food_type'): 2,
    ('geographic', 'region'): 2,
    ('location', 'street_name'): 2,
    ('geographic', 'county'): 2,
}


def _load(root_dir):
    data = {}
    if root_dir:
        p = os.path.join(root_dir, 'specification.json')
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json.load(f)
            except Exception:
                data = {}
    return data


def get_spec():
    """Return a dict with sizes, boundary literals, null shares, formulas, ties."""
    data = _load(os.environ.get('TSCORE_SPEC_DIR'))
    sizes = dict(_DEFAULT_SIZES)
    for k, v in (data.get('table_sizes_per_instance') or {}).items():
        if isinstance(v, int) and v >= 0:
            sizes[k] = v
    boundary = dict(_BOUNDARY)
    boundary_num = dict(_BOUNDARY_NUM)
    for ex in (data.get('per_column_exceptions') or []):
        col = ex.get('column', '')
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        tgt = ex.get('targets')
        if ex.get('pattern') == 'comparison_boundary' and isinstance(tgt, list):
            if all(isinstance(x, int) for x in tgt):
                boundary_num[(t, c)] = list(tgt)
            elif all(isinstance(x, str) for x in tgt):
                boundary[(t, c)] = list(tgt)
    formulas = {}
    for r in (data.get('semantic_rules_and_formulas') or []):
        t = r.get('table')
        c = r.get('column')
        f = r.get('formula', '')
        if t and c:
            if 'NOT NULL' in f.upper():
                formulas[(t, c)] = 'not_null'
            elif 'BETWEEN 1.0 AND 5.0' in f:
                formulas[(t, c)] = 'range_review'
            elif 'BETWEEN 1 AND 9999' in f:
                formulas[(t, c)] = 'integer_range'
            elif '> 0' in f:
                formulas[(t, c)] = 'positive'
    if not formulas:
        formulas = dict(_SEMANTIC)
    return {'sizes': sizes, 'boundary': boundary, 'boundary_num': boundary_num,
            'formulas': formulas, 'null_share': dict(_NULL_SHARE), 'dups': set(_DUPS),
            'ties': dict(_TIES)}
