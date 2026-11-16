"""Generation specification encoded by construction (never evaluated as SQL)."""
import datetime as dt
import re


TABLE_SIZES = {
    'Addresses': 15,
    'Products': 3,
    'Customers': 15,
    'Customer_Addresses': 15,
    'Customer_Contact_Channels': 20,
    'Customer_Orders': 15,
    'Order_Items': 15,
}

MIN_ADDRESSES_SIZE = 5
PRODUCTS_SIZE = 3

ENUMS = {
    'Addresses.country': ['USA'],
    'Customers.payment_method': ['Cash', 'Cheque', 'Credit Card'],
    'Customer_Addresses.address_type': ['Billing', 'Residential'],
    'Customer_Orders.order_status': ['Cancelled', 'Delivered'],
}

POSITIVE_INT = {
    'Addresses.address_id', 'Products.product_id', 'Customers.customer_id',
    'Customer_Orders.order_id',
}

BOUNDARY_STRINGS = {
    'Products.product_details': [
        'Americano', 'Latte', 'Americano x', 'Latte x', 'Americanp', 'Lattf', 'americano', 'latte',
    ],
    'Addresses.country': ['USA', 'USA '],
    'Addresses.city': [
        'Lucasville', 'New Sabryna', 'Reingertown', 'Gleasonmouth', 'Stantonville',
        'South Meghanview', 'Lake Walterton', 'South Bellaland',
        'Lucasville ', 'lucasville', 'New Sabryna x',
    ],
    'Customers.payment_method': ['Cash', 'Cheque', 'Credit Card', 'cash', 'Credit', 'Cheque '],
}

LIKE_PATTERNS = {
    'Products.product_details': ['%A%', '%Latte%', '%Americano%'],
}

REQUIRED_BOUNDARIES = {
    'Products.product_details': ['Americano', 'Latte'],
    'Addresses.country': ['USA'],
    'Customers.payment_method': ['Cash', 'Cheque', 'Credit Card'],
}

BOUNDARY_NUMBERS = {
    'Addresses.address_id': [3, 4, 5],
    'Products.product_id': [1, 2, 3],
    'Customers.customer_id': [1, 2, 3],
    'Customer_Orders.order_id': [1, 2, 3],
    'Order_Items.product_id': [1, 2, 3],
}

BOUNDARY_DATES = {
    'Customer_Orders.order_date': [
        '2018-02-28 15:46:06', '2018-03-05 06:35:33', '2018-03-17 02:51:37',
        '2018-03-17 07:13:53',
    ],
    'Customers.date_became_customer': [
        '2018-02-24 00:20:18', '2018-02-28 11:37:44', '2018-03-09 17:41:58',
    ],
}

NULLABLE_COLUMNS = {
    'Addresses.other_address_details',
    'Customer_Addresses.date_address_to',
    'Customer_Contact_Channels.active_to_date',
    'Customer_Orders.order_date',
    'Customer_Orders.order_details',
    'Customers.customer_name',
    'Customers.date_became_customer',
    'Customers.other_customer_details',
    'Order_Items.order_quantity',
}

NULL_SHARE = {
    'Addresses.other_address_details': 1.0,
    'Customers.customer_name': 0.05,
    'Customers.date_became_customer': 0.05,
    'Customers.other_customer_details': 0.867,
    'Customer_Addresses.date_address_to': 0.10,
    'Customer_Contact_Channels.active_to_date': 0.10,
    'Customer_Orders.order_date': 0.05,
    'Customer_Orders.order_details': 0.667,
    'Order_Items.order_quantity': 0.05,
}

DUPLICATE_COLUMNS = {
    'Addresses.city',
    'Addresses.country',
    'Customers.customer_name',
    'Products.product_details',
    'Customer_Addresses.address_id',
    'Order_Items.product_id',
}

TIE_COLUMNS = {
    'Addresses.city', 'Addresses.country', 'Customers.customer_name',
    'Customers.payment_method', 'Products.product_details',
    'Customer_Contact_Channels.active_to_date',
}

TIE_PLANTS_EXTERNAL = [
    ('Order_Items', 'product_id', 'Products.product_id'),
    ('Customer_Orders', 'customer_id', 'Customers.customer_id'),
    ('Customer_Addresses', 'address_id', 'Addresses.address_id'),
]

UNMATCHED_PARENTS = {
    'Customers': {'Customer_Addresses', 'Customer_Orders'},
    'Products': {'Order_Items'},
    'Customer_Orders': {'Order_Items'},
    'Addresses': {'Customer_Addresses'},
}

DATE_PAIRS = [
    ('Customer_Addresses', 'date_address_to', 'date_address_from', 'ge'),
    ('Customer_Contact_Channels', 'active_to_date', 'active_from_date', 'ge'),
]

POSITIVE_QUANTITIES = {
    ('Order_Items', 'order_quantity'),
}

OBSERVED = {
    'Addresses.address_content': [
        '9443 Boyle Route Suite 857', '1969 Jabari Port Suite 393', '295 Hackett Curve',
        '92865 Margaretta Streets Suite 467', '08996 Brisa Lane Apt. 583',
        '826 Murray Locks Apt. 654', '59540 Grover Wells Apt. 814', '78614 Maybell Alley Suite 057',
    ],
    'Addresses.city': [
        'Lucasville', 'New Sabryna', 'Reingertown', 'Gleasonmouth', 'Stantonville',
        'South Meghanview', 'Lake Walterton', 'South Bellaland',
    ],
    'Addresses.zip_postcode': ['416', '721', '255', '940', '354', '918', '767', '921'],
    'Addresses.state_province_county': [
        'Colorado', 'SouthCarolina', 'NewJersey', 'Arizona', 'Mississippi', 'Virginia',
        'Florida', 'Texas',
    ],
    'Customers.customer_name': [
        'Dr. Julia Wuckert MD', 'Tillman Ernser', 'Rodrick Heaney', 'Prof. Alexzander Hamill',
        'Prof. Reyes Berge II', 'Maudie Kertzmann', 'Mozell Morissette', 'Eunice Morar',
    ],
    'Customers.payment_method': ['Cash', 'Cheque', 'Credit Card'],
    'Customer_Addresses.address_type': ['Billing', 'Residential'],
    'Customer_Contact_Channels.channel_code': ['Email', 'Cell', 'Handheld', 'Fax', 'Mobile'],
    'Customer_Contact_Channels.contact_number': [
        '940.035.6435x0225', '189.449.8326x7607', '958-653-2640', '1-968-863-4947x96956',
        '(165)527-5756x2419', '1-077-864-0102', '06068550461', '542.983.0224',
    ],
    'Customer_Orders.order_status': ['Cancelled', 'Delivered'],
    'Customer_Orders.order_details': ['Second time'],
    'Order_Items.order_quantity': ['5', '9', '2', '6', '8', '1', '7'],
    'Products.product_details': ['Americano', 'Dove Chocolate', 'Latte'],
}

DATE_WINDOWS = {
    'Customers.date_became_customer': ('2018-01-01 00:00:00', '2018-03-31 23:59:59'),
    'Customer_Addresses.date_address_from': ('1972-01-01 00:00:00', '2018-03-31 23:59:59'),
    'Customer_Addresses.date_address_to': ('1972-01-01 00:00:00', '2018-03-31 23:59:59'),
    'Customer_Contact_Channels.active_from_date': ('2017-01-01 00:00:00', '2018-01-31 23:59:59'),
    'Customer_Contact_Channels.active_to_date': ('2017-01-01 00:00:00', '2018-03-31 23:59:59'),
    'Customer_Orders.order_date': ('2018-01-01 00:00:00', '2018-03-31 23:59:59'),
}


def _parse_dt(s):
    s = (s or '').strip()
    for t in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None


def minute_key(s):
    """Canonical form used to enforce 'distinct timestamps' in a column."""
    d = _parse_dt(s)
    return d.strftime('%Y-%m-%d %H:%M') if d else str(s)


class Spec:
    """Resolved specification for one database (table sizes, pools, rules)."""

    def __init__(self, schema):
        self.schema = schema
        self.table_sizes = {t: n for t, n in TABLE_SIZES.items() if t in schema.tables}
        for t in schema.tables:
            self.table_sizes.setdefault(
                t, max(1, len(schema.original_values.get((t, schema.tables[t].columns[0].name), []))))
        self.enums = {k: list(v) for k, v in ENUMS.items()}
        self.positive_int = set(POSITIVE_INT)
        self.boundary_strings = {k: list(v) for k, v in BOUNDARY_STRINGS.items()}
        self.like_patterns = {k: list(v) for k, v in LIKE_PATTERNS.items()}
        self.required_boundaries = {k: list(v) for k, v in REQUIRED_BOUNDARIES.items()}
        self.boundary_numbers = {k: list(v) for k, v in BOUNDARY_NUMBERS.items()}
        self.boundary_dates = {k: list(v) for k, v in BOUNDARY_DATES.items()}
        self.nullable = set(NULLABLE_COLUMNS)
        self.null_share = dict(NULL_SHARE)
        self.duplicates = set(DUPLICATE_COLUMNS)
        self.ties = set(TIE_COLUMNS)
        self.tie_plants_external = list(TIE_PLANTS_EXTERNAL)
        self.unmatched_parents = {p: set(c) for p, c in UNMATCHED_PARENTS.items()}
        self.date_pairs = list(DATE_PAIRS)
        self.positive_quantities = set(POSITIVE_QUANTITIES)
        self.observed = {k: list(v) for k, v in OBSERVED.items()}
        self.date_windows = dict(DATE_WINDOWS)
        self.min_addresses_size = MIN_ADDRESSES_SIZE
        self.products_size = PRODUCTS_SIZE
        self.pk_offset = {}
        for t, tm in schema.tables.items():
            if not tm.primary_key:
                self.pk_offset[t] = 0
                continue
            mx = 0
            for c in tm.primary_key:
                for v in schema.original_values.get((t, c), []):
                    try:
                        mx = max(mx, int(v))
                    except (TypeError, ValueError):
                        pass
            self.pk_offset[t] = mx
        self._merge_compact_observed()

    def _merge_compact_observed(self):
        for (t, c), vals in self.schema.original_values.items():
            key = '%s.%s' % (t, c)
            present = [v for v in vals if v is not None]
            if present:
                merged = list(self.observed.get(key, [])) + present
                self.observed[key] = list(dict.fromkeys(str(x) for x in merged))

    def is_nullable(self, table, column):
        return '%s.%s' % (table, column) in self.nullable

    def null_share_for(self, table, column):
        return self.null_share.get('%s.%s' % (table, column), 0.05)

    def observed_for(self, table, column):
        return list(self.observed.get('%s.%s' % (table, column), []))

    def boundary_for(self, table, column):
        key = '%s.%s' % (table, column)
        out = []
        out += self.boundary_strings.get(key, [])
        out += self.like_patterns.get(key, [])
        out += [str(v) for v in self.boundary_numbers.get(key, [])]
        out += self.boundary_dates.get(key, [])
        return out

    def required_boundary_for(self, table, column):
        return list(self.required_boundaries.get('%s.%s' % (table, column), []))

    def pk_start_for(self, table):
        return self.pk_offset.get(table, 0) + 1


def build_spec(schema):
    """Build the resolved Spec for a schema."""
    return Spec(schema)


def like_body(lit):
    """Strip surrounding quotes and any leading/trailing '%' used for LIKE patterns."""
    s = (lit or '').strip()
    if len(s) >= 2 and s[0] in '\'"' and s[-1] == s[0]:
        s = s[1:-1]
    s = re.sub(r'^%+|%+$', '', s)
    return s
