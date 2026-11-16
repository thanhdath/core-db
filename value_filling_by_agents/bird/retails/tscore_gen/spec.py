"""The generation specification, encoded as data (no SQL is ever evaluated)."""

TABLE_SIZES = {
    'region': 5,
    'nation': 25,
    'supplier': 200,
    'customer': 500,
    'part': 400,
    'partsupp': 800,
    'orders': 1000,
    'lineitem': 2500,
}

ENUMS = {
    ('customer', 'c_mktsegment'): ['BUILDING', 'MACHINERY', 'FURNITURE', 'AUTOMOBILE', 'HOUSEHOLD'],
    ('orders', 'o_orderpriority'): ['1-URGENT', '2-HIGH', '3-MEDIUM', '4-NOT SPECIFIED', '5-LOW'],
    ('orders', 'o_orderstatus'): ['O', 'F', 'P'],
    ('lineitem', 'l_returnflag'): ['A', 'N', 'R'],
    ('lineitem', 'l_linestatus'): ['F', 'O'],
    ('lineitem', 'l_shipmode'): ['AIR', 'FOB', 'MAIL', 'RAIL', 'REG AIR', 'SHIP', 'TRUCK'],
    ('lineitem', 'l_shipinstruct'): ['COLLECT COD', 'DELIVER IN PERSON', 'NONE', 'TAKE BACK RETURN'],
}

BOUNDARY_NUMERIC = {
    ('customer', 'c_custkey'): [0, 1, 2, 106935, 106936, 106937],
    ('orders', 'o_orderkey'): [0, 1, 2, 3, 4, 5],
    ('lineitem', 'l_orderkey'): [0, 1, 2, 3, 4, 5],
    ('customer', 'c_acctbal'): [-0.01, 0, 0.01, 3999.99, 4000, 4000.01],
    ('partsupp', 'ps_supplycost'): [8.99, 9, 9.01, 499.99, 500, 500.01],
    ('nation', 'n_regionkey'): [1, 2, 3, 4],
    ('region', 'r_regionkey'): [1, 2, 3],
}

BOUNDARY_DATE = {
    ('orders', 'o_orderdate'): ['1997-12-31', '1998-01-01', '1998-12-31', '1999-01-01'],
    ('lineitem', 'l_shipdate'): ['1994-12-31', '1995-01-01', '1995-12-31',
                                 '1996-01-01', '1996-12-31', '1997-01-01'],
}

BOUNDARY_TEXT = {
    ('customer', 'c_name'): ['Customer#000000001', 'Customer#000000008'],
    ('customer', 'c_mktsegment'): ['AUTOMOBILE', 'HOUSEHOLD'],
    ('lineitem', 'l_shipmode'): ['RAIL', 'MAIL', 'TRUCK'],
    ('lineitem', 'l_returnflag'): ['R', 'A', 'N'],
    ('part', 'p_name'): ['hot spring dodger dim light', 'pink powder drab lawn cyan',
                         'cornflower sky burlywood green beige'],
    ('part', 'p_container'): ['JUMBO CASE'],
    ('part', 'p_mfgr'): ['Manufacturer#3', 'Manufacturer#5'],
    ('nation', 'n_name'): ['United States', 'GERMANY', 'IRAN'],
    ('region', 'r_name'): ['America', 'EUROPE', 'ASIA'],
}

LIKE_LITERALS = {
    ('orders', 'o_orderdate'): ['1998-%', '1998%'],
    ('lineitem', 'l_shipdate'): ['1994-%', '1998-%', '1998-11%', '1998-11-01'],
}

NULL_SHARE = 0.10
NULL_SHARE_OVERRIDE = {
    ('customer', 'c_name'): 0.20,
    ('orders', 'o_orderpriority'): 0.20,
    ('supplier', 's_name'): 0.20,
    ('nation', 'n_name'): 0.20,
}

DUPLICATE_SHARE = 0.30
DUPLICATE_COLUMNS = {
    ('customer', 'c_custkey'), ('customer', 'c_phone'),
    ('part', 'p_name'), ('supplier', 's_suppkey'), ('supplier', 's_name'),
    ('supplier', 's_phone'),
}

TIE_COLUMNS = {
    ('supplier', 's_acctbal'), ('region', 'r_name'), ('part', 'p_size'),
    ('lineitem', 'l_receiptdate'),
}

UNMATCHED_PARENT_SHARE = 0.03
NULL_FK_SHARE = 0.05

NARROW_RANGES = {
    ('lineitem', 'l_linenumber'): (1, 7),
}

def _between(lo, hi):
    return lambda v: v is None or (lo <= v <= hi)


def _ge(lo):
    return lambda v: v is None or v >= lo


def _gt(lo):
    return lambda v: v is None or v > lo


def _in(vals):
    return lambda v: v is None or v in vals


FORMULAS = {
    ('customer', 'c_custkey'): _gt(0),
    ('customer', 'c_mktsegment'): _in(ENUMS[('customer', 'c_mktsegment')]),
    ('customer', 'c_acctbal'): _between(-999.99, 9999.99),
    ('orders', 'o_orderkey'): _gt(0),
    ('orders', 'o_orderpriority'): _in(ENUMS[('orders', 'o_orderpriority')]),
    ('orders', 'o_orderstatus'): _in(ENUMS[('orders', 'o_orderstatus')]),
    ('orders', 'o_totalprice'): _ge(0),
    ('lineitem', 'l_linenumber'): _between(1, 7),
    ('lineitem', 'l_quantity'): _gt(0),
    ('lineitem', 'l_discount'): _between(0, 1),
    ('lineitem', 'l_tax'): _between(0, 1),
    ('lineitem', 'l_extendedprice'): _ge(0),
    ('lineitem', 'l_returnflag'): _in(ENUMS[('lineitem', 'l_returnflag')]),
    ('lineitem', 'l_linestatus'): _in(ENUMS[('lineitem', 'l_linestatus')]),
    ('lineitem', 'l_shipmode'): _in(ENUMS[('lineitem', 'l_shipmode')]),
    ('lineitem', 'l_shipinstruct'): _in(ENUMS[('lineitem', 'l_shipinstruct')]),
    ('part', 'p_size'): _between(1, 50),
    ('part', 'p_retailprice'): _ge(0),
    ('partsupp', 'ps_supplycost'): _ge(0),
    ('partsupp', 'ps_availqty'): _ge(0),
    ('supplier', 's_acctbal'): _between(-999.99, 9999.99),
    ('nation', 'n_nationkey'): _ge(0),
    ('region', 'r_regionkey'): _ge(0),
}

DATE_ORDER = {
    ('lineitem', 'l_shipdate'): ('l_commitdate', '>='),
    ('lineitem', 'l_receiptdate'): ('l_shipdate', '>='),
    ('lineitem', 'l_commitdate'): ('__min_date__', '>='),
}
MIN_DATE = '1992-01-01'

INT_RANGE = (1, 100000)
REAL_AMOUNT = (0.0, 100000.0)
REAL_BALANCE = (-999.99, 9999.99)
REAL_RATE = (0.0, 1.0)
DATE_RANGE = ('1992-01-01', '1998-12-31')
TEXT_SHORT_LEN = (8, 40)
TEXT_COMMENT_LEN = (20, 120)

NAME_FORMATS = {
    ('customer', 'c_name'): 'Customer#%09d',
    ('supplier', 's_name'): 'Supplier#%09d',
    ('orders', 'o_clerk'): 'Clerk#%09d',
    ('part', 'p_brand'): 'Brand#%02d',
    ('part', 'p_mfgr'): 'Manufacturer#%d',
}
