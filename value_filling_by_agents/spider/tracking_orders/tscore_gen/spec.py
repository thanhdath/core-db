"""Specification loading and literal routing (by construction, never evaluated with SQL)."""
import json
import re

_EMBEDDED = {
    "table_sizes_per_instance": {"Customers": 15, "Invoices": 15, "Products": 15, "Orders": 15,
                                 "Order_Items": 15, "Shipments": 15, "Shipment_Items": 15},
    "null_targets": ["Customers.customer_name", "Customers.customer_details", "Invoices.invoice_date",
                     "Invoices.invoice_details", "Orders.order_details", "Products.product_name",
                     "Products.product_details", "Shipments.shipment_tracking_number",
                     "Shipments.shipment_date", "Shipments.other_shipment_details"],
    "enums": {"Orders.order_status": ["Shipped", "Packing", "On Road"],
              "Order_Items.order_item_status": ["Finish", "Payed", "Cancel"]},
    "enum_case_variants": {"Orders.order_status": ["On Road", "on road", "Shipped", "shipped"]},
    "date_ranges": {"Orders.date_order_placed": ["1970-01-01 00:00:00", "2015-12-31 23:59:59"],
                    "Invoices.invoice_date": ["1970-01-01 00:00:00", "2015-12-31 23:59:59"],
                    "Shipments.shipment_date": ["1970-01-01 00:00:00", "2015-12-31 23:59:59"]},
    "boundary_dates": {
        "Orders.date_order_placed": ["2008-12-31 00:00:00", "2009-01-01 00:00:00", "2009-01-02 00:00:00",
                                     "2009-12-31 00:00:00", "2010-01-01 00:00:00", "2010-01-02 00:00:00"],
        "Invoices.invoice_date": ["1989-09-02 00:00:00", "1989-09-03 00:00:00", "1989-09-04 00:00:00",
                                  "2007-12-24 00:00:00", "2007-12-25 00:00:00", "2007-12-26 00:00:00"],
    },
    "boundary_numbers": {"Products.product_id": [10, 11, 12],
                         "Order_Items.product_id": [10, 11, 12]},
    "boundary_strings": {"Shipments.shipment_tracking_number": ["3451", "3452", "3453", "3452", "3453"]},
    "literal_pool": {"Shipments.invoice_number": [10]},
    "group_sizes": {"Customers.customer_id": "1, 2 and >= 3",
                    "Customers.customer_name": "1, 2 and >= 3",
                    "Customers.customer_details": "1, 2 and >= 3",
                    "Orders.customer_id": "1, 2 and >= 3",
                    "Products.product_name": "1, 2 and >= 3"},
    "duplicate_share": {"Customers.customer_name": "20-50 %",
                        "Orders.order_id": "20-50 %",
                        "Orders.date_order_placed": "20-50 %",
                        "Order_Items.order_item_id": "20-50 %"},
    "tie_rank": {"Customers.customer_id": {"tie_at_rank": [1], "direction": "DESC",
                                           "tie_on": ["COUNT(orders.order_id)"]}},
    "unmatched_join_rows": {"Orders.order_id": ["Shipments.order_id", "Order_Items.order_id"],
                            "Products.product_id": ["Order_Items.product_id"],
                            "Order_Items.product_id": ["Products.product_id"],
                            "Order_Items.order_id": ["Orders.order_id"],
                            "Shipments.order_id": ["Orders.order_id"]},
    "soft_rules": [],
    "uncertainty": "shipment_date >= order_date is contradicted by the compact data and is not enforced.",
    "fresh_value_share": 0.3,
}


def load_specification(path):
    """Load the specification JSON, falling back to the embedded copy."""
    if path is None:
        return dict(_EMBEDDED)
    with open(path) as f:
        spec = json.load(f)
    merged = dict(_EMBEDDED)
    merged.update(spec or {})
    return merged


def _split_key(key: str):
    """'Table.column' -> (Table, column)."""
    if '.' in key:
        t, c = key.split('.', 1)
        return t, c
    return None, key


def spec_pool_values(spec: dict, schema) -> dict:
    """Route specification literals to (table, column) pools (typed by declared type)."""
    out: dict = {}

    def add(key, v):
        t, c = _split_key(key)
        if t is None:
            return
        if t not in schema.tables:
            return
        if not any(cm.name.lower() == c.lower() for cm in schema.tables[t].columns):
            return
        out.setdefault((t, c), []).append(str(v))

    for key, vals in (spec.get('boundary_dates') or {}).items():
        for v in vals:
            add(key, v)
    for key, vals in (spec.get('boundary_numbers') or {}).items():
        for v in vals:
            add(key, v)
    for key, vals in (spec.get('boundary_strings') or {}).items():
        for v in vals:
            add(key, v)
    for key, vals in (spec.get('literal_pool') or {}).items():
        for v in vals:
            add(key, v)
    for key, vals in (spec.get('enums') or {}).items():
        for v in vals:
            add(key, v)
    for key, vals in (spec.get('enum_case_variants') or {}).items():
        for v in vals:
            add(key, v)
    return out


def spec_for_column(spec: dict, table: str, column: str) -> dict:
    """Collect the per-column specification entries for (table, column)."""
    key = '%s.%s' % (table, column)
    out = {
        'enum': (spec.get('enums') or {}).get(key),
        'enum_case_variants': (spec.get('enum_case_variants') or {}).get(key),
        'date_range': (spec.get('date_ranges') or {}).get(key),
        'boundary_dates': (spec.get('boundary_dates') or {}).get(key),
        'boundary_numbers': (spec.get('boundary_numbers') or {}).get(key),
        'boundary_strings': (spec.get('boundary_strings') or {}).get(key),
        'literal_pool': (spec.get('literal_pool') or {}).get(key),
        'group_sizes': (spec.get('group_sizes') or {}).get(key),
        'duplicate_share': (spec.get('duplicate_share') or {}).get(key),
        'tie_rank': (spec.get('tie_rank') or {}).get(key),
        'unmatched_join_rows': (spec.get('unmatched_join_rows') or {}).get(key),
        'is_null_target': key in (spec.get('null_targets') or []),
    }
    return out


def parse_duplicate_share(text):
    """'20-50 %' -> (0.2, 0.5); None when absent."""
    if not text:
        return None
    m = re.search(r'(\d+)\s*-\s*(\d+)', str(text))
    if not m:
        return None
    return int(m.group(1)) / 100.0, int(m.group(2)) / 100.0
