"""Specification constants (value domains, enums, ranges, NULL rule, table sizes)."""

TABLE_SIZES = {'people': 120, 'entrepreneur': 24}

HEIGHT_RANGE = (1.5, 2.2)
WEIGHT_RANGE = (40.0, 120.0)
MONEY_MIN = 0.0
DATE_LO, DATE_HI = '1970-01-01', '2000-12-31'

INVESTOR_ENUM = ['Duncan Bannatyne', 'Doug Richard', 'Rachel Elnaugh',
                 'Peter Jones', 'Simon Woodroffe']
INVESTOR_NEAR_VARIANT = 'rachel elnaugh'

MONEY_BOUNDARIES = [81206, 81207, 81208, 119999, 120000, 120001, 139999, 140000, 140001]

MONEY_TIE_RANK = 10
WEIGHT_TIE_RANK = 100

GROUP_SIZES = (1, 2, 3)

NULL_SHARE = 0.10
NULL_TARGETS = ['entrepreneur.People_ID', 'entrepreneur.Company', 'entrepreneur.Money_Requested',
                'entrepreneur.Investor', 'people.Name', 'people.Height', 'people.Weight',
                'people.Date_of_Birth']

DUP_SHARE = (0.20, 0.50)
