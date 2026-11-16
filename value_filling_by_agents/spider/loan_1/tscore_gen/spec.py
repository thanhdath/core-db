"""Specification tables (tscore_gen/specification.json) implemented by construction."""

SEMANTIC_RULES = {
    ('bank', 'branch_ID'): ('range', (1, None)),
    ('bank', 'no_of_customers'): ('nonneg', None),
    ('customer', 'acc_type'): ('enum', ('saving', 'checking')),
    ('customer', 'acc_bal'): ('nonneg', None),
    ('customer', 'no_of_loans'): ('nonneg', None),
    ('customer', 'credit_score'): ('range', (0, 1000)),
    ('loan', 'loan_type'): ('enum', ('Mortgages', 'Auto', 'Business')),
    ('loan', 'amount'): ('nonneg', None),
}

BOUNDARY_VALUES = {
    ('customer', 'credit_score'): [86, 87, 88, 99, 100, 101],
    ('customer', 'cust_ID'): ['99', '100', '101'],
    ('loan', 'cust_ID'): ['0', '1', '2'],
    ('customer', 'no_of_loans'): [-1, 0, 1, 2],
    ('loan', 'loan_type'): ['Mortgages', 'mortgages', 'Auto', 'auto'],
    ('customer', 'acc_type'): ['saving', 'SAVING'],
    ('bank', 'city'): ['', 'x', 'New York City', 'new york city'],
}

TIE_TARGETS = {
    ('bank', 'bname'): ('DESC', 1),
    ('bank', 'state'): ('DESC', 1),
    ('bank', 'no_of_customers'): ('DESC', 1),
    ('customer', 'acc_bal'): ('ASC', None),
    ('loan', 'amount'): ('DESC', 1),
}

DUPLICATE_TARGETS = {
    ('customer', 'credit_score'): (0.2, 0.5),
    ('customer', 'cust_name'): (0.2, 0.5),
    ('bank', 'bname'): (0.2, 0.5),
    ('customer', 'state'): (0.2, 0.5),
}

GROUP_SIZE_TARGETS = {
    ('bank', 'branch_ID'), ('bank', 'bname'), ('customer', 'credit_score'),
    ('customer', 'cust_name'), ('customer', 'cust_ID'),
}

NULL_TARGETS = [('customer', 'branch_ID'), ('loan', 'cust_ID'), ('loan', 'branch_ID')]

TABLE_SIZES = {'bank': 4, 'customer': 6, 'loan': 6}

DEPENDENCIES = [
    ('customer', 'branch_ID', 'bank', 'branch_ID'),
    ('loan', 'branch_ID', 'bank', 'branch_ID'),
    ('loan', 'cust_ID', 'customer', 'cust_ID'),
]

UNMATCHED_JOIN = {
    ('bank', 'branch_ID'): ['customer.branch_ID', 'loan.branch_ID'],
    ('customer', 'cust_ID'): ['loan.cust_ID'],
    ('customer', 'branch_ID'): ['bank.branch_ID'],
    ('loan', 'branch_ID'): ['bank.branch_ID'],
    ('loan', 'cust_ID'): ['customer.cust_ID'],
}


def rule_for(table: str, column: str):
    """Return the semantic rule tuple for a column, or None."""
    return SEMANTIC_RULES.get((table, column))


def boundary_for(table: str, column: str) -> list:
    """Return boundary literals for a column (possibly empty)."""
    return list(BOUNDARY_VALUES.get((table, column), []))


def tie_for(table: str, column: str):
    """Return (direction, rank) tie target or None."""
    return TIE_TARGETS.get((table, column))


def duplicate_for(table: str, column: str):
    """Return (lo_share, hi_share) duplicate target or None."""
    return DUPLICATE_TARGETS.get((table, column))


def null_target(table: str, column: str) -> bool:
    """True if the column is a NULL target."""
    return (table, column) in NULL_TARGETS
