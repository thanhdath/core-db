"""Specification constants (generation specification, round 1)."""

TABLE_SIZES = {'people': 12, 'body_builder': 10}

NULL_SHARE_LO = 0.05
NULL_SHARE_HI = 0.30

DUP_SHARE_LO = 0.20
DUP_SHARE_HI = 0.50

NEAR_VARIANT_SHARE = 0.20

LIKE_LITERALS = ['%January%', 'January%']
LIKE_VARIANTS = ['January', 'Januarz', 'January x', 'january']

HEIGHT_RANGE = (120.0, 230.0)
WEIGHT_RANGE = (30.0, 200.0)
LIFT_RANGE = (0.5, 500.0)

HEIGHT_TIE_RANK = 10
TOTAL_TIE_RANKS = (10, 50)

GROUP_SIZE_MIX = (1, 2, 3)

TOTAL_FORMULA = True
