"""Specification constants and helpers (value domains, enum pools, semantic rules) by construction."""
import datetime as dt

ENUM_POOLS = {
    'Role_Code': ['ED', 'HR', 'MG', 'PR', 'PT'],
    'Document_Type_Code': ['BK', 'CV', 'PR', 'RV'],
    'Location_Code': ['b', 'c', 'e', 'n', 'x'],
    'Gender_MFU': ['M', 'F', 'U'],
}

ASSUMED_DOMAINS = {
    ('Employees', 'Gender_MFU'),
    ('Ref_Calendar', 'Day_Number'),
}

TABLE_SIZES = {
    'Ref_Document_Types': 4,
    'Ref_Locations': 5,
    'Roles': 5,
    'Ref_Calendar': 15,
    'All_Documents': 15,
    'Employees': 15,
    'Document_Locations': 15,
    'Documents_to_be_Destroyed': 11,
}

NULLABLE = {
    ('All_Documents', 'Date_Stored'),
    ('All_Documents', 'Document_Description'),
    ('All_Documents', 'Other_Details'),
    ('Document_Locations', 'Date_in_Locaton_To'),
    ('Documents_to_be_Destroyed', 'Destruction_Authorised_by_Employee_ID'),
    ('Documents_to_be_Destroyed', 'Destroyed_by_Employee_ID'),
    ('Documents_to_be_Destroyed', 'Planned_Destruction_Date'),
    ('Documents_to_be_Destroyed', 'Actual_Destruction_Date'),
    ('Documents_to_be_Destroyed', 'Other_Details'),
    ('Employees', 'Employee_Name'),
    ('Employees', 'Other_Details'),
    ('Ref_Calendar', 'Day_Number'),
    ('Roles', 'Role_Name'),
    ('Roles', 'Role_Description'),
}

BOUNDARY_LITERALS = {
    ('Employees', 'Role_Code'): ['HR', 'hr', 'ED', 'ed'],
    ('Roles', 'Role_Code'): ['HR', 'hr'],
    ('Roles', 'Role_Name'): ['Editor', 'editor'],
}

GROUP_SIZE_TARGETS = {
    ('Employees', 'Role_Code'): [1, 2, 3],
    ('Roles', 'Role_Code'): [1, 2, 3],
    ('Document_Locations', 'Location_Code'): [1, 2, 3],
    ('Ref_Locations', 'Location_Code'): [1, 2, 3],
}

AGGREGATE_BOUNDARY = {
    ('Employees', 'Role_Code'): [2, 3, 4],
    ('Roles', 'Role_Code'): [2, 3, 4],
}

DUPLICATE_SHARE = {
    ('Employees', 'Employee_Name'): 0.3,
    ('Document_Locations', 'Location_Code'): 0.3,
    ('Ref_Locations', 'Location_Name'): 0.3,
    ('Ref_Document_Types', 'Document_Type_Name'): 0.3,
}

TIE_TARGETS = {
    ('Document_Locations', 'Location_Code'): True,
    ('All_Documents', 'Date_Stored'): True,
}

UNMATCHED_JOIN = {
    ('Employees', 'Role_Code'): {'parent_no_child': True, 'child_null': False},
    ('Roles', 'Role_Code'): {'parent_no_child': True, 'child_null': False},
    ('Employees', 'Employee_ID'): {'parent_no_child': True, 'child_null': True},
    ('Document_Locations', 'Location_Code'): {'parent_no_child': True, 'child_null': False},
    ('Ref_Locations', 'Location_Code'): {'parent_no_child': True, 'child_null': False},
    ('Documents_to_be_Destroyed', 'Destruction_Authorised_by_Employee_ID'): {'parent_no_child': True, 'child_null': True},
    ('Documents_to_be_Destroyed', 'Destroyed_by_Employee_ID'): {'parent_no_child': True, 'child_null': True},
    ('Document_Locations', 'Document_ID'): {'parent_no_child': True, 'child_null': False},
    ('All_Documents', 'Document_ID'): {'parent_no_child': True, 'child_null': False},
}


def _date_in_range(v):
    if v is None:
        return True
    try:
        d = dt.datetime.strptime(str(v)[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return True
    return dt.datetime(1900, 1, 1) <= d <= dt.datetime(2020, 12, 31, 23, 59, 59)


def _day_in_range(v):
    if v is None:
        return True
    try:
        return 1 <= int(v) <= 31
    except (TypeError, ValueError):
        return True


def _role_code_ok(v):
    """Case-insensitive membership so boundary literals 'hr'/'ed' survive."""
    return v is None or str(v).upper() in ENUM_POOLS['Role_Code']


def _doc_type_ok(v):
    return v is None or str(v).upper() in ENUM_POOLS['Document_Type_Code']


def _loc_code_ok(v):
    return v is None or str(v).lower() in ENUM_POOLS['Location_Code']


def _gender_ok(v):
    return v is None or str(v).upper() in ENUM_POOLS['Gender_MFU']


SEMANTIC_RULES = {
    ('Employees', 'Role_Code'): _role_code_ok,
    ('Employees', 'Gender_MFU'): _gender_ok,
    ('Employees', 'Date_of_Birth'): _date_in_range,
    ('Roles', 'Role_Code'): _role_code_ok,
    ('Ref_Document_Types', 'Document_Type_Code'): _doc_type_ok,
    ('Ref_Locations', 'Location_Code'): _loc_code_ok,
    ('All_Documents', 'Document_Type_Code'): _doc_type_ok,
    ('Ref_Calendar', 'Day_Number'): _day_in_range,
}


def _parse_dt(v):
    if v is None:
        return None
    try:
        return dt.datetime.strptime(str(v)[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def row_rule_ok(table, row):
    """Check row-level semantic rules (non-NULL operands only; SQL three-valued logic)."""
    for (t, c), pred in SEMANTIC_RULES.items():
        if t == table and c in row:
            if not pred(row[c]):
                return False
    if table == 'Document_Locations':
        f = _parse_dt(row.get('Date_in_Location_From'))
        to = _parse_dt(row.get('Date_in_Locaton_To'))
        if f is not None and to is not None and to < f:
            return False
    if table == 'Documents_to_be_Destroyed':
        p = _parse_dt(row.get('Planned_Destruction_Date'))
        a = _parse_dt(row.get('Actual_Destruction_Date'))
        if p is not None and a is not None and a < p:
            return False
    return True
