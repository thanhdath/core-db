"""Specification constants: enums, date ranges, name pools, per-column pattern targets."""
import datetime as dt

POLICY_TYPE_VALUES = ['Car', 'Life', 'Property', 'Travel']
PAYMENT_METHOD_VALUES = ['MasterCard', 'Discover Card', 'Visa', 'American Express']

ENUMS = {
    ('Customer_Policies', 'Policy_Type_Code'): POLICY_TYPE_VALUES,
    ('Payments', 'Payment_Method_Code'): PAYMENT_METHOD_VALUES,
}

DATE_LO = dt.date(2016, 1, 1)
DATE_HI = dt.date(2018, 12, 31)
DATE_SPAN_DAYS = 400

FIRST_NAMES = [
    'America', 'Ellsworth', 'Hanna', 'Diana', 'Selena', 'Lauriane', 'Sydnie', 'Dayana',
    'James', 'Mary', 'Robert', 'Patricia', 'John', 'Jennifer', 'Michael', 'Linda',
    'David', 'Elizabeth', 'William', 'Barbara', 'Richard', 'Susan', 'Joseph', 'Jessica',
    'Thomas', 'Sarah', 'Charles', 'Karen', 'Christopher', 'Nancy', 'Daniel', 'Lisa',
    'Matthew', 'Betty', 'Anthony', 'Margaret', 'Mark', 'Sandra', 'Donald', 'Ashley',
]
LAST_NAMES = [
    'Jaskolski', 'Paucek', 'Willms', 'Rath', 'Gerhold', 'Ferry', 'Friesen', 'Robel',
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
    'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
    'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker',
    'Young',
]
NAME_TITLES = ['', '', '', 'Dr. ', 'Mrs. ', 'Mr. ', 'Ms. ', 'PhD ']

GROUP_SIZE_PLAN = [1, 2, 3]

DUP_SHARE_LO, DUP_SHARE_HI = 0.20, 0.50

TIE_ROWS = 2

AGG_BOUNDARY_VALUES = [0, 1, 2, 3]

NULL_SHARE = 0.10

AMOUNT_LO, AMOUNT_HI = 1, 100000
SMALL_LO, SMALL_HI = 1, 2000

TABLE_SIZES = {'Customers': 15, 'Customer_Policies': 15, 'Claims': 15,
               'Settlements': 15, 'Payments': 15}

PK_COLUMNS = {
    ('Customers', 'Customer_ID'),
    ('Customer_Policies', 'Policy_ID'),
    ('Claims', 'Claim_ID'),
    ('Settlements', 'Settlement_ID'),
    ('Payments', 'Payment_ID'),
}

DISTINCT_TARGETS = {
    ('Customers', 'Customer_Details'),
    ('Payments', 'Date_Payment_Made'),
    ('Payments', 'Amount_Payment'),
}

GROUP_SIZE_TARGETS = {
    ('Claims', 'Date_Claim_Made'),
    ('Customers', 'Customer_Details'),
    ('Payments', 'Payment_Method_Code'),
    ('Payments', 'Date_Payment_Made'),
    ('Settlements', 'Claim_ID'),
    ('Claims', 'Amount_Settled'),
    ('Claims', 'Date_Claim_Settled'),
}

TIE_TARGETS = {
    ('Claims', 'Date_Claim_Made'): ('ASC', None),
    ('Payments', 'Payment_Method_Code'): ('ASC', 'COUNT'),
    ('Claims', 'Amount_Claimed'): ('DESC', None),
    ('Claims', 'Policy_ID'): ('DESC', None),
    ('Customer_Policies', 'Policy_Type_Code'): ('DESC', 'COUNT'),
}

NULLABLE = {
    ('Claims', 'Date_Claim_Made'), ('Claims', 'Date_Claim_Settled'),
    ('Claims', 'Amount_Claimed'), ('Claims', 'Amount_Settled'),
    ('Customer_Policies', 'Start_Date'), ('Customer_Policies', 'End_Date'),
    ('Payments', 'Payment_Method_Code'), ('Payments', 'Date_Payment_Made'),
    ('Payments', 'Amount_Payment'),
}

DATE_PAIRS = {
    ('Customer_Policies', 'Start_Date', 'End_Date'),
    ('Claims', 'Date_Claim_Made', 'Date_Claim_Settled'),
}

COPIED = {
    ('Settlements', 'Claim_ID'): [('Date_Claim_Made', 'Date_Claim_Made'),
                                  ('Date_Claim_Settled', 'Date_Claim_Settled'),
                                  ('Amount_Claimed', 'Amount_Claimed'),
                                  ('Amount_Settled', 'Amount_Settled')],
}

FKS = [
    ('Customer_Policies', 'Customer_ID', 'Customers', 'Customer_ID'),
    ('Claims', 'Policy_ID', 'Customer_Policies', 'Policy_ID'),
    ('Settlements', 'Claim_ID', 'Claims', 'Claim_ID'),
    ('Payments', 'Settlement_ID', 'Settlements', 'Settlement_ID'),
]

PARENT_WITHOUT_CHILDREN = {
    ('Settlements', 'Payments'),
    ('Claims', 'Settlements'),
    ('Customers', 'Customer_Policies'),
}
