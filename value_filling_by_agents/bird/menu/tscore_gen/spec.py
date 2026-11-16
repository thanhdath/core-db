"""The generation specification, encoded as data (no SQL is ever evaluated)."""
import datetime as dt

TABLE_SIZES = {'Dish': 200, 'Menu': 120, 'MenuPage': 180, 'MenuItem': 400}

NULL_SHARE = {
    ('Dish', 'description'): 1.0,
    ('Dish', 'lowest_price'): 0.069,
    ('Dish', 'highest_price'): 0.069,
    ('Menu', 'name'): 0.357,
    ('Menu', 'sponsor'): 0.089,
    ('Menu', 'event'): 0.507,
    ('Menu', 'venue'): 0.518,
    ('Menu', 'place'): 0.518,
    ('Menu', 'physical_description'): 0.093,
    ('Menu', 'occasion'): 0.518,
    ('Menu', 'notes'): 0.093,
    ('Menu', 'call_number'): 0.089,
    ('Menu', 'keywords'): 1.0,
    ('Menu', 'language'): 1.0,
    ('Menu', 'date'): 0.033,
    ('Menu', 'location_type'): 1.0,
    ('Menu', 'currency'): 0.632,
    ('Menu', 'currency_symbol'): 0.632,
    ('MenuPage', 'page_number'): 0.018,
    ('MenuPage', 'full_height'): 0.005,
    ('MenuPage', 'full_width'): 0.005,
    ('MenuItem', 'price'): 0.335,
    ('MenuItem', 'high_price'): 0.931,
}

NULL_TARGETS = set(NULL_SHARE.keys())

NULL_DOMINANT = {('Dish', 'description'), ('Menu', 'keywords'), ('Menu', 'language'),
                 ('Menu', 'location_type')}
NULL_DOMINANT_NONNULL_SHARE = 0.02

BOUNDARY = {
    ('Dish', 'name'): ['Clear green turtle', 'clear green turtle', 'Anchovies', 'anchovies',
                       'Fresh lobsters in every style', 'fresh lobsters in every style'],
    ('Dish', 'first_appeared'): [1849, 1850, 1851, 2011, 2012, 2013],
    ('Dish', 'last_appeared'): [1849, 1850, 1851, 2011, 2012, 2013],
    ('Dish', 'id'): [106, 107, 108],
    ('Menu', 'id'): [12463, 12464, 12465, 12881, 12882, 12883],
    ('Menu', 'name'): ['Ritz Carlton', 'ritz carlton', 'Zentral Theater Terrace',
                       'zentral theater terrace', "Young's Hotel", "young's hotel"],
    ('Menu', 'date'): ['1949-12-31', '1950-01-01', '1950-01-02', '1950-12-31', '1951-01-01'],
    ('MenuPage', 'id'): [143, 144, 145, 1388, 1389, 1390],
    ('MenuPage', 'menu_id'): [12881, 12882, 12883],
    ('MenuPage', 'page_number'): [0, 1, 2],
    ('MenuPage', 'uuid'): ['510d47e4-295a-a3d9-e040-e00a18064a99',
                           '510D47E4-295A-A3D9-E040-E00A18064A99',
                           '510d47e4-2958-a3d9-e040-e00a18064a99',
                           '510D47E4-2958-A3D9-E040-E00A18064A99',
                           'c02c9a3b-6881-7080-e040-e00a180631aa',
                           'C02C9A3B-6881-7080-E040-E00A180631AA'],
    ('MenuItem', 'menu_page_id'): [143, 144, 145, 1388, 1389, 1390],
}

PK_FK_BOUNDARY_HONOURED_BY_COMPACT = {
    ('Dish', 'id'), ('Menu', 'id'), ('MenuPage', 'id'),
    ('MenuPage', 'menu_id'), ('MenuItem', 'menu_page_id'), ('MenuItem', 'dish_id'),
}

DUPLICATE_COLUMNS = {('Dish', 'name')}
DUPLICATE_SHARE = 0.30

TIE_COLUMNS = {('MenuItem', 'price')}

GROUP_DISTINCT = {('MenuItem', 'menu_page_id', 'price')}

YEAR_LO, YEAR_HI = 1800, 2030
DATE_LO, DATE_HI = dt.date(1850, 1, 1), dt.date(2015, 12, 31)
TS_LO, TS_HI = dt.datetime(2011, 1, 1), dt.datetime(2012, 12, 31)
PRICE_LO, PRICE_HI = 0.0, 100.0
QUANTITY_LO, QUANTITY_HI = 1, 500

ENUMS = {
    ('Menu', 'status'): ['complete'],
    ('Menu', 'currency'): ['Dollars', 'Cents', 'Francs', 'Belgian Francs', 'Shillings',
                           'Deutsche Marks', 'UK Pounds', 'Pence'],
    ('Menu', 'currency_symbol'): ['$', 'c', 'FF', 'BEF', 's', 'DM', '\u00a3', 'p'],
    ('Menu', 'event'): ['BREAKFAST', '[DINNER]', 'FRUHSTUCK/BREAKFAST;', 'LUNCH;', 'DINNER;',
                        'SUPPER', 'FRUHSTUCK/BREAKFAST', 'LUNCH'],
    ('Menu', 'venue'): ['COMMERCIAL', '', 'SOC;', 'EDUC;', 'MIL;', 'GOVT;', 'POL;', '?'],
    ('Menu', 'occasion'): ['EASTER;', '', 'ANNIVERSARY;', 'DAILY;', 'DAILY',
                           'OTHER (COMPLIMENTARY);', 'OTHER (DAILY);', 'COMPLIMENTARY/TESTIMONIAL'],
}

def _f_dish_id(r):
    return r['id'] > 0


def _f_nonneg(col):
    return lambda r: r[col] is None or r[col] >= 0


def _f_year(col):
    return lambda r: r[col] is None or YEAR_LO <= r[col] <= YEAR_HI


def _f_last_ge_first(r):
    a, b = r['first_appeared'], r['last_appeared']
    return a is None or b is None or b >= a


def _f_high_ge_low(r):
    a, b = r['lowest_price'], r['highest_price']
    return a is None or b is None or b >= a


def _f_status(r):
    return r['status'] is None or r['status'] in ('complete',)


def _f_page_count(r):
    return r['page_count'] is None or r['page_count'] > 0


def _f_date(r):
    d = r['date']
    if d is None:
        return True
    try:
        x = dt.date.fromisoformat(str(d)[:10])
    except ValueError:
        return False
    return DATE_LO <= x <= DATE_HI


def _f_page_number(r):
    return r['page_number'] is None or r['page_number'] >= 0


def _f_pos(col):
    return lambda r: r[col] is None or r[col] > 0


def _f_high_ge_price(r):
    a, b = r['price'], r['high_price']
    return a is None or b is None or b >= a


def _f_unit(col):
    return lambda r: r[col] is None or 0.0 <= r[col] <= 1.0


FORMULAS = {
    'Dish': [_f_dish_id, _f_nonneg('menus_appeared'), _f_nonneg('times_appeared'),
             _f_year('first_appeared'), _f_year('last_appeared'), _f_last_ge_first,
             _f_nonneg('lowest_price'), _f_nonneg('highest_price'), _f_high_ge_low],
    'Menu': [_f_dish_id, _f_status, _f_page_count, _f_nonneg('dish_count'), _f_date],
    'MenuPage': [_f_dish_id, _f_page_number, _f_pos('full_height'), _f_pos('full_width')],
    'MenuItem': [_f_dish_id, _f_nonneg('price'), _f_nonneg('high_price'), _f_high_ge_price,
                 _f_unit('xpos'), _f_unit('ypos')],
}

DEPENDENCIES = {
    ('MenuPage', 'menu_id'): ('Menu', 'id'),
    ('MenuItem', 'menu_page_id'): ('MenuPage', 'id'),
    ('MenuItem', 'dish_id'): ('Dish', 'id'),
}

PARENT_WITHOUT_CHILDREN = {'Dish', 'Menu', 'MenuPage'}
NULL_FK = {('MenuItem', 'menu_page_id'), ('MenuItem', 'dish_id')}

GROUP_SIZE_TARGETS = {'Menu': ('MenuPage', 'menu_id'), 'MenuPage': ('MenuItem', 'menu_page_id')}
