"""Specification tables: enums, boundary literals, NULL targets, per-column patterns."""

ENUMS = {
    ('Ref_Hotel_Star_Ratings', 'star_rating_code'): ['1', '2', '3', '4', '5'],
    ('Ref_Attraction_Types', 'Attraction_Type_Code'): ['2', '3', '5', '6', '9'],
    ('Hotels', 'star_rating_code'): ['1', '2', '3', '4', '5'],
    ('Tourist_Attractions', 'How_to_Get_There'): ['bus', 'walk', 'shuttle'],
    ('Hotels', 'pets_allowed_yn'): ['0', '1', ''],
}

BOUNDARY_TEXT = {
    ('Locations', 'Address'): ['254 Ottilie Junction', '254 ottilie junction',
                               '660 Shea Crescent', '660 shea crescent',
                               '254 Ottile Junction', '254 ottile junction'],
    ('Tourist_Attractions', 'How_to_Get_There'): ['walk', 'bus', 'shuttle'],
    ('Visitors', 'Tourist_Details'): ['Rosalind', 'rosalind', 'Alison', 'alison'],
    ('Features', 'Feature_Details'): ['park', 'PARK', 'shopping', 'SHOPPING'],
}

RESTRICTED_DOMAIN = {
    ('Tourist_Attractions', 'How_to_Get_There'): {'bus', 'walk', 'shuttle'},
}

BOUNDARY_NUM = {
    ('Hotels', 'star_rating_code'): (['5', '4', '3'], 1),
}

NULL_TARGETS = [
    ('Hotels', 'price_range'), ('Hotels', 'pets_allowed_yn'), ('Hotels', 'other_hotel_details'),
    ('Locations', 'Other_Details'), ('Locations', 'Location_Name'), ('Locations', 'Address'),
    ('Tourist_Attractions', 'Description'), ('Tourist_Attractions', 'Opening_Hours'),
    ('Tourist_Attractions', 'Other_Details'), ('Tourist_Attractions', 'How_to_Get_There'),
    ('Tourist_Attractions', 'Name'),
    ('Photos', 'Description'), ('Photos', 'Other_Details'), ('Photos', 'Name'),
    ('Staff', 'Other_Details'), ('Staff', 'Name'),
    ('Royal_Family', 'Royal_Family_Details'), ('Museums', 'Museum_Details'),
    ('Shops', 'Shop_Details'), ('Street_Markets', 'Market_Details'),
    ('Theme_Parks', 'Theme_Park_Details'), ('Visitors', 'Tourist_Details'),
    ('Features', 'Feature_Details'),
    ('Ref_Attraction_Types', 'Attraction_Type_Description'),
    ('Ref_Hotel_Star_Ratings', 'star_rating_description'),
]

NULL_SHARE = set(NULL_TARGETS)

DUP_SHARE = {
    ('Locations', 'Location_Name'), ('Staff', 'Name'), ('Photos', 'Name'),
    ('Photos', 'Description'), ('Shops', 'Shop_Details'), ('Street_Markets', 'Market_Details'),
    ('Visits', 'Visit_Date'),
}

GROUP_SIZES = [
    ('Tourist_Attractions', 'Name'),
    ('Ref_Attraction_Types', 'Attraction_Type_Description'),
]

AGG_BOUNDARY = [
    ('Tourist_Attractions', 'Name'),
    ('Visits', 'Visit_Details'),
]

FK_GROUP_SIZES = [
    ('Tourist_Attractions', 'Attraction_Type_Code'),
    ('Tourist_Attractions', 'Tourist_Attraction_ID'),
    ('Visits', 'Tourist_Attraction_ID'),
]
FK_AGG_BOUNDARY = [
    ('Tourist_Attractions', 'Tourist_Attraction_ID'),
    ('Visits', 'Tourist_Attraction_ID'),
]

UNMATCHED_PARENT = [
    ('Ref_Hotel_Star_Ratings', 'star_rating_code'),
    ('Locations', 'Location_ID'),
    ('Tourist_Attractions', 'Tourist_Attraction_ID'),
    ('Visitors', 'Tourist_ID'),
]

TIE_ORDER = [('Museums', 'Museum_Details'), ('Locations', 'Location_Name'), ('Staff', 'Name')]

TABLE_SIZES = {
    'Ref_Hotel_Star_Ratings': 5, 'Ref_Attraction_Types': 5, 'Features': 5, 'Locations': 15,
    'Visitors': 20, 'Hotels': 20, 'Tourist_Attractions': 15, 'Street_Markets': 2, 'Shops': 4,
    'Museums': 3, 'Royal_Family': 2, 'Theme_Parks': 3, 'Visits': 20, 'Photos': 15, 'Staff': 20,
    'Tourist_Attraction_Features': 18,
}

PK_IS_FK = {
    'Museums': 'Museum_ID', 'Shops': 'Shop_ID', 'Street_Markets': 'Market_ID',
    'Royal_Family': 'Royal_Family_ID', 'Theme_Parks': 'Theme_Park_ID',
}

FORMULAS = {
    ('Hotels', 'star_rating_code'): "IN ('1','2','3','4','5')",
    ('Hotels', 'pets_allowed_yn'): "IS NULL OR IN ('0','1','')",
    ('Hotels', 'price_range'): "IS NULL OR >= 0",
    ('Ref_Hotel_Star_Ratings', 'star_rating_code'): "IN ('1','2','3','4','5')",
    ('Ref_Attraction_Types', 'Attraction_Type_Code'): "IN ('2','3','5','6','9')",
    ('Tourist_Attractions', 'How_to_Get_There'): "IS NULL OR IN ('bus','walk','shuttle')",
    ('Visits', 'Visit_Date'): "IS NOT NULL",
    ('Visits', 'Visit_Details'): "IS NOT NULL",
}
