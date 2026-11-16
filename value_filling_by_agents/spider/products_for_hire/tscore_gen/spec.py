"""Specification implemented by construction (tscore_gen/specification.json -> this module)."""
import datetime as dt

DT_FMT = '%Y-%m-%d %H:%M:%S'
RANGE_LO = dt.datetime(2015, 1, 1)
RANGE_HI = dt.datetime(2018, 12, 31, 23, 59, 59)

TABLE_SIZES = {
    'Discount_Coupons': 15,
    'Customers': 15,
    'Bookings': 15,
    'Products_for_Hire': 5,
    'Payments': 15,
    'Products_Booked': 12,
    'View_Product_Availability': 4,
}

ENUMS = {
    ('Bookings', 'booking_status_code'): ['Provisional', 'Confirmed'],
    ('Bookings', 'returned_damaged_yn'): ['0', '1'],
    ('Customers', 'gender_mf'): ['0', '1'],
    ('Payments', 'payment_type_code'): ['Check', 'Cash', 'Credit Card', 'Direct Debit'],
    ('Payments', 'amount_paid_in_full_yn'): ['0', '1'],
    ('Products_for_Hire', 'product_type_code'): ['Cutlery', 'Din_Plates'],
    ('Products_Booked', 'returned_yn'): ['0', '1'],
    ('Products_Booked', 'returned_late_yn'): ['0', '1'],
    ('View_Product_Availability', 'available_yn'): ['0', '1'],
}

BOUNDARY_STRINGS = {
    ('Products_for_Hire', 'product_name'): ['Book collection A', 'Book collection B', 'Book collection C',
                                            'book collection a', 'DVD collection A', 'DVD collection B'],
    ('Customers', 'good_or_bad_customer'): ['good', 'bad', 'GOOD', 'BAD'],
}
BOUNDARY_NUMBERS = {
    ('Products_for_Hire', 'daily_hire_cost'): [19.99, 20.0, 20.01, 20.99, 21.0, 21.01],
}

LIKE_BASES = {
    ('Products_for_Hire', 'product_name'): ['Book', 'Boo', 'Bool', 'Book x', 'book', 'Bop', 'Boo x', 'boo'],
}

DUPLICATE_SHARE = {
    ('Discount_Coupons', 'coupon_amount'): 0.30,
    ('Payments', 'payment_date'): 0.35,
}

GROUP_SIZES = [
    ('Customers', 'first_name'),
    ('Customers', 'date_last_hire'),
    ('Payments', 'booking_id'),
]
GROUP_SIZES_MIN = 6

DIFFERENT_VALUES = [
    ('Payments', 'amount_due', 'booking_id'),
    ('Products_Booked', 'product_id', 'booking_id'),
    ('Products_Booked', 'booked_count', 'booking_id'),
]

ORDER_TIES = [
    ('Products_for_Hire', 'product_description'),
]

PARENT_WITHOUT_CHILD = [
    ('Products_for_Hire', 'product_id', 'Products_Booked', 'product_id'),
]

NONNEGATIVE = [
    ('Discount_Coupons', 'coupon_amount'),
    ('Bookings', 'amount_payable'), ('Bookings', 'amount_of_discount'),
    ('Bookings', 'amount_outstanding'), ('Bookings', 'amount_of_refund'),
    ('Payments', 'amount_due'), ('Payments', 'amount_paid'),
    ('Products_for_Hire', 'daily_hire_cost'),
    ('Products_Booked', 'booked_amount'),
]
POSITIVE = [('Products_Booked', 'booked_count')]
DATE_GE = [('Customers', 'date_last_hire', 'date_became_customer'),
           ('Bookings', 'booking_end_date', 'booking_start_date')]

NOT_REQUIRED = ['cross_table_amount_consistency']

NULL_SHARE_FALLBACK = 0.1


def rule_value_floor(table: str, column: str):
    """Forced minimum for a numeric column under a nonneg/positive rule, else None."""
    for t, c in NONNEGATIVE:
        if t == table and c == column:
            return 0.0
    for t, c in POSITIVE:
        if t == table and c == column:
            return 1.0
    return None


def datetime_floor(table: str, column: str):
    """Name of the sibling datetime column this one must be >= (or None)."""
    for t, hi_col, lo_col in DATE_GE:
        if t == table and hi_col == column:
            return lo_col
    return None
