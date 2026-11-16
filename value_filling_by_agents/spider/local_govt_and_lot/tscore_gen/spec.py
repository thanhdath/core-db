"""Specification constants: enum pools, per-column pattern targets, table sizes, NULL targets."""
import datetime as dt

ENUM_POOLS = {
    ('Properties', 'property_type_code'): ['apartment', 'house', 'flat'],
    ('Services', 'service_type_code'): ['Cleanning', 'Check', 'Moving Out', 'Pay bills'],
    ('Services', 'service_details'): ['Satisfied', 'Unsatisfied'],
    ('Things', 'Type_of_Thing_Code'): ['Electronics', 'Commen', 'Furniture'],
    ('Things', 'service_type_code'): ['Check', 'Cleanning'],
    ('Things', 'service_details'): ['Satisfied', 'Unsatisfied'],
    ('Residents_Services', 'other_details'): ['Satisfied', 'Unsatisfied'],
    ('Customer_Event_Notes', 'service_type_code'): ['Cleanning', 'Check'],
    ('Timed_Status_of_Things', 'Status_of_Thing_Code'): ['Open', 'Close', 'In Progress'],
}

NEAR_VARIANTS = {
    ('Organizations', 'organization_details'): ['Denesik and Sons Party', 'denesik and sons party'],
    ('Timed_Status_of_Things', 'Status_of_Thing_Code'): ['Close', 'close'],
    ('Residents', 'other_details'): ['Miss Naomie Osinski', 'Miss Alanis Lockman', 'Miss', 'Mi',
                                      'Miss Chaim Swaniawski', 'Miss Jess Wyman'],
}

BOUNDARY_DATES = {
    ('Timed_Status_of_Things', 'Date_and_Date'): [
        '2017-06-18 00:00:00', '2017-06-19 00:00:00', '2017-06-20 00:00:00',
        '2017-06-19 02:59:21', '2017-06-19 02:59:20', '2017-06-19 02:59:22',
    ],
}

LIKE_PATTERNS = {
    ('Residents', 'other_details'): ['%Miss%', '%Mi%'],
}

BASE_SIZES = {
    'Customers': 15, 'Properties': 15, 'Residents': 15, 'Organizations': 3, 'Services': 15,
    'Residents_Services': 11, 'Things': 15, 'Customer_Events': 13, 'Customer_Event_Notes': 13,
    'Timed_Status_of_Things': 18, 'Timed_Locations_of_Things': 15,
}

NULL_TARGETS = [
    ('Customer_Events', 'customer_id'), ('Customer_Events', 'date_moved_in'),
    ('Customer_Events', 'property_id'), ('Customer_Events', 'resident_id'),
    ('Residents_Services', 'date_moved_in'), ('Residents_Services', 'property_id'),
    ('Residents_Services', 'date_requested'), ('Residents_Services', 'date_provided'),
    ('Residents_Services', 'other_details'), ('Organizations', 'parent_organization_id'),
    ('Services', 'service_details'),
]

GROUP_SIZE_TARGETS = {
    ('Customers', 'customer_details'): [1, 2, 3],
    ('Customer_Events', 'customer_id'): [1, 2, 3],
    ('Customer_Events', 'property_id'): [1, 2, 3],
    ('Residents', 'property_id'): [1, 2, 3],
    ('Services', 'service_details'): [1, 2, 3],
    ('Residents_Services', 'resident_id'): [1, 2, 3],
    ('Customer_Event_Notes', 'Customer_Event_ID'): [1, 2, 3],
    ('Residents', 'other_details'): [1, 2, 3],
}

DISTINCT_DUP_TARGETS = [
    ('Customers', 'customer_details'),
    ('Residents', 'other_details'),
]

DISTINCT_DUP_SHARE = 0.35

DATE_LO = dt.datetime(2015, 1, 1)
DATE_HI = dt.datetime(2018, 12, 31)
DATE_FMT = '%Y-%m-%d %H:%M:%S'

NAME_POOL = [
    'Mr. Raul Prosacco', 'Esteban Senger', 'Tyrique Durgan II', 'Malcolm Farrell',
    'Sabryna Moore PhD', 'Dr. Haylie Hilll III', 'Monty Sauer III', 'Jayme Marquardt',
    'Anderson Batz', 'Miss Naomie Osinski', 'Jess Wyman', 'Miss Alanis Lockman',
    'Prof. Arvel Kozey', 'Chaim Swaniawski', 'Elroy Schuster', 'Prof. Nasir Hoppe',
]
ADDRESS_POOL = [
    '85456 Annie Lodge Suite 449', '2580 Yundt Plains', '5983 Fleta Throughway',
    '322 Johnston Parkway Suite 422', '5384 Sipes Land Apt. 344', '04164 Raul Stream',
    '54591 Bernard Ridges Suite 864', '7713 Bode Burgs Apt. 113',
]
ORG_POOL = ['Reinger, Hudson and Nolan Group', 'Denesik and Sons Party', 'Robel-Schulist Group']
LOCATION_POOL = [
    '064 Charles Mou', '288 Lang Ferry', '854 Keeling Sho', '1316 Morgan Spr',
    '192 Kub Rapids', '4667 Kellen Fie', '1313 Sawayn Riv', '94425 Nellie Kn',
]
DETAIL_POOL = ['USA', 'Satisfied', 'Unsatisfied']
