"""Specification constants (value domains, ranges, NULL rule, per-column targets)."""
import datetime as dt

TABLE_SIZES = {
    'customers': 40,
    'geolocation': 3,
    'location': 3,
    'rootbeerbrand': 24,
    'rootbeer': 200,
    'rootbeerreview': 60,
    'transaction': 200,
}

FLAG = ('TRUE', 'FALSE')
GENDER = ('M', 'F')
CONTAINER = ('Bottle', 'Can')
CARD_TYPE = ('Discover', 'Visa', 'MasterCard', 'American Express')

RANGES = {
    ('customers', 'FirstPurchaseDate'): ('2012-01-01', '2014-12-31'),
    ('geolocation', 'Latitude'): (-90.0, 90.0),
    ('geolocation', 'Longitude'): (-180.0, 180.0),
    ('rootbeerbrand', 'FirstBrewedYear'): (1800, 2025),
    ('rootbeer', 'PurchaseDate'): ('2013-01-01', '2017-12-31'),
    ('rootbeerreview', 'StarRating'): (0, 6),
    ('rootbeerreview', 'ReviewDate'): ('2012-01-01', '2015-12-31'),
    ('transaction', 'TransactionDate'): ('2014-01-01', '2015-12-31'),
}

BOUNDARY = {
    ('rootbeerreview', 'StarRating'): [0, 1, 2, 3, 4, 5, 6],
    ('rootbeerreview', 'ReviewDate'): ['2012-10-31', '2012-11-01', '2012-11-02', '2012-11-29',
                                       '2012-11-30', '2012-12-01', '2013-12-31', '2014-01-01',
                                       '2014-12-31', '2015-01-01'],
    ('rootbeer', 'PurchaseDate'): ['2013-12-31', '2014-01-01', '2014-12-31', '2015-01-01',
                                   '2015-12-31', '2016-01-01', '2016-01-02', '2016-12-30',
                                   '2016-12-31', '2017-01-01'],
    ('rootbeerbrand', 'FirstBrewedYear'): [1929, 1930, 1931, 1999, 2000, 2001],
    ('customers', 'First'): ['Jayne', 'jayne', 'Anna', 'anna', 'Dawn', 'dawn'],
    ('customers', 'Last'): ['Collins', 'collins', 'Childress', 'childress', 'Ocel', 'ocel'],
    ('rootbeerbrand', 'BrandName'): ['River City', 'river city', 'A&W', 'a&w', 'Frostie', 'frostie'],
    ('location', 'LocationName'): ['Sac State Union', 'sac state union',
                                   'Sac State American River Courtyard',
                                   'sac state american river courtyard',
                                   'Sac State AmeriCourtyard', 'sac state americourtyard'],
}

LIKE_LITERALS = {
    ('rootbeerreview', 'ReviewDate'): ['2012-11%', '2014%', '2013%', '2012%', '2014-09%'],
    ('rootbeer', 'PurchaseDate'): ['2014%', '2016%'],
}

GROUP_SIZE_COLUMNS = [
    ('rootbeerbrand', 'BrandID'),
    ('rootbeerreview', 'BrandID'),
    ('rootbeerreview', 'CustomerID'),
    ('rootbeer', 'LocationID'),
    ('location', 'LocationName'),
    ('customers', 'CustomerID'),
]

DEFAULT_NULL_SHARE = 0.05

def parse_date(s):
    """Parse %Y-%m-%d (or a LIKE pattern without '%') into a date, else None."""
    if s is None:
        return None
    s = str(s).replace('%', '')
    try:
        return dt.datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def date_shift(s, days):
    """Shift a %Y-%m-%d string by days; returns the string or the input if unparsable."""
    d = parse_date(s)
    if d is None:
        return s
    return (d + dt.timedelta(days=days)).isoformat()
