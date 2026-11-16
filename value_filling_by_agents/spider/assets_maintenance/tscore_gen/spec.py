"""Specification constants (generation specification, by construction)."""
import datetime as dt

ENUMS = {
    ('Third_Party_Companies', 'company_type'): ['Maintenance Contractor', 'Supplier'],
    ('Parts', 'chargeable_yn'): ['0', '1'],
    ('Skills', 'skill_code'): ['ELEC', 'MECH', 'TV'],
    ('Skills', 'skill_description'): ['Electrical', 'Mechanical', 'TV, Video'],
    ('Staff', 'gender'): ['0', '1'],
    ('Engineer_Visits', 'fault_status'): ['Waiting', 'Return', 'Fixed', 'Reported'],
    ('Fault_Log_Parts', 'fault_status'): ['Waiting', 'Return', 'Fixed', 'Reported'],
}

NULL_TARGETS = [
    ('Engineer_Visits', 'contact_staff_id'),
    ('Engineer_Visits', 'visit_start_datetime'),
    ('Engineer_Visits', 'visit_end_datetime'),
    ('Engineer_Visits', 'other_visit_details'),
    ('Assets', 'asset_details'),
    ('Assets', 'asset_make'),
    ('Assets', 'asset_model'),
    ('Assets', 'asset_acquired_date'),
    ('Assets', 'asset_disposed_date'),
    ('Assets', 'other_asset_details'),
    ('Maintenance_Engineers', 'first_name'),
    ('Maintenance_Engineers', 'last_name'),
    ('Maintenance_Engineers', 'other_details'),
    ('Staff', 'staff_name'),
    ('Staff', 'gender'),
    ('Staff', 'other_staff_details'),
    ('Parts', 'part_name'),
    ('Parts', 'chargeable_yn'),
    ('Parts', 'chargeable_amount'),
    ('Parts', 'other_part_details'),
    ('Fault_Log', 'fault_log_entry_datetime'),
    ('Fault_Log', 'fault_description'),
    ('Fault_Log', 'other_fault_details'),
    ('Maintenance_Contracts', 'contract_start_date'),
    ('Maintenance_Contracts', 'contract_end_date'),
    ('Maintenance_Contracts', 'other_contract_details'),
    ('Part_Faults', 'fault_short_name'),
    ('Part_Faults', 'fault_description'),
    ('Part_Faults', 'other_fault_details'),
    ('Skills', 'skill_code'),
    ('Skills', 'skill_description'),
    ('Third_Party_Companies', 'company_name'),
    ('Third_Party_Companies', 'company_address'),
    ('Third_Party_Companies', 'other_company_details'),
]
NULL_SHARE_MIN, NULL_SHARE_MAX = 0.05, 0.30

DUPLICATE_COLUMNS = [
    ('Assets', 'asset_model'),
    ('Assets', 'asset_make'),
    ('Maintenance_Engineers', 'last_name'),
    ('Skills', 'skill_code'),
    ('Skills', 'skill_description'),
]
DUP_SHARE_MIN, DUP_SHARE_MAX = 0.20, 0.50

GROUP_SIZE_COLUMNS = [
    ('Parts', 'part_name'),
    ('Maintenance_Engineers', 'company_id'),
    ('Staff', 'staff_name'),
    ('Staff', 'other_staff_details'),
    ('Maintenance_Contracts', 'contract_end_date'),
    ('Fault_Log', 'fault_description'),
    ('Fault_Log', 'fault_log_entry_datetime'),
    ('Engineer_Visits', 'contact_staff_id'),
    ('Assets', 'supplier_company_id'),
    ('Skills', 'skill_description'),
    ('Staff', 'gender'),
]

AGGREGATE_BOUNDARY = {
    ('Assets', 'asset_details'): ('lt', 2),
    ('Parts', 'part_name'): ('gt', 2),
}
PARTS_FAULT_GROUP_MIN = 3

TIE_FAULT_LOG_PARTS = True

ACQUIRED_DATE_DISTINCT = True

UNMATCHED = [
    ('Engineer_Visits', 'engineer_id', 'Maintenance_Engineers', 'engineer_id'),
    ('Part_Faults', 'part_fault_id', 'Skills_Required_To_Fix', 'part_fault_id'),
    ('Part_Faults', 'part_id', 'Parts', 'part_id'),
    ('Asset_Parts', 'part_id', 'Parts', 'part_id'),
    ('Fault_Log_Parts', 'fault_log_entry_id', 'Fault_Log', 'fault_log_entry_id'),
    ('Skills_Required_To_Fix', 'part_fault_id', 'Part_Faults', 'part_fault_id'),
]

DATE_LO = dt.datetime(2017, 1, 1)
DATE_HI = dt.datetime(2018, 12, 31, 23, 59, 59)
DATE_FMT = '%Y-%m-%d %H:%M:%S'

FORMULAS = [
    ('Maintenance_Contracts', 'contract_end_date', 'Maintenance_Contracts', 'contract_start_date'),
    ('Assets', 'asset_disposed_date', 'Assets', 'asset_acquired_date'),
    ('Engineer_Visits', 'visit_end_datetime', 'Engineer_Visits', 'visit_start_datetime'),
]
NONNEGATIVE = [('Parts', 'chargeable_amount')]
POSITIVE_PK = ['Assets', 'Maintenance_Contracts', 'Fault_Log', 'Engineer_Visits',
               'Part_Faults', 'Maintenance_Engineers', 'Staff', 'Third_Party_Companies',
               'Skills', 'Parts']

TABLE_SIZES = {
    'Third_Party_Companies': 15, 'Maintenance_Contracts': 15, 'Parts': 3, 'Skills': 3,
    'Staff': 15, 'Assets': 15, 'Asset_Parts': 15, 'Maintenance_Engineers': 15,
    'Engineer_Skills': 20, 'Fault_Log': 15, 'Engineer_Visits': 15, 'Part_Faults': 15,
    'Fault_Log_Parts': 15, 'Skills_Required_To_Fix': 15,
}

COMPANY_NAMES = ['Langworth-Funk', 'McDermott Group', 'Schuppe-Carroll', 'Dooley-Langosh',
                 'Dooley and Sons', 'Grimes, Mosciski and Renner', 'Weimann-Swift',
                 'Glover-Vandervort', 'Kutch LLC', 'Bode Inc', 'Hahn Group', 'Rath PLC']
COMPANY_ADDRESSES = ['615 Jacobs Mews', '873 Conrad Creek Apt. 286', '066 Bechtelar Ridge',
                     '9576 Jacynthe Point Suite 747', '84631 Rosenbaum Well Suite 727',
                     '9405 Leffler Hollow Apt. 753', '016 Kaitlyn Fall Suite 236',
                     '51515 Conn Corner Suite 696', '12 Oak Street', '99 Pine Road']
COUNTRIES = ['Uganda', 'China', 'United Arab Emirates', 'Albania', 'Palestinian Territory',
             'Kiribati', 'Egypt', 'Ethiopia', 'Peru', 'Norway']
FIRST_NAMES = ['Etha', 'Clemens', 'Samanta', 'Lorine', 'Manley', 'Courtney', 'Josie', 'Nellie',
               'Ada', 'Boris', 'Cora', 'Dmitri']
LAST_NAMES = ['Reinger', 'Orn', 'Hauck', 'Morar', 'Grady', 'Adams', 'Harvey', 'Hirthe',
              'Klein', 'Lowe', 'Mills', 'Nolan']
STAFF_NAMES = ['Audreanne', 'Berneice', 'Helena', 'Edmond', 'Leola', 'Rodger', 'Kadin',
               'Christophe', 'Della', 'Emil', 'Fiona', 'Gus']
PART_NAMES = ['top', 'middle', 'package', 'base', 'cover']
ASSET_DETAILS = ['dell laptop1', 'dell laptop2', 'dell laptop3', 'dell laptop4', 'dell laptop5',
                 'monitor1', 'monitor2', 'monitor3', 'printer1', 'scanner1']
ASSET_MAKES = ['PT', 'IN', 'IT', 'RU', 'DE', 'CN', 'GB', 'FR', 'US', 'JP']
ASSET_MODELS = ['58 ub', '35 xt', '63 ok', '69 uv', '90 oq', '91 ub', '27 du', '94 kg',
                '11 aa', '22 bb']
FAULT_DESCRIPTIONS = ['system error', 'failed parts', 'overheating', 'no power']
FAULT_SHORT = ['PW', 'TW', 'MW', 'OW']
FAULT_LONG = ['Package Wrong', 'Top Parts Wrong', 'Medium Scale Wrong', 'Other Wrong']
OTHER_DETAILS = ['Bad condition', 'Skilled', 'Manager', 'Woker', 'New', 'Old']
