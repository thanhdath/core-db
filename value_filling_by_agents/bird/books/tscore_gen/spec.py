"""Specification loading and per-column construction rules."""
import json
import os

_DEFAULT = {
    "generic_sampling_rules": {
        "integer_pk": "Sequential from 1; never NULL; unique per table.",
        "integer_fk": "Copy from parent pool; 5% NULL when nullable; 10% parent rows left childless.",
        "text_short": "Draw from a small pool of realistic values; 20-50% duplicate share; 5% near-variant.",
        "text_long": "Draw from a pool of realistic titles/names; 20-50% duplicate share; 5% near-variant.",
        "date": "Uniform over 1800-01-01..2025-12-31; format %Y-%m-%d; 5% boundary values at year edges.",
        "datetime": "Uniform over 2019-01-01..2023-12-31; format %Y-%m-%d %H:%M:%S; 5% boundary values.",
        "real_price": "Uniform 0.50..50.00, 2 decimals; 5% boundary at 9.99/10.00/10.01/12.99/13.00/13.01.",
        "real_cost": "Uniform 1.00..30.00, 2 decimals.",
        "integer_quantity": "Uniform 1..1000; 5% boundary at 499/500/501.",
        "enum_small": "Draw uniformly from the listed enum values.",
        "null_share": "For each nullable column, 5% NULL rows per instance, at least one."
    },
    "per_column_exceptions": [],
    "dependencies": [],
    "semantic_rules_and_formulas": [],
    "table_sizes_per_instance": {},
    "null_targets": []
}

_ENUMS = {
    ('address_status', 'address_status'): ['Active', 'Inactive'],
    ('order_status', 'status_value'): ['Order Received', 'Pending Delivery', 'Delivery In Progress',
                                       'Delivered', 'Cancelled', 'Returned'],
}

_BOUNDARIES = {
    ('book', 'title'): ['Anleitung zum Zickigsein', 'anleitung zum zickigsein', 'Fantasmas', 'fantasmas'],
    ('book', 'publication_date'): ['1899-12-31', '1900-01-01', '1900-12-31', '1901-01-01',
                                   '2000-12-31', '2001-01-01', '2001-12-31', '2002-01-01',
                                   '1997-07-10', '2017-01-01'],
    ('publisher', 'publisher_name'): ['Ace Book', 'ace book', 'HarperCollins Publishers',
                                      'harpercollins publishers', 'Free Press', 'free press'],
    ('author', 'author_name'): ['Hirohiko Araki', 'hirohiko araki', 'Jennifer Crusie', 'jennifer crusie',
                                'A.J. Ayer', 'a.j. ayer', 'Ada', 'Adb', 'Ada x', 'ada', 'Adam', 'Adan',
                                'Adam x', 'adam', 'Orson Scott Card', 'Orson Scott Card x'],
    ('cust_order', 'order_date'): ['2020-12-31 00:00:00', '2021-01-01 00:00:00', '2021-12-31 00:00:00',
                                   '2022-01-01 00:00:00', '2020-11-30 00:00:00', '2020-12-01 00:00:00',
                                   '2019-12-31 00:00:00', '2020-01-01 00:00:00', '2020-12-31 00:00:00'],
    ('customer', 'first_name'): ['Lucas', 'lucas', 'Ursola', 'ursola', 'Ruthanne', 'ruthanne'],
    ('customer', 'last_name'): ['Vatini', 'vatini', 'Wyldbore', 'wyldbore', 'Purdy', 'purdy'],
    ('book', 'num_pages'): [499, 500, 501],
    ('order_history', 'status_date'): ['2021-12-31 00:00:00', '2022-01-01 00:00:00',
                                       '2022-12-31 00:00:00', '2023-01-01 00:00:00',
                                       '2019-11-30 00:00:00', '2019-12-01 00:00:00',
                                       '2019-12-31 00:00:00', '2020-01-01 00:00:00',
                                       '2020-12-31 00:00:00', '2021-01-01 00:00:00'],
    ('book_language', 'language_name'): ['English', 'english'],
    ('shipping_method', 'method_name'): ['International', 'international', 'Priority', 'priority',
                                         'Express', 'express'],
    ('address', 'street_number'): ['8', '9', '10'],
    ('order_line', 'price'): [9.99, 10.0, 10.01, 12.99, 13.0, 13.01],
    ('publisher', 'publisher_id'): [21, 22, 23, 1928, 1929, 1930],
    ('book', 'publisher_id'): [21, 22, 23, 1928, 1929, 1930],
}

_RANGES = {
    ('book', 'num_pages'): (1, 1000, True, 0),
    ('order_line', 'price'): (0.5, 50.0, False, 2),
    ('shipping_method', 'cost'): (1.0, 30.0, False, 2),
}

_DATE_RANGES = {
    ('book', 'publication_date'): ('1800-01-01', '2025-12-31', '%Y-%m-%d'),
    ('cust_order', 'order_date'): ('2019-01-01 00:00:00', '2023-12-31 23:59:59', '%Y-%m-%d %H:%M:%S'),
    ('order_history', 'status_date'): ('2019-01-01 00:00:00', '2023-12-31 23:59:59', '%Y-%m-%d %H:%M:%S'),
}

_UNIQUE = set()

_LONG_TEXT = {('book', 'title'), ('author', 'author_name'), ('publisher', 'publisher_name')}


def load_specification(path: str) -> dict:
    """Read specification.json if present, else the built-in default."""
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_DEFAULT)


def _parse_null_target(entry) -> tuple:
    """Accept 'table.column' strings or [table, column] pairs; return (table, column) or None."""
    if isinstance(entry, (list, tuple)) and len(entry) == 2:
        return (str(entry[0]), str(entry[1]))
    if isinstance(entry, str) and '.' in entry:
        t, c = entry.split('.', 1)
        return (t.strip(), c.strip())
    return None


def build_spec(raw: dict, schema) -> dict:
    """Turn the raw specification into sampler-friendly structures."""
    sizes = dict(raw.get('table_sizes_per_instance') or {})
    null_targets = set()
    for entry in (raw.get('null_targets') or []):
        parsed = _parse_null_target(entry)
        if parsed is not None:
            null_targets.add(parsed)
    deps = dict(schema.fks)
    rules = []
    for r in (raw.get('semantic_rules_and_formulas') or []):
        rules.append(r)
    return {
        'sizes': sizes,
        'null_targets': null_targets,
        'deps': deps,
        'enums': dict(_ENUMS),
        'boundaries': dict(_BOUNDARIES),
        'ranges': dict(_RANGES),
        'date_ranges': dict(_DATE_RANGES),
        'unique': set(_UNIQUE),
        'long_text': set(_LONG_TEXT),
        'rules': rules,
        'raw': raw,
    }
