"""Generation specification modelled by construction (values per column, table sizes, NULL targets)."""

TABLE_SIZES = {
    'Addresses': 8, 'Ref_Document_Types': 3, 'Ref_Document_Status': 3, 'Ref_Shipping_Agents': 5,
    'Roles': 4, 'Documents': 15, 'Employees': 6, 'Document_Drafts': 15, 'Draft_Copies': 8,
    'Circulation_History': 6, 'Documents_Mailed': 14,
}

ENUMS = {
    ('Documents', 'document_status_code'): ['done', 'overdue', 'working'],
    ('Documents', 'document_type_code'): ['CD', 'Hard Drive', 'Paper'],
    ('Ref_Document_Status', 'document_status_code'): ['done', 'overdue', 'working'],
    ('Ref_Document_Types', 'document_type_code'): ['CD', 'Hard Drive', 'Paper'],
    ('Ref_Shipping_Agents', 'shipping_agent_code'): ['AL', 'FE', 'SH', 'UP', 'US'],
    ('Employees', 'role_code'): ['ED', 'MG', 'PR', 'PT'],
    ('Roles', 'role_code'): ['ED', 'MG', 'PR', 'PT'],
}

CHAR_PK_POOLS = {
    ('Ref_Document_Status', 'document_status_code'): ['done', 'overdue', 'working'],
    ('Ref_Document_Types', 'document_type_code'): ['CD', 'Hard Drive', 'Paper'],
    ('Ref_Shipping_Agents', 'shipping_agent_code'): ['AL', 'FE', 'SH', 'UP', 'US'],
    ('Roles', 'role_code'): ['ED', 'MG', 'PR', 'PT'],
}

BOUNDARY = {
    ('Documents', 'document_id'): [0, 1, 2, 6, 7, 8],
    ('Ref_Shipping_Agents', 'shipping_agent_name'): ['USPS', 'usps', 'UPS', 'ups'],
    ('Documents', 'document_status_code'): ['done'],
    ('Documents', 'document_type_code'): ['Paper'],
    ('Draft_Copies', 'document_id'): [1, 2, 3],
    ('Document_Drafts', 'document_id'): [1, 2, 3, 6, 7, 8],
    ('Draft_Copies', 'draft_number'): [1, 2, 3],
    ('Documents_Mailed', 'document_id'): [6, 7, 8],
    ('Ref_Shipping_Agents', 'shipping_agent_code'): ['UP'],
    ('Ref_Document_Types', 'document_type_code'): ['Paper'],
}

GUARANTEED_LITERALS = {
    ('Ref_Shipping_Agents', 'shipping_agent_name'): ['USPS'],
    ('Documents', 'document_status_code'): ['done'],
    ('Documents', 'document_type_code'): ['Paper'],
}

NULL_TARGETS = {
    ('Documents', 'shipping_agent_code'), ('Documents', 'receipt_date'), ('Documents', 'receipt_number'),
    ('Documents', 'other_details'), ('Employees', 'employee_name'), ('Employees', 'other_details'),
    ('Document_Drafts', 'draft_details'), ('Documents_Mailed', 'mailing_date'),
    ('Addresses', 'address_details'), ('Roles', 'role_description'),
}

INT_SMALL_POOL = set()

GROUP_SIZE = {
    ('Document_Drafts', 'document_id'),
    ('Draft_Copies', 'document_id'),
    ('Circulation_History', 'document_id'),
    ('Documents_Mailed', 'document_id'),
    ('Circulation_History', 'draft_number'),
    ('Circulation_History', 'copy_number'),
    ('Employees', 'role_code'),
    ('Roles', 'role_description'),
    ('Roles', 'role_code'),
}

PARENT_GROUP_SIZE = {'Documents': 'document_id'}

DUP_DISTINCT_TARGETS = {
    ('Employees', 'employee_name'),
    ('Circulation_History', 'employee_id'),
    ('Documents', 'document_status_code'),
    ('Documents', 'document_type_code'),
    ('Ref_Shipping_Agents', 'shipping_agent_name'),
}

DUP_DISTINCT_SHARE = 0.30


def table_size(table: str, rng) -> int:
    """Spec base size, jittered upward by 0/1 so instances differ but never shrink below spec."""
    base = TABLE_SIZES.get(table)
    if base is None:
        return 0
    return base + rng.randint(0, 1)
