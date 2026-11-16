"""Specification constants implemented by construction in the samplers."""

ENUMS = {
    ('Customers', 'customer_status_code'): ['Good Customer', 'Bad Customer'],
    ('Customer_Payments', 'payment_method_code'): ['Direct Debit', 'Credit Card'],
    ('Lessons', 'lesson_status_code'): ['Completed', 'Cancelled'],
    ('Vehicles', 'vehicle_details'): ['Van', 'Truck', 'Car'],
}

BOUNDARY_TEXT = {
    ('Addresses', 'city'): ['Lockmanfurt', 'lockmanfurt', 'Damianfort', 'damianfort'],
    ('Customers', 'first_name'): ['Carole', 'carole'],
    ('Customers', 'last_name'): ['Bernhard', 'bernhard'],
    ('Staff', 'first_name'): ['Ludie', 'ludie', 'Janessa', 'janessa'],
    ('Staff', 'last_name'): ['Sawayn', 'sawayn'],
    ('Lessons', 'lesson_time'): ['', 'x'],
}

GIVEN_NAMES = ['Carole', 'Genevieve', 'Clara', 'Jordy', 'Millie', 'Amya', 'Marina', 'Dianna',
               'Janessa', 'Camylle', 'Kaitlin', 'Rebekah', 'Jedidiah', 'Eulalia', 'Queenie',
               'Titus', 'Ludie', 'Amara', 'Icie', 'Stephania', 'Sherwood', 'Dejon', 'Tre',
               'Madelyn', 'Duane', 'Everette', 'Jana', 'Hilario', 'Asha', 'Citlalli', 'Judy']
SURNAMES = ['Bernhard', 'Terry', 'Ortiz', 'Tromp', 'Bruen', 'Spinka', 'Koelpin', 'Trantow',
            'Sawayn', 'Weissnat', 'Mertz', 'Hermann', 'Herzog', 'Maggio', 'Macejkovic',
            'Durgan', 'Goyette', 'Huel', 'Spoorer', 'Franeki', 'Kilback', 'Kozey', 'Mayert',
            'Roberts', 'Senger', 'Bogisich', 'Kling', 'Nader', 'Constantin', 'Santos']
CITIES = ['Port Melyssa', 'Hagenesfurt', 'Lake Elaina', 'Buckridgehaven', 'Powlowskichester',
          'Elviebury', 'Lockmanfurt', 'Lake Rafaela', 'Damianfort', 'lockmanfurt', 'damianfort']
STATES = ['Georgia', 'Kentucky', 'Oregon', 'Ohio', 'Connecticut', 'Washington',
          'WestVirginia', 'Maine', 'Texas', 'Florida', 'Nevada']
COUNTRIES = ['USA']
STREET_WORDS = ['Stroman', 'Quigley', 'Zoe', 'O\'Hara', 'Frederik', 'Kallie', 'Baumbach',
                'Dejah', 'Main', 'Oak', 'Pine', 'Maple']
STREET_SUFFIX = ['Passage', 'Island', 'Alley', 'Drive', 'Ridge', 'Tunnel', 'Well', 'Suite',
                 'Street', 'Avenue', 'Road']

NULL_SHARE_COLUMNS = {
    ('Customers', 'amount_outstanding'),
    ('Lessons', 'lesson_time'), ('Lessons', 'lesson_date'), ('Lessons', 'price'),
    ('Staff', 'date_left_staff'), ('Staff', 'date_of_birth'), ('Staff', 'date_joined_staff'),
    ('Customers', 'date_of_birth'), ('Customers', 'date_became_customer'),
    ('Customers', 'first_name'), ('Customers', 'last_name'), ('Customers', 'email_address'),
    ('Customers', 'phone_number'), ('Customers', 'cell_mobile_phone_number'),
    ('Addresses', 'line_1_number_building'), ('Addresses', 'city'),
    ('Addresses', 'zip_postcode'), ('Addresses', 'state_province_county'),
    ('Addresses', 'country'), ('Staff', 'nickname'), ('Staff', 'first_name'),
    ('Staff', 'middle_name'), ('Staff', 'last_name'), ('Vehicles', 'vehicle_details'),
    ('Customer_Payments', 'amount_payment'),
}

NULLABLE_FK_COLUMNS = {('Lessons', 'staff_id')}

DUPLICATE_COLUMNS = {
    ('Addresses', 'country'), ('Addresses', 'state_province_county'),
    ('Addresses', 'zip_postcode'), ('Customers', 'date_of_birth'),
    ('Staff', 'nickname'), ('Lessons', 'vehicle_id'),
}

GROUP_SIZE_COLUMNS = {
    ('Customer_Payments', 'customer_id'), ('Vehicles', 'vehicle_details'),
}

DIFFERENT_VALUE_COLUMNS = {
    ('Customers', 'date_became_customer'),
}

UNMATCHED_JOIN = {
    'Addresses': 'address_id',
    'Customers': 'customer_id',
    'Staff': 'staff_id',
}

AGGREGATE_BOUNDARY = [
    ('Customers', 'customer_id', 'Customer_Payments', 'customer_id', 'customer_id'),
    ('Customers', 'customer_id', 'Customer_Payments', 'customer_id', 'amount_payment'),
]

TABLE_SIZES = {
    'Addresses': 15, 'Staff': 15, 'Vehicles': 6, 'Customers': 15,
    'Customer_Payments': 15, 'Lessons': 15,
}
