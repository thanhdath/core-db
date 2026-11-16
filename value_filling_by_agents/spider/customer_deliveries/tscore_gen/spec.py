"""Specification model: value domains, enumerations, NULL targets, dependencies, formulas."""
import datetime as dt
import re

DEFAULT_ENUMS = {
    ('Customers', 'payment_method'): ['Visa', 'MasterCard', 'Discover', 'American'],
    ('Actual_Orders', 'order_status_code'): ['Success', 'Cancel', 'success'],
    ('Customer_Addresses', 'address_type'): ['House', 'Flat', 'Apartment'],
    ('Order_Deliveries', 'delivery_status_code'): ['Ready', 'On Road', 'Delivered'],
    ('Products', 'product_description'): ['good condition', 'great condition', 'bad condition'],
}

DEFAULT_NULL_TARGETS = [
    'Addresses.address_details', 'Addresses.city', 'Addresses.zip_postcode',
    'Addresses.state_province_county', 'Addresses.country', 'Customers.customer_name',
    'Customers.customer_phone', 'Customers.customer_email', 'Customers.date_became_customer',
    'Customer_Addresses.date_to', 'Delivery_Route_Locations.location_name',
    'Delivery_Routes.route_name', 'Delivery_Routes.other_route_details',
    'Employees.employee_name', 'Employees.employee_phone', 'Order_Deliveries.delivery_date',
    'Products.product_name', 'Products.product_price', 'Products.product_description',
    'Trucks.truck_licence_number', 'Trucks.truck_details', 'Actual_Orders.actual_order_date',
]

DEFAULT_SIZES = {
    'Products': 6, 'Addresses': 15, 'Customers': 15, 'Regular_Orders': 15,
    'Regular_Order_Products': 15, 'Actual_Orders': 15, 'Actual_Order_Products': 15,
    'Customer_Addresses': 15, 'Delivery_Routes': 15, 'Delivery_Route_Locations': 15,
    'Trucks': 15, 'Employees': 15, 'Order_Deliveries': 15,
}

DEFAULT_PATTERNS = {
    ('Addresses', 'state_province_county'): ['duplicates_for_distinct', 'group_sizes'],
    ('Addresses', 'address_details'): ['group_sizes'],
    ('Addresses', 'address_id'): ['group_sizes'],
    ('Products', 'product_price'): ['rows_with_different_values'],
    ('Customers', 'customer_id'): ['unmatched_join_rows'],
    ('Customer_Addresses', 'customer_id'): ['unmatched_join_rows'],
    ('Customers', 'payment_method'): ['group_sizes', 'null_rows'],
    ('Actual_Order_Products', 'product_id'): ['unmatched_join_rows'],
    ('Actual_Orders', 'actual_order_id'): ['duplicates_for_distinct'],
    ('Actual_Orders', 'order_status_code'): ['comparison_boundary'],
    ('Customers', 'date_became_customer'): ['group_sizes'],
    ('Employees', 'employee_id'): ['null_rows'],
    ('Products', 'product_id'): ['unmatched_join_rows'],
    ('Regular_Orders', 'distributer_id'): ['unmatched_join_rows'],
}

DEFAULT_BOUNDARY = {
    ('Actual_Orders', 'order_status_code'): ['Success', 'success'],
}

def _f_price_ge0(row, ctx):
    v = row.get('product_price')
    return v is None or v >= 0


def _f_enum(col, vals):
    def f(row, ctx):
        v = row.get(col)
        return v is None or v in vals
    return f


def _f_date_to_ge_from(row, ctx):
    a, b = row.get('date_from'), row.get('date_to')
    return b is None or a is None or b >= a


def _f_date_ge_min(col, lo):
    def f(row, ctx):
        v = row.get(col)
        return v is None or v >= lo
    return f


_MIN_TS = '2009-01-01 00:00:00'

DEFAULT_FORMULAS = {
    ('Products', 'product_price'): _f_price_ge0,
    ('Customers', 'payment_method'): _f_enum('payment_method', DEFAULT_ENUMS[('Customers', 'payment_method')]),
    ('Actual_Orders', 'order_status_code'): _f_enum('order_status_code', DEFAULT_ENUMS[('Actual_Orders', 'order_status_code')]),
    ('Customer_Addresses', 'address_type'): _f_enum('address_type', DEFAULT_ENUMS[('Customer_Addresses', 'address_type')]),
    ('Order_Deliveries', 'delivery_status_code'): _f_enum('delivery_status_code', DEFAULT_ENUMS[('Order_Deliveries', 'delivery_status_code')]),
    ('Products', 'product_description'): _f_enum('product_description', DEFAULT_ENUMS[('Products', 'product_description')]),
    ('Customer_Addresses', 'date_to'): _f_date_to_ge_from,
    ('Actual_Orders', 'actual_order_date'): _f_date_ge_min('actual_order_date', _MIN_TS),
    ('Order_Deliveries', 'delivery_date'): _f_date_ge_min('delivery_date', _MIN_TS),
}


def _split_col(s: str):
    t, c = s.split('.', 1)
    return (t, c)


def default_specification() -> dict:
    """Built-in specification (mirrors the generation specification JSON)."""
    return {
        'enums': dict(DEFAULT_ENUMS),
        'null_targets': set(DEFAULT_NULL_TARGETS),
        'sizes': dict(DEFAULT_SIZES),
        'patterns': dict(DEFAULT_PATTERNS),
        'boundary': dict(DEFAULT_BOUNDARY),
        'formulas': dict(DEFAULT_FORMULAS),
        'dependencies': {},
        'date_format': '%Y-%m-%d %H:%M:%S',
        'date_min': '2009-01-01 00:00:00',
        'date_max': '2018-12-31 23:59:59',
    }


def load_specification(raw: dict) -> dict:
    """Translate the pipeline's specification.json into the internal model."""
    spec = default_specification()
    if not isinstance(raw, dict):
        return spec
    enums = {}
    for e in raw.get('per_column_exceptions', []) or []:
        if e.get('pattern') == 'enum':
            enums[_split_col(e['column'])] = list(e.get('targets', {}).get('values', []))
    if enums:
        spec['enums'] = enums
        for (t, c), vals in enums.items():
            spec['formulas'][(t, c)] = _f_enum(c, vals)
    nt = raw.get('null_targets')
    if isinstance(nt, list):
        spec['null_targets'] = {_split_col(x) for x in nt}
    sizes = raw.get('table_sizes_per_instance')
    if isinstance(sizes, dict) and sizes:
        spec['sizes'] = {k: int(v) for k, v in sizes.items()}
    pats = {}
    bnd = {}
    for e in raw.get('per_column_exceptions', []) or []:
        key = _split_col(e['column'])
        pats.setdefault(key, []).append(e.get('pattern'))
        if e.get('pattern') == 'comparison_boundary':
            bnd[key] = list(e.get('targets', {}).get('values', []))
    if pats:
        spec['patterns'] = pats
    if bnd:
        spec['boundary'] = bnd
    deps = {}
    for d in raw.get('dependencies', []) or []:
        deps[_split_col(d['child'])] = _split_col(d['parent'])
    if deps:
        spec['dependencies'] = deps
    return spec


def parse_ts(s: str):
    """Parse a '%Y-%m-%d %H:%M:%S' timestamp (tolerant of date-only)."""
    if s is None:
        return None
    if isinstance(s, dt.datetime):
        return s
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def fmt_ts(d: dt.datetime) -> str:
    return d.strftime('%Y-%m-%d %H:%M:%S')


def has_pattern(spec: dict, table: str, column: str, name: str) -> bool:
    return name in (spec.get('patterns', {}).get((table, column)) or [])


def enum_values(spec: dict, table: str, column: str):
    return spec.get('enums', {}).get((table, column))


def is_null_target(spec: dict, table: str, column: str) -> bool:
    return (table, column) in spec.get('null_targets', set())


def formula_for(spec: dict, table: str, column: str):
    return spec.get('formulas', {}).get((table, column))


def boundary_variants(spec: dict, table: str, column: str) -> list:
    """Listed boundary literals plus a lexicographically smaller and a strictly greater string variant (for strings)
    so that both `>= c` and `= c` separate."""
    vals = list(spec.get('boundary', {}).get((table, column)) or [])
    out = list(vals)
    for v in vals:
        if isinstance(v, str) and v:
            lo = v[:-1] if len(v) > 1 else 'A' + v
            hi = v + 'z'
            out.extend([lo, hi])
    return out


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(s).lower())
