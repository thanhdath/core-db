"""Generation specification, implemented by construction (no SQL evaluation)."""
import datetime as dt
import re
from dataclasses import dataclass, field


BOUNDARY = {
    ('customers', 'customerNumber'): [102, 103, 104, 185, 186, 187],
    ('customers', 'customerName'): ['Atelier graphique', 'atelier graphique', 'ATELIER GRAPHIQUE',
                                    'Cruz & Sons Co.', 'cruz & sons co.'],
    ('customers', 'creditLimit'): [-1, 0, 1, 219999, 220000, 220001],
    ('orders', 'orderNumber'): [10099, 10100, 10101, 10251, 10252, 10253],
    ('orders', 'orderDate'): ['2005-04-07', '2005-04-08', '2005-04-09', '2005-04-10', '2005-04-11'],
    ('orderdetails', 'orderNumber'): [10099, 10100, 10101, 10251, 10252, 10253],
    ('payments', 'paymentDate'): ['2003-12-31', '2004-01-01', '2004-12-31', '2005-01-01'],
    ('payments', 'customerNumber'): [102, 103, 104],
    ('employees', 'lastName'): ['Patterson', 'patterson', 'a', 'A', 'Jones', 'jones'],
    ('employees', 'firstName'): ['William', 'william', 'Steve', 'steve', 'Patterson', 'patterson'],
}

NEAR_VARIANTS = {
    ('orders', 'orderDate'): ['2003-', '2004-', '2003- x', '2003-03-04', '2003-03-03x'],
    ('payments', 'paymentDate'): ['2004-', '2005-', '2004- x', '2003-12-31', '2004-01-01',
                                  '2004-12-31', '2005-01-01'],
}

ENUMS = {
    ('orders', 'status'): ['Shipped', 'Resolved', 'Cancelled', 'On Hold', 'Disputed', 'In Process'],
    ('employees', 'jobTitle'): ['President', 'VP Sales', 'VP Marketing', 'Sales Manager (APAC)',
                                'Sale Manager (EMEA)', 'Sales Manager (NA)', 'Sales Rep'],
    ('offices', 'territory'): ['NA', 'EMEA', 'Japan', 'APAC'],
    ('products', 'productScale'): ['1:10', '1:12', '1:18', '1:24', '1:32', '1:50', '1:72', '1:700'],
}

TIES = {
    ('orderdetails', 'priceEach'): {'ranks': [1], 'direction': 'DESC',
                                    'expr': 'quantityOrdered * priceEach'},
    ('orderdetails', 'quantityOrdered'): {'ranks': [1, 5], 'direction': 'ASC and DESC',
                                          'expr': 'quantityOrdered * priceEach'},
}

DUPLICATE_SHARE = {
    ('customers', 'customerName'): (0.20, 0.50),
}

UNMATCHED_PARENTS = {
    'customers': ['payments', 'orders'],
    'orders': ['orderdetails'],
}

NULL_SHARES = {
    ('customers', 'addressLine2'): 0.82,
    ('customers', 'state'): 0.598,
    ('customers', 'postalCode'): 0.057,
    ('customers', 'salesRepEmployeeNumber'): 0.18,
    ('customers', 'creditLimit'): 0.10,
    ('employees', 'reportsTo'): 0.043,
    ('offices', 'addressLine2'): 0.286,
    ('offices', 'state'): 0.429,
    ('orders', 'shippedDate'): 0.043,
    ('orders', 'comments'): 0.755,
    ('productlines', 'textDescription'): 0.0,
    ('productlines', 'htmlDescription'): 1.0,
    ('productlines', 'image'): 1.0,
}

NULLABLE_FK_SHARE = {
    ('customers', 'salesRepEmployeeNumber'): 0.18,
    ('employees', 'reportsTo'): 0.043,
}

TABLE_SIZES = {
    'offices': 7, 'employees': 23, 'customers': 122, 'orders': 326,
    'payments': 273, 'productlines': 7, 'products': 110, 'orderdetails': 2996,
}

DATE_FORMAT = '%Y-%m-%d'


def _rule_required_ge_order(row):
    r, o = row.get('requiredDate'), row.get('orderDate')
    return r is None or o is None or r >= o


def _rule_shipped_ge_order(row):
    s, o = row.get('shippedDate'), row.get('orderDate')
    return s is None or o is None or s >= o


def _rule_credit_nonneg(row):
    v = row.get('creditLimit')
    return v is None or v >= 0


def _rule_qty_pos(row):
    v = row.get('quantityOrdered')
    return v is None or v > 0


def _rule_line_pos(row):
    v = row.get('orderLineNumber')
    return v is None or v > 0


def _rule_stock_nonneg(row):
    v = row.get('quantityInStock')
    return v is None or v >= 0


def _rule_amount_nonneg(row):
    v = row.get('amount')
    return v is None or v >= 0


def _rule_buyprice_nonneg(row):
    v = row.get('buyPrice')
    return v is None or v >= 0


def _rule_msrp_nonneg(row):
    v = row.get('MSRP')
    return v is None or v >= 0


def _rule_price_nonneg(row):
    v = row.get('priceEach')
    return v is None or v >= 0


def _rule_reports_not_self(row):
    r, e = row.get('reportsTo'), row.get('employeeNumber')
    return r is None or e is None or r != e


RULES = {
    'orders': [_rule_required_ge_order, _rule_shipped_ge_order],
    'customers': [_rule_credit_nonneg],
    'orderdetails': [_rule_qty_pos, _rule_line_pos, _rule_price_nonneg],
    'products': [_rule_stock_nonneg, _rule_buyprice_nonneg, _rule_msrp_nonneg],
    'payments': [_rule_amount_nonneg],
    'employees': [_rule_reports_not_self],
}


@dataclass
class Spec:
    """Parsed specification bound to a schema."""
    boundary: dict = field(default_factory=dict)
    near_variants: dict = field(default_factory=dict)
    enums: dict = field(default_factory=dict)
    ties: dict = field(default_factory=dict)
    duplicate_share: dict = field(default_factory=dict)
    unmatched_parents: dict = field(default_factory=dict)
    null_shares: dict = field(default_factory=dict)
    nullable_fk_share: dict = field(default_factory=dict)
    table_sizes: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    date_format: str = DATE_FORMAT

    def null_share(self, table: str, column: str) -> float:
        return self.null_shares.get((table, column), 0.0)

    def fk_null_share(self, table: str, column: str) -> float:
        return self.nullable_fk_share.get((table, column), 0.0)

    def boundary_values(self, table: str, column: str) -> list:
        return list(self.boundary.get((table, column), []))

    def near_variant_values(self, table: str, column: str) -> list:
        return list(self.near_variants.get((table, column), []))

    def enum_values(self, table: str, column: str):
        return self.enums.get((table, column))

    def tie_target(self, table: str, column: str):
        return self.ties.get((table, column))

    def dup_share(self, table: str, column: str):
        return self.duplicate_share.get((table, column))

    def size_for(self, table: str, rng) -> int:
        """Compact row count with a small per-instance variation (0-230 or level x4 capped at 2500)."""
        base = self.table_sizes.get(table, 0)
        if base <= 0:
            return 0
        lo = max(1, int(base * 0.9))
        hi = max(lo, int(base * 1.1))
        return rng.randint(lo, hi)

    def check_rules(self, table: str, row: dict) -> bool:
        for rule in self.rules.get(table, ()):
            if not rule(row):
                return False
        return True


def _coerce_boundary(schema, table: str, column: str, values: list) -> list:
    """Coerce boundary literals to the column's declared type."""
    cm = None
    tm = schema.tables.get(table)
    if tm is not None:
        cm = next((c for c in tm.columns if c.name == column), None)
    if cm is None:
        return values
    t = (cm.type_str or '').lower()
    out = []
    for v in values:
        if 'int' in t:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                out.append(v)
        elif any(k in t for k in ('real', 'float', 'double', 'numeric', 'decimal')):
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(v)
        else:
            out.append(str(v))
    return out


def load_spec(schema) -> Spec:
    """Build a Spec bound to the given schema (coerces boundary literals to column types)."""
    boundary = {}
    for (t, c), vals in BOUNDARY.items():
        boundary[(t, c)] = _coerce_boundary(schema, t, c, vals)
    near = {}
    for (t, c), vals in NEAR_VARIANTS.items():
        near[(t, c)] = list(vals)
    enums = {k: list(v) for k, v in ENUMS.items()}
    ties = {k: dict(v) for k, v in TIES.items()}
    dup = dict(DUPLICATE_SHARE)
    unmatched = {k: list(v) for k, v in UNMATCHED_PARENTS.items()}
    null_shares = dict(NULL_SHARES)
    fk_share = dict(NULLABLE_FK_SHARE)
    sizes = dict(TABLE_SIZES)
    def _exists(t, c):
        tm = schema.tables.get(t)
        return tm is not None and any(col.name == c for col in tm.columns)
    boundary = {k: v for k, v in boundary.items() if _exists(*k)}
    near = {k: v for k, v in near.items() if _exists(*k)}
    enums = {k: v for k, v in enums.items() if _exists(*k)}
    ties = {k: v for k, v in ties.items() if _exists(*k)}
    dup = {k: v for k, v in dup.items() if _exists(*k)}
    null_shares = {k: v for k, v in null_shares.items() if _exists(*k)}
    fk_share = {k: v for k, v in fk_share.items() if _exists(*k)}
    sizes = {k: v for k, v in sizes.items() if k in schema.tables}
    rules = {k: v for k, v in RULES.items() if k in schema.tables}
    return Spec(boundary=boundary, near_variants=near, enums=enums, ties=ties,
                duplicate_share=dup, unmatched_parents=unmatched, null_shares=null_shares,
                nullable_fk_share=fk_share, table_sizes=sizes, rules=rules,
                date_format=DATE_FORMAT)
