"""Specification constants (tscore_gen/specification.json) implemented by construction."""
import json
import os

TABLE_SIZES = {
    'Apartment_Buildings': 15,
    'Apartments': 15,
    'Apartment_Facilities': 7,
    'Guests': 15,
    'Apartment_Bookings': 15,
    'View_Unit_Status': 20,
}

ENUMS = {
    ('Apartment_Buildings', 'building_description'): ['Studio', 'Flat', 'Duplex'],
    ('Apartments', 'apt_type_code'): ['Flat', 'Studio', 'Duplex'],
    ('Apartment_Facilities', 'facility_code'): ['Boardband', 'Gym', 'Swimming Pool', 'Cable TV'],
    ('Guests', 'gender_code'): ['M', 'F', 'U'],
    ('Apartment_Bookings', 'booking_status_code'): ['Provisional', 'Confirmed'],
}

BOUNDARY_TEXT = {
    ('Apartment_Buildings', 'building_short_name'): ['Columbus Square', 'columbus square'],
    ('Apartment_Buildings', 'building_full_name'): ['Columbus Square', 'columbus square'],
    ('Apartments', 'apt_type_code'): ['Duplex', 'duplex'],
    ('Apartments', 'apt_number'): ['Suite 634', 'suite 634'],
    ('Apartment_Bookings', 'booking_status_code'): ['Confirmed', 'confirmed', 'Provisional', 'provisional'],
}

BOUNDARY_NUMERIC = {
    ('Apartments', 'bathroom_count'): [0, 1, 2],
    ('Apartments', 'bedroom_count'): [2, 3, 4],
}

LITERAL_POOLS = {
    ('Apartment_Buildings', 'building_manager'): ['Kyle', 'Brenden', 'Emma'],
}

NUMERIC_RANGES = {
    ('Apartments', 'bathroom_count'): (1, 3),
    ('Apartments', 'bedroom_count'): (3, 6),
}

ROOM_COUNT_RANGE = (3, 9)

NULL_TARGETS = [
    ('Apartment_Bookings', 'apt_id'),
    ('View_Unit_Status', 'apt_id'),
    ('View_Unit_Status', 'apt_booking_id'),
    ('View_Unit_Status', 'available_yn'),
]

DUPLICATE_SHARE = 0.3

DATETIME_LO = '2015-01-01 00:00:00'
DATETIME_HI = '2018-12-31 23:59:59'


def load_specification(path=None):
    """Load specification.json if present, else return the built-in constants."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'specification.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'table_sizes_per_instance': TABLE_SIZES,
        'enums': {'%s.%s' % k: v for k, v in ENUMS.items()},
        'boundary_text': {'%s.%s' % k: v for k, v in BOUNDARY_TEXT.items()},
        'boundary_numeric': {'%s.%s' % k: v for k, v in BOUNDARY_NUMERIC.items()},
        'literal_pools': {'%s.%s' % k: v for k, v in LITERAL_POOLS.items()},
        'numeric_ranges': {'%s.%s' % k: list(v) for k, v in NUMERIC_RANGES.items()},
        'room_count_range': list(ROOM_COUNT_RANGE),
        'null_targets': ['%s.%s' % k for k in NULL_TARGETS],
        'duplicate_share': DUPLICATE_SHARE,
        'datetime_lo': DATETIME_LO,
        'datetime_hi': DATETIME_HI,
    }
