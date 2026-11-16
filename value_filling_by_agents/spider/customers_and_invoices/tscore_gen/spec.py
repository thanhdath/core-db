"""Specification constants (tscore_gen/specification.json) as plain Python data."""

TABLE_SIZES = {
    'Customers': 20, 'Product_Categories': 4, 'Products': 20, 'Orders': 24,
    'Accounts': 20, 'Invoices': 24, 'Order_Items': 30, 'Invoice_Line_Items': 30,
    'Financial_Transactions': 24,
}

ENUMS = {
    ('Customers', 'gender'): ['0', '1'],
    ('Customers', 'country'): ['USA'],
    ('Products', 'product_color'): ['Red', 'Yellow', 'Black'],
    ('Products', 'product_size'): ['Small', 'Medium', 'Large'],
    ('Accounts', 'other_account_details'): ['Regular', 'VIP'],
    ('Financial_Transactions', 'transaction_type'): ['Payment', 'Refund'],
}

RANGES = {
    ('Product_Categories', 'vat_rating'): (0.0, 20.0),
    ('Products', 'unit_price'): (0.0, 2000.0),
    ('Financial_Transactions', 'transaction_amount'): (0.0, 2000.0),
    ('Invoice_Line_Items', 'product_price'): (0.0, 2000.0),
    ('Invoice_Line_Items', 'derived_product_cost'): (0.0, 2000.0),
    ('Invoice_Line_Items', 'derived_total_cost'): (0.0, 2000.0),
    ('Invoice_Line_Items', 'derived_vat_payable'): (0.0, 2000.0),
}

DATE_LO = '2009-01-01 00:00:00'
DATE_HI = '2018-12-31 23:59:59'

COPIED = {
    ('Invoice_Line_Items', 'product_title'): ('Products', 'product_name'),
}

ALL_NULL = {
    ('Financial_Transactions', 'transaction_comment'),
    ('Financial_Transactions', 'other_transaction_details'),
    ('Order_Items', 'other_order_item_details'),
    ('Orders', 'order_details'),
    ('Invoice_Line_Items', 'derived_vat_payable'),
}

BOUNDARY_TEXT = {
    ('Accounts', 'account_name'): ['336', '337', '338'],
}

DUP_TARGETED = {
    ('Accounts', 'date_account_opened'),
    ('Accounts', 'other_account_details'),
    ('Customers', 'customer_last_name'),
    ('Customers', 'phone_number'),
    ('Order_Items', 'product_quantity'),
    ('Products', 'product_name'),
}

GROUP_TARGETED = {
    ('Accounts', 'account_name'),
    ('Accounts', 'customer_id'),
    ('Financial_Transactions', 'account_id'),
    ('Invoices', 'order_id'),
    ('Orders', 'order_details'),
    ('Order_Items', 'order_id'),
    ('Order_Items', 'product_id'),
}

UNMATCHED_OK = {
    ('Financial_Transactions', 'account_id'),
    ('Order_Items', 'order_id'),
    ('Invoices', 'order_id'),
    ('Orders', 'customer_id'),
    ('Accounts', 'customer_id'),
    ('Order_Items', 'product_id'),
}

NOT_NULL = {
    ('Customers', 'customer_id'),
    ('Orders', 'order_id'),
    ('Orders', 'customer_id'),
    ('Orders', 'date_order_placed'),
    ('Invoices', 'invoice_number'),
    ('Invoices', 'order_id'),
    ('Accounts', 'account_id'),
    ('Accounts', 'customer_id'),
    ('Product_Categories', 'production_type_code'),
    ('Products', 'product_id'),
    ('Products', 'production_type_code'),
    ('Financial_Transactions', 'transaction_id'),
    ('Financial_Transactions', 'account_id'),
    ('Financial_Transactions', 'transaction_type'),
    ('Order_Items', 'order_item_id'),
    ('Order_Items', 'order_id'),
    ('Order_Items', 'product_id'),
    ('Invoice_Line_Items', 'order_item_id'),
    ('Invoice_Line_Items', 'invoice_number'),
    ('Invoice_Line_Items', 'product_id'),
}
