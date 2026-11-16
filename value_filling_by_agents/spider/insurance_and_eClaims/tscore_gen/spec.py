"""Specification constants (enums, ranges, NULL targets, per-column targets)."""
import datetime as dt

ENUMS = {
    ('Policies', 'Policy_Type_Code'): ['Deputy', 'Jurisdiction', 'Uniformed', 'Normal'],
    ('Claim_Headers', 'Claim_Status_Code'): ['Settled', 'Disputed', 'In Progress'],
    ('Claim_Headers', 'Claim_Type_Code'): ['Handphone Subsidy', 'Child Birth', 'Overtime Meal Subsidy'],
    ('Claims_Documents', 'Document_Type_Code'): ['Document', 'Medical', 'Photo'],
    ('Claims_Processing', 'Claim_Outcome_Code'): ['In progress', 'Disputed', 'Settled'],
    ('Claims_Processing_Stages', 'Claim_Status_Name'): ['Open', 'Close'],
}

NEAR_VARIANTS = {
    ('Policies', 'Policy_Type_Code'): ['deputy', 'Uniform', 'uniform', 'Uni', 'uni', 'form', 'FORM'],
}

INT_ENUMS = {
    ('Claims_Processing', 'Claim_Stage_ID'): [1, 3],
}

BOUNDARY_LITERALS = {
    ('Customers', 'Customer_Details'): ['Dayana Robel'],
}

NULL_TARGETS = [
    ('Policies', 'Start_Date'), ('Policies', 'End_Date'),
    ('Claim_Headers', 'Date_of_Claim'), ('Claim_Headers', 'Date_of_Settlement'),
    ('Claim_Headers', 'Amount_Claimed'), ('Claim_Headers', 'Amount_Piad'),
    ('Claims_Documents', 'Created_by_Staff_ID'), ('Claims_Documents', 'Created_Date'),
    ('Claims_Processing', 'Staff_ID'),
    ('Claims_Processing_Stages', 'Next_Claim_Stage_ID'),
]

DATE_LO = dt.datetime(2016, 1, 1)
DATE_HI = dt.datetime(2018, 12, 31)
DATE_FMT = '%Y-%m-%d %H:%M:%S'

AMOUNT_LO = 0.0
AMOUNT_HI = 1000.0

INT_LO, INT_HI = 1, 1000

GROUP_SIZE_TARGETS = (1, 2, 3)

DUP_SHARE_LO, DUP_SHARE_HI = 0.20, 0.50

BASE_SIZES = {
    'Customers': 15, 'Staff': 15, 'Policies': 15, 'Claim_Headers': 15,
    'Claims_Documents': 14, 'Claims_Processing_Stages': 2, 'Claims_Processing': 15,
}

DIFFERENT_VALUE_COLUMNS = [
    ('Claim_Headers', 'Amount_Claimed'), ('Claim_Headers', 'Amount_Piad'),
    ('Policies', 'Start_Date'),
]

DISTINCT_COLUMNS = [
    ('Customers', 'Customer_Details'), ('Policies', 'Policy_Type_Code'),
    ('Claims_Processing', 'Claim_Stage_ID'), ('Claims_Processing_Stages', 'Claim_Status_Name'),
]

GROUP_SIZE_COLUMNS = [
    ('Customers', 'Customer_Details'), ('Policies', 'Policy_Type_Code'),
    ('Claims_Processing', 'Claim_Stage_ID'), ('Claims_Processing_Stages', 'Claim_Status_Name'),
    ('Claim_Headers', 'Policy_ID'),
    ('Claims_Processing', 'Staff_ID'),
]

PARENT_WITHOUT_CHILDREN = [
    ('Policies', 'Policy_ID', 'Claim_Headers', 'Policy_ID'),
    ('Claim_Headers', 'Claim_Header_ID', 'Claims_Processing', 'Claim_ID'),
    ('Customers', 'Customer_ID', 'Policies', 'Customer_ID'),
]

NULL_SHARE_FALLBACK_LO, NULL_SHARE_FALLBACK_HI = 0.10, 0.20
