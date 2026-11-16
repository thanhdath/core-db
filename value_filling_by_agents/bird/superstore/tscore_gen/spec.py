"""Specification model: value domains, enums, ranges, dependencies, NULL targets."""
import json
import os
import re

REGIONS = ['Central', 'East', 'South', 'West']
SEGMENTS = ['Consumer', 'Corporate', 'Home Office']
CATEGORIES = ['Furniture', 'Office Supplies', 'Technology']
SUB_CATEGORIES = ['Bookcases', 'Chairs', 'Furnishings', 'Tables', 'Appliances', 'Art', 'Binders',
                  'Envelopes', 'Labels', 'Paper', 'Storage', 'Supplies', 'Accessories', 'Copiers',
                  'Machines', 'Phones', 'Fasteners']
SHIP_MODES = ['Standard Class', 'First Class', 'Second Class', 'Same Day']
COUNTRIES = ['United States']
CITIES = ['Round Rock', 'Omaha', 'Springfield', 'Oklahoma City', 'Arlington', 'Greenwood',
          'Indianapolis', 'Tulsa', 'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix',
          'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville']
STATES = ['Texas', 'Nebraska', 'Missouri', 'Oklahoma', 'Indiana', 'Illinois', 'Minnesota',
          'Michigan', 'California', 'New York', 'Florida', 'Ohio', 'Georgia', 'Arizona',
          'Washington', 'Colorado', 'Virginia', 'Oregon', 'Nevada', 'Utah']
DISCOUNTS = [0.0, 0.1, 0.15, 0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8]

SUPERSTORE_REGION = {'central_superstore': 'Central', 'east_superstore': 'East',
                     'south_superstore': 'South', 'west_superstore': 'West'}

BOUNDARY = {
    ('product', 'Region'): ['Central', 'central', 'South', 'south', 'West', 'west', 'East', 'east'],
    ('central_superstore', 'Region'): ['Central', 'central'],
    ('south_superstore', 'Region'): ['South', 'south'],
    ('east_superstore', 'Region'): ['East', 'east'],
    ('west_superstore', 'Region'): ['West', 'west'],
    ('people', 'Region'): ['Central', 'central', 'South', 'south', 'West', 'west', 'East', 'east'],
    ('people', 'Segment'): ['Consumer', 'consumer', 'Corporate', 'Home Office'],
    ('west_superstore', 'Sales'): [4999.999, 5000, 5000.001],
    ('central_superstore', 'Discount'): [0, 0.01],
}
EXPR_BOUNDARY = {'east_superstore': [79999, 80000, 80001]}
TIES = {
    ('west_superstore', 'Quantity'): ([1], 'DESC'),
    ('central_superstore', 'Profit'): ([1], 'DESC'),
    ('central_superstore', 'Sales'): ([1, 10], 'DESC'),
}
DUP_SHARE = {('product', 'Category'): (0.2, 0.5)}

NULL_TARGETS = [
    'central_superstore.Order ID', 'central_superstore.Order Date', 'central_superstore.Ship Date',
    'central_superstore.Ship Mode', 'central_superstore.Customer ID', 'central_superstore.Region',
    'central_superstore.Product ID', 'central_superstore.Sales', 'central_superstore.Quantity',
    'central_superstore.Discount', 'central_superstore.Profit',
    'east_superstore.Order ID', 'east_superstore.Order Date', 'east_superstore.Ship Date',
    'east_superstore.Ship Mode', 'east_superstore.Customer ID', 'east_superstore.Region',
    'east_superstore.Product ID', 'east_superstore.Sales', 'east_superstore.Quantity',
    'east_superstore.Discount', 'east_superstore.Profit',
    'south_superstore.Order ID', 'south_superstore.Order Date', 'south_superstore.Ship Date',
    'south_superstore.Ship Mode', 'south_superstore.Customer ID', 'south_superstore.Region',
    'south_superstore.Product ID', 'south_superstore.Sales', 'south_superstore.Quantity',
    'south_superstore.Discount', 'south_superstore.Profit',
    'west_superstore.Order ID', 'west_superstore.Order Date', 'west_superstore.Ship Date',
    'west_superstore.Ship Mode', 'west_superstore.Customer ID', 'west_superstore.Region',
    'west_superstore.Product ID', 'west_superstore.Sales', 'west_superstore.Quantity',
    'west_superstore.Discount', 'west_superstore.Profit',
    'people.Customer Name', 'people.Segment', 'people.Country', 'people.City', 'people.State',
    'people.Postal Code', 'product.Product Name', 'product.Category', 'product.Sub-Category',
]

DEPENDENCIES = [
    ('central_superstore', 'Customer ID', 'people', 'Customer ID', ['Region']),
    ('central_superstore', 'Product ID', 'product', 'Product ID', ['Region']),
    ('east_superstore', 'Customer ID', 'people', 'Customer ID', ['Region']),
    ('east_superstore', 'Product ID', 'product', 'Product ID', ['Region']),
    ('south_superstore', 'Customer ID', 'people', 'Customer ID', ['Region']),
    ('south_superstore', 'Product ID', 'product', 'Product ID', ['Region']),
    ('west_superstore', 'Customer ID', 'people', 'Customer ID', ['Region']),
    ('west_superstore', 'Product ID', 'product', 'Product ID', ['Region']),
]

KEY_FORMATS = {
    'people': ('Customer ID', re.compile(r'^[A-Z]{2}-\d{5}$'), 'XX-NNNNN'),
    'product': ('Product ID', re.compile(r'^[A-Z]{3}-[A-Z]{2}-\d{8}$'), 'XXX-XX-NNNNNNNN'),
}

DEFAULT_SIZES = {'people': 200, 'product': 200, 'central_superstore': 200, 'east_superstore': 200,
                 'south_superstore': 200, 'west_superstore': 200}


def default_specification(db: str = '') -> dict:
    """Built-in specification (mirrors the generation specification JSON)."""
    return {
        'db': db,
        'tables': dict(DEFAULT_SIZES),
        'regions': list(REGIONS),
        'segments': list(SEGMENTS),
        'categories': list(CATEGORIES),
        'sub_categories': list(SUB_CATEGORIES),
        'ship_modes': list(SHIP_MODES),
        'countries': list(COUNTRIES),
        'cities': list(CITIES),
        'states': list(STATES),
        'discounts': list(DISCOUNTS),
        'superstore_region': dict(SUPERSTORE_REGION),
        'boundary': {('%s.%s' % k): v for k, v in BOUNDARY.items()},
        'expr_boundary': dict(EXPR_BOUNDARY),
        'ties': {('%s.%s' % k): v for k, v in TIES.items()},
        'dup_share': {('%s.%s' % k): v for k, v in DUP_SHARE.items()},
        'null_targets': list(NULL_TARGETS),
        'dependencies': [list(d) for d in DEPENDENCIES],
        'key_formats': {t: [v[0], v[2]] for t, v in KEY_FORMATS.items()},
        'null_share': 0.02,
        'date_range': ['2013-01-01', '2014-12-31'],
        'quantity_range': [1, 14],
        'postal_range': [10000, 99999],
        'sales_range': [0.0, 10000.0],
        'profit_range': [-5000.0, 5000.0],
    }


def spec_get(spec: dict, key: str, default):
    """Tolerant getter (specification JSON may omit keys)."""
    if not isinstance(spec, dict):
        return default
    v = spec.get(key, default)
    return default if v is None else v


def load_specification(path: str, db: str = '') -> dict:
    """Load the pipeline specification JSON; fall back to the built-in default."""
    base = default_specification(db)
    if not path or not os.path.exists(path):
        return base
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return base
    if not isinstance(data, dict):
        return base
    if 'tables' not in data:
        return base
    merged = dict(base)
    merged.update(data)
    return merged
