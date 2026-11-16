"""Specification constants: per-domain ranges, value pools, and per-column targets."""
import json
import os

TABLE_SIZES = {'Manufacturers': 12, 'Products': 20}

RANGES = {
    ('Manufacturers', 'Revenue'): (0.0, 200.0, False, 1.0),
    ('Products', 'Price'): (0.0, 270.0, True, 1.0),
}

BOUNDARIES = {
    ('Manufacturers', 'Revenue'): [86.0, 87.0, 88.0, 89.0, 99.0, 100.0, 101.0, 149.0, 150.0, 151.0],
    ('Products', 'Price'): [59.0, 60.0, 61.0, 62.0, 119.0, 120.0, 121.0, 149.0, 150.0, 151.0],
}

VALUE_POOLS = {
    ('Manufacturers', 'Name'): ['Sony', 'Creative Labs', 'Hewlett-Packard', 'Iomega', 'Fujitsu', 'Winchester'],
    ('Manufacturers', 'Headquarter'): ['Tokyo', 'Austin', 'Los Angeles', 'Beijing', 'Taiwan', 'Paris'],
    ('Manufacturers', 'Founder'): ['Andy', 'Owen', 'James', 'Mary', 'John', 'Robert'],
    ('Products', 'Name'): ['Hard drive', 'Memory', 'ZIP drive', 'Floppy disk', 'Monitor', 'DVD drive',
                           'CD drive', 'Printer'],
}

LIKE_VARIANTS = {
    ('Manufacturers', 'Name'): ['Sony', 'Sonz', 'Sony x', 'sony', 'S', 'T', 'S x', 's'],
    ('Products', 'Name'): ['DVD drive', 'DVD drivf', 'DVD drive x', 'dvd drive', 'DVD', 'DVE', 'DVD x', 'dvd'],
}

FRESH_SHARE = (0.20, 0.50)

DISTINCT_COLUMNS = {
    ('Manufacturers', 'Code'), ('Manufacturers', 'Name'), ('Manufacturers', 'Founder'),
    ('Manufacturers', 'Headquarter'), ('Products', 'Manufacturer'),
}

NULLABLE = {('Manufacturers', 'Revenue')}

FK_KEYS = {('Products', 'Manufacturer'): ('Manufacturers', 'Code')}

TIE_MIN = 2
TIE_MAX = 2

FRESH_STRINGS = {
    ('Manufacturers', 'Name'): ['Sony', 'Sonz', 'Sony x', 'sony', 'S', 'T', 'S x', 's',
                                'Panasonic', 'Philips', 'Samsung', 'Toshiba'],
    ('Manufacturers', 'Founder'): ['Andy', 'Owen', 'James', 'Mary', 'John', 'Robert',
                                   'Alice', 'David', 'Susan', 'Peter'],
    ('Manufacturers', 'Headquarter'): ['Tokyo', 'Austin', 'Los Angeles', 'Beijing', 'Taiwan', 'Paris',
                                       'Seoul', 'Berlin', 'London', 'Osaka'],
    ('Products', 'Name'): ['Hard drive', 'Memory', 'ZIP drive', 'Floppy disk', 'Monitor', 'DVD drive',
                           'CD drive', 'Printer', 'DVD drivf', 'DVD drive x', 'dvd drive', 'DVD', 'DVE',
                           'DVD x', 'dvd', 'Keyboard', 'Mouse', 'Scanner'],
}


def load_specification():
    """Read tscore_gen/specification.json when present, else the built-in defaults."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = os.path.join(here, 'specification.json')
    if os.path.exists(spec):
        try:
            with open(spec) as f:
                return json.load(f)
        except Exception:
            pass
    return None
