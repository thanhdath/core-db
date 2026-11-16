"""Specification model: value domains, ranges, enums, dependencies, semantic rules."""
import re

REGION_ENUM = ['Northeast', 'Midwest', 'South', 'West']
SALES_CHANNEL_ENUM = ['In-Store', 'Online', 'Distributor', 'Wholesale']
STORE_TYPE_ENUM = ['City', 'Town', 'CDP', 'Unified Government', 'Consolidated Government',
                   'Other', 'Township', 'Urban County']
TIME_ZONE_ENUM = ['America/Chicago', 'America/Phoenix', 'America/Los Angeles', 'America/Denver',
                  'America/New York', 'Pacific/Honolulu', 'America/Boise', 'America/Indiana/Indianapolis']
DISCOUNT_ENUM = [0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4]
QUANTITY_ENUM = [1, 2, 3, 4, 5, 6, 7, 8]
WAREHOUSE_ENUM = ['WARE-UHY1004', 'WARE-NMK1003', 'WARE-PUJ1005', 'WARE-XYS1001',
                  'WARE-MKL1006', 'WARE-NBV1002']
CURRENCY_ENUM = ['USD']

BOUNDARY_LITERALS = {
    ('Regions', 'Region'): ['Midwest', 'South', 'West', 'midwest', 'south', 'west'],
    ('Regions', 'State'): ['California', 'Michigan', 'Arizona', 'california', 'michigan', 'arizona'],
    ('Regions', 'StateCode'): ['GA', 'ga'],
    ('Products', 'ProductID'): [29, 30, 31, 39, 40, 41],
}

ENUMS = {
    ('Regions', 'Region'): REGION_ENUM,
    ('Sales Team', 'Region'): REGION_ENUM,
    ('Sales Orders', 'Sales Channel'): SALES_CHANNEL_ENUM,
    ('Sales Orders', 'CurrencyCode'): CURRENCY_ENUM,
    ('Sales Orders', 'WarehouseCode'): WAREHOUSE_ENUM,
    ('Sales Orders', 'Discount Applied'): DISCOUNT_ENUM,
    ('Sales Orders', 'Order Quantity'): QUANTITY_ENUM,
    ('Store Locations', 'Type'): STORE_TYPE_ENUM,
    ('Store Locations', 'Time Zone'): TIME_ZONE_ENUM,
}

RANGES = {
    ('Store Locations', 'Latitude'): (-90.0, 90.0, False),
    ('Store Locations', 'Longitude'): (-180.0, 180.0, False),
    ('Store Locations', 'Population'): (0, 5_000_000, True),
    ('Store Locations', 'Household Income'): (0, 250_000, True),
    ('Store Locations', 'Median Income'): (0, 250_000, True),
    ('Store Locations', 'Land Area'): (0, 1_000_000_000, True),
    ('Store Locations', 'Water Area'): (0, 1_000_000_000, True),
    ('Store Locations', 'AreaCode'): (200, 999, True),
}

MONEY_COLUMNS = {('Sales Orders', 'Unit Price'), ('Sales Orders', 'Unit Cost')}

DATE_COLUMNS = {('Sales Orders', 'ProcuredDate'), ('Sales Orders', 'OrderDate'),
                ('Sales Orders', 'ShipDate'), ('Sales Orders', 'DeliveryDate')}

NULL_TARGETS = [('Sales Orders', '_SalesTeamID'), ('Sales Orders', '_CustomerID'),
                ('Sales Orders', '_StoreID'), ('Sales Orders', '_ProductID'),
                ('Store Locations', 'StateCode')]

DISTINCT_TARGETS = [('Regions', 'Region'), ('Regions', 'State')]

TIE_TARGETS = [('Store Locations', 'Population'), ('Store Locations', 'Water Area'),
               ('Sales Orders', 'Discount Applied'), ('Sales Orders', 'Unit Price'),
               ('Sales Orders', 'Unit Cost')]

GROUP_SIZE_TARGETS = [('Customers', 'CustomerID')]

AGGREGATE_BOUNDARY = {('Customers', 'CustomerID'): [2, 3, 4]}

TABLE_SIZES = {'Customers': 50, 'Products': 47, 'Regions': 48, 'Sales Team': 28,
               'Store Locations': 120, 'Sales Orders': 400}

DEPENDENCIES = [
    ('Store Locations', 'StateCode', 'Regions', 'StateCode', ['State']),
    ('Sales Orders', '_SalesTeamID', 'Sales Team', 'SalesTeamID', []),
    ('Sales Orders', '_CustomerID', 'Customers', 'CustomerID', []),
    ('Sales Orders', '_StoreID', 'Store Locations', 'StoreID', []),
    ('Sales Orders', '_ProductID', 'Products', 'ProductID', []),
]

UNMATCHED_JOINS = [
    ('Store Locations', 'StateCode', 'Regions', 'StateCode'),
    ('Sales Orders', '_SalesTeamID', 'Sales Team', 'SalesTeamID'),
    ('Sales Orders', '_CustomerID', 'Customers', 'CustomerID'),
    ('Sales Orders', '_StoreID', 'Store Locations', 'StoreID'),
    ('Sales Orders', '_ProductID', 'Products', 'ProductID'),
]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _rule_region(r):
    v = r.get('Region')
    return v is None or v in REGION_ENUM


def _rule_statecode(r):
    v = r.get('StateCode')
    return v is None or len(str(v)) == 2


def _rule_channel(r):
    v = r.get('Sales Channel')
    return v is None or v in SALES_CHANNEL_ENUM


def _rule_currency(r):
    v = r.get('CurrencyCode')
    return v is None or v == 'USD'


def _rule_quantity(r):
    v = r.get('Order Quantity')
    if v is None:
        return True
    n = _num(v)
    return n is not None and n > 0


def _rule_discount(r):
    v = r.get('Discount Applied')
    if v is None:
        return True
    n = _num(v)
    return n is not None and 0 <= n <= 1


def _money_ge0(v):
    if v is None:
        return True
    try:
        return float(str(v).replace(',', '')) >= 0
    except (TypeError, ValueError):
        return False


def _rule_unit_price(r):
    return _money_ge0(r.get('Unit Price'))


def _rule_unit_cost(r):
    return _money_ge0(r.get('Unit Cost'))


def _rule_type(r):
    v = r.get('Type')
    return v is None or v in STORE_TYPE_ENUM


def _rule_lat(r):
    v = r.get('Latitude')
    n = _num(v)
    return v is None or (n is not None and -90 <= n <= 90)


def _rule_lon(r):
    v = r.get('Longitude')
    n = _num(v)
    return v is None or (n is not None and -180 <= n <= 180)


def _rule_nonneg(col):
    def f(r):
        v = r.get(col)
        if v is None:
            return True
        n = _num(v)
        return n is not None and n >= 0
    return f


def _date_key(s):
    """M/D/YY -> (yy, m, d) tuple for ordering; tolerant of odd strings."""
    m = re.match(r'^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$', str(s))
    if not m:
        return (0, 0, 0)
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    return (y, mo, d)


def _rule_ship_ge_order(r):
    o, s = r.get('OrderDate'), r.get('ShipDate')
    if o is None or s is None:
        return True
    return _date_key(s) >= _date_key(o)


def _rule_delivery_ge_ship(r):
    s, d = r.get('ShipDate'), r.get('DeliveryDate')
    if s is None or d is None:
        return True
    return _date_key(d) >= _date_key(s)


RULES = {
    ('Regions', 'Region'): _rule_region,
    ('Regions', 'StateCode'): _rule_statecode,
    ('Sales Team', 'Region'): _rule_region,
    ('Sales Orders', 'Sales Channel'): _rule_channel,
    ('Sales Orders', 'CurrencyCode'): _rule_currency,
    ('Sales Orders', 'Order Quantity'): _rule_quantity,
    ('Sales Orders', 'Discount Applied'): _rule_discount,
    ('Sales Orders', 'Unit Price'): _rule_unit_price,
    ('Sales Orders', 'Unit Cost'): _rule_unit_cost,
    ('Sales Orders', 'ShipDate'): _rule_ship_ge_order,
    ('Sales Orders', 'DeliveryDate'): _rule_delivery_ge_ship,
    ('Store Locations', 'Type'): _rule_type,
    ('Store Locations', 'Latitude'): _rule_lat,
    ('Store Locations', 'Longitude'): _rule_lon,
    ('Store Locations', 'Population'): _rule_nonneg('Population'),
    ('Store Locations', 'Household Income'): _rule_nonneg('Household Income'),
    ('Store Locations', 'Median Income'): _rule_nonneg('Median Income'),
    ('Store Locations', 'Land Area'): _rule_nonneg('Land Area'),
    ('Store Locations', 'Water Area'): _rule_nonneg('Water Area'),
}


def load_specification(raw: dict) -> dict:
    """Merge a JSON specification (if any) over the built-in defaults."""
    spec = default_specification()
    if not isinstance(raw, dict):
        return spec
    for k in ('table_sizes_per_instance', 'table_sizes'):
        if isinstance(raw.get(k), dict):
            spec['table_sizes'].update({str(a): int(b) for a, b in raw[k].items()})
    return spec


def default_specification() -> dict:
    """Built-in specification (mirrors the generation spec)."""
    return {
        'table_sizes': dict(TABLE_SIZES),
        'enums': dict(ENUMS),
        'ranges': dict(RANGES),
        'money_columns': set(MONEY_COLUMNS),
        'date_columns': set(DATE_COLUMNS),
        'null_targets': list(NULL_TARGETS),
        'distinct_targets': list(DISTINCT_TARGETS),
        'tie_targets': list(TIE_TARGETS),
        'group_size_targets': list(GROUP_SIZE_TARGETS),
        'aggregate_boundary': dict(AGGREGATE_BOUNDARY),
        'boundary_literals': dict(BOUNDARY_LITERALS),
        'dependencies': list(DEPENDENCIES),
        'unmatched_joins': list(UNMATCHED_JOINS),
        'rules': dict(RULES),
    }
