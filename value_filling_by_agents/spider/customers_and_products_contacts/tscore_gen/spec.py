"""Specification constants (generation specification, per-column exceptions, semantic rules)."""

TABLE_SIZES = {
    'Addresses': 15,
    'Contacts': 15,
    'Customer_Address_History': 20,
    'Customer_Orders': 15,
    'Customers': 15,
    'Order_Items': 15,
    'Products': 15,
}

ENUMS = {
    ('Addresses', 'country'): ['USA', 'usa'],
    ('Customer_Orders', 'order_status_code'): ['Completed', 'Part', 'completed', 'part'],
    ('Customers', 'payment_method_code'): ['Credit Card', 'Direct Debit'],
    ('Products', 'product_type_code'): ['Hardware', 'Clothes'],
    ('Contacts', 'gender'): ['male', 'female'],
}

COMPARISON_LITERALS = {
    ('Addresses', 'country'): ['USA', 'usa'],
    ('Customer_Orders', 'order_status_code'): ['Completed', 'Part', 'completed', 'part'],
}

DISTINCT_DUP_COLUMNS = {
    ('Customers', 'customer_name'),
    ('Customers', 'customer_phone'),
    ('Customers', 'payment_method_code'),
    ('Products', 'product_type_code'),
    ('Addresses', 'city'),
}

GROUP_SIZE_COLUMNS = {
    ('Customers', 'customer_id'),
    ('Customers', 'customer_name'),
    ('Customers', 'customer_phone'),
}

TIE_COLUMNS = {
    ('Customers', 'customer_id'),
    ('Customers', 'customer_name'),
    ('Customers', 'customer_phone'),
    ('Customers', 'customer_number'),
}

UNMATCHED_PARENT_COLUMNS = {
    ('Customers', 'customer_id'),
    ('Products', 'product_id'),
    ('Customer_Orders', 'customer_id'),
    ('Order_Items', 'product_id'),
    ('Order_Items', 'order_id'),
}

DIFFERENT_VALUE_COLUMNS = {
    ('Order_Items', 'order_quantity'),
}

NULL_TARGETS = {
    ('Addresses', 'line_1_number_building'),
    ('Addresses', 'city'),
    ('Addresses', 'zip_postcode'),
    ('Addresses', 'state_province_county'),
    ('Addresses', 'country'),
    ('Contacts', 'gender'),
    ('Contacts', 'first_name'),
    ('Contacts', 'last_name'),
    ('Contacts', 'contact_phone'),
    ('Customer_Address_History', 'date_to'),
    ('Customer_Orders', 'order_status_code'),
    ('Customers', 'payment_method_code'),
    ('Customers', 'customer_number'),
    ('Customers', 'customer_name'),
    ('Customers', 'customer_address'),
    ('Customers', 'customer_phone'),
    ('Customers', 'customer_email'),
    ('Order_Items', 'order_quantity'),
    ('Products', 'product_type_code'),
    ('Products', 'product_name'),
    ('Products', 'product_price'),
}

NONNEGATIVE_COLUMNS = {('Products', 'product_price')}
QUANTITY_COLUMN = ('Order_Items', 'order_quantity')
QUANTITY_NONNUMERIC = 'male'
DATE_ORDER = ('Customer_Address_History', 'date_from', 'date_to')

FIRST_NAMES = ['Cierra', 'Jennifer', 'Carli', 'Gustave', 'Danika', 'Rachelle', 'Sid', 'Adella',
               'Kayley', 'Sterling', 'Buford', 'Caterina', 'Raymond', 'Cheyenne', 'Cecelia', 'Brenna']
LAST_NAMES = ['Collins', 'Doyle', 'Blick', 'Ebert', 'Bauch', 'Stamm', 'Legros', 'Streich',
              'Smith', 'Johnson', 'Brown', 'Miller', 'Davis', 'Wilson', 'Moore', 'Taylor']
CITIES = ['Hertafurt', 'Edgardoberg', 'Gilbertmouth', 'Lake Floyd', 'Gibsonfurt', 'North Jairo',
          'East Rickey', 'West Kaiatown', 'Springfield', 'Riverton', 'Fairview', 'Clinton']
STATES = ['Nevada', 'Colorado', 'Virginia', 'Oklahoma', 'District of Columbia', 'Maryland',
          'Louisiana', 'Oregon', 'Texas', 'Florida', 'Ohio', 'Maine']
STREET_WORDS = ['Canyon', 'Highway', 'Ridge', 'Green', 'Greens', 'Path', 'Fort', 'Islands',
                'Isle', 'Crossroad', 'Way', 'Expressway', 'Stravenue', 'Street', 'Vista', 'Ports']
PRODUCT_NAMES = ['Apple', 'jcrew', 'Sony', 'gucci', 'Nike', 'Adidas', 'Dell', 'HP', 'Canon', 'LG']
