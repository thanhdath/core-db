"""Generation specification, encoded as data (no rule is ever evaluated with SQL)."""

TABLE_SIZES = {
    'Addresses': 15, 'Locations': 15, 'Products': 15, 'Parties': 7, 'Assets': 3,
    'Channels': 15, 'Finances': 15, 'Events': 15, 'Products_in_Events': 15,
    'Parties_in_Events': 15, 'Agreements': 15, 'Assets_in_Events': 12,
}

ENUMS = {
    ('Products', 'Product_Type_Code'): ['Books', 'Food', 'Clothes', 'Electronics'],
    ('Events', 'Event_Type_Code'): ['Trade Show', 'Press Conferenc', 'Ceremonies',
                                    'Seminar', 'Conference'],
    ('Parties_in_Events', 'Role_Code'): ['Organizer', 'Participant'],
}

PRICE_LO, PRICE_HI = 0.01, 5000.00
PRICE_DECIMALS = 4

NULL_SHARE = 0.10

PRICE_TIE_ROWS = 2
PRICE_DISTINCT_MIN = 3
TYPE_CODE_DUP_SHARE = 0.30
GROUP_SIZE_TARGETS = (1, 2, 3)
UNMATCHED_PARENT_ROWS = 1

GROUP_SIZE_COLUMNS = [
    ('Products', 'Product_Name'),
    ('Products', 'Product_Type_Code'),
    ('Products_in_Events', 'Product_ID'),
]

NULLABLE_COLUMNS = [
    ('Products', 'Product_Price'),
    ('Products', 'Product_Type_Code'),
    ('Products', 'Product_Name'),
    ('Events', 'Address_ID'),
    ('Events', 'Event_Type_Code'),
    ('Parties_in_Events', 'Role_Code'),
    ('Addresses', 'address_details'),
    ('Assets', 'Other_Details'),
    ('Channels', 'Other_Details'),
    ('Finances', 'Other_Details'),
    ('Locations', 'Other_Details'),
    ('Parties', 'Party_Details'),
]
