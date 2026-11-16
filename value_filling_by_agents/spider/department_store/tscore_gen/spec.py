"""Specification handling: value domains, enum pools, NULL targets, table sizes."""

ENUMS = {
    ('Customer_Orders', 'order_status_code'): ['Completed', 'New', 'PartFilled', 'Pending', 'Cancelled'],
    ('Products', 'product_type_code'): ['Clothes', 'Hardware'],
    ('Staff', 'staff_gender'): ['0', '1'],
    ('Customers', 'payment_method_code'): ['Credit Card', 'Direct Debit'],
    ('Staff_Department_Assignments', 'job_title_code'):
        ['Department Manager', 'Sales Person', 'Clerical Staff', 'Administration'],
}

BOUNDARY = {
    ('Customers', 'payment_method_code'): ['Credit Card', 'credit card', '', 'x', 'Cr Card', 'cr card',
                                           'Direct Debit'],
    ('Customers', 'customer_id'): [9, 10, 11],
    ('Customer_Addresses', 'customer_id'): [9, 10, 11],
    ('Staff_Department_Assignments', 'job_title_code'):
        ['Clerical Staff', 'clerical staff', 'Sales Person', 'sales person', 'Clericf', 'clericf',
         'Department Manager', 'Administration'],
    ('Products', 'product_price'): [-0.01, 0, 0.01, 100, 500, 1000],
    ('Product_Suppliers', 'total_amount_purchased'): [29999, 30000, 30001, 79999, 80000, 80001],
}

AGG_BOUNDARY = {
    ('Product_Suppliers', 'total_amount_purchased'): [29999, 30000, 30001, 79999, 80000, 80001],
}

DUPLICATE_SHARE = {
    ('Products', 'product_name'): 0.35,
    ('Staff', 'staff_name'): 0.35,
    ('Department_Stores', 'dept_store_id'): 0.35,
}

NULL_TARGETS = [
    ('Staff_Department_Assignments', 'date_assigned_to'),
    ('Supplier_Addresses', 'date_to'),
    ('Customer_Addresses', 'date_to'),
    ('Product_Suppliers', 'date_supplied_to'),
    ('Product_Suppliers', 'total_amount_purchased'),
    ('Product_Suppliers', 'total_value_purchased'),
    ('Department_Stores', 'dept_store_chain_id'),
]

DATE_ORDER = [
    ('Staff_Department_Assignments', 'date_assigned_to', 'date_assigned_from'),
    ('Supplier_Addresses', 'date_to', 'date_from'),
    ('Customer_Addresses', 'date_to', 'date_from'),
    ('Product_Suppliers', 'date_supplied_to', 'date_supplied_from'),
]

NONNEG = [
    ('Products', 'product_price'),
    ('Product_Suppliers', 'total_value_purchased'),
]

TABLE_SIZES = {
    'Addresses': 15, 'Staff': 15, 'Suppliers': 4, 'Department_Store_Chain': 4, 'Customers': 15,
    'Products': 15, 'Supplier_Addresses': 4, 'Customer_Addresses': 15, 'Customer_Orders': 15,
    'Department_Stores': 15, 'Departments': 5, 'Order_Items': 15, 'Product_Suppliers': 15,
    'Staff_Department_Assignments': 15,
}

TIE_TARGETS = {
    ('Customer_Orders', 'customer_id'): 2,
    ('Staff_Department_Assignments', 'department_id'): 2,
    ('Staff_Department_Assignments', 'date_assigned_to'): 2,
    ('Staff_Department_Assignments', 'date_assigned_from'): 2,
}

AGG_COUNT_TARGETS = {
    ('Customer_Orders', 'customer_id'): [1, 2, 3],
    ('Order_Items', 'product_id'): [2, 3, 4],
    ('Products', 'product_id'): [2, 3, 4],
}


def load_specification(raw: dict) -> dict:
    """Merge a JSON specification with the built-in defaults (JSON wins)."""
    spec = {
        'enums': dict(ENUMS),
        'boundary': dict(BOUNDARY),
        'agg_boundary': dict(AGG_BOUNDARY),
        'duplicate_share': dict(DUPLICATE_SHARE),
        'null_targets': list(NULL_TARGETS),
        'date_order': list(DATE_ORDER),
        'nonneg': list(NONNEG),
        'table_sizes': dict(TABLE_SIZES),
        'tie_targets': dict(TIE_TARGETS),
        'agg_count_targets': dict(AGG_COUNT_TARGETS),
    }
    if not isinstance(raw, dict):
        return spec
    for key in ('enums', 'boundary', 'agg_boundary', 'duplicate_share', 'table_sizes',
                'tie_targets', 'agg_count_targets'):
        if isinstance(raw.get(key), dict):
            spec[key].update({_tuple_key(k): v for k, v in raw[key].items()})
    for key in ('null_targets', 'date_order', 'nonneg'):
        if isinstance(raw.get(key), list):
            spec[key] = [_tuple_key(x) for x in raw[key]]
    return spec


def _tuple_key(k):
    """'Table.col' or ['Table','col'] -> ('Table','col')."""
    if isinstance(k, (list, tuple)) and len(k) == 2:
        return (str(k[0]), str(k[1]))
    if isinstance(k, str) and '.' in k:
        a, b = k.split('.', 1)
        return (a, b)
    return k


def spec_from_schema(schema) -> dict:
    """Fallback specification derived from the compact schema (no JSON available)."""
    spec = {
        'enums': {}, 'boundary': {}, 'agg_boundary': {}, 'duplicate_share': {},
        'null_targets': [], 'date_order': [], 'nonneg': [], 'table_sizes': {},
        'tie_targets': {}, 'agg_count_targets': {},
    }
    for t, tm in schema.tables.items():
        spec['table_sizes'][t] = max(1, min(230, schema.original_sizes.get(t, 0) or 15))
        for c in tm.columns:
            key = (t, c.name)
            if not c.notnull and c.pk_pos == 0:
                spec['null_targets'].append(key)
            tl = (c.type_str or '').lower()
            if 'date' in tl or 'time' in tl:
                spec['date_order'].append(key)
            if any(k in tl for k in ('int', 'decimal', 'numeric', 'real', 'float')):
                spec['nonneg'].append(key)
    return spec
