"""Generation-specification knowledge, embedded as data and applied by construction in the samplers."""

ENUMS = {
    ('mountain', 'Country'): ['Tanzania', 'Kenya', 'DR Congo Uganda', 'Uganda'],
    ('mountain', 'Range'): ['Kilimanjaro', 'Mount Kenya', 'Rwenzori'],
    ('climber', 'Country'): ['West Germany', 'Switzerland', 'United Kingdom'],
}

BOUNDARIES = {
    ('mountain', 'Height'): [4999, 5000, 5001, 5002, 5199, 5200, 5201, 5599, 5600, 5601],
    ('mountain', 'Prominence'): [999, 1000, 1001],
}

RANGES = {
    ('mountain', 'Height'): (1.0, 6000.0),
    ('mountain', 'Prominence'): (1.0, 6000.0),
    ('climber', 'Points'): (0.0, 100.0),
}

TIE_TOP = {
    ('mountain', 'Height'): 2,
    ('mountain', 'Prominence'): 3,
    ('climber', 'Points'): 2,
}

TIE_RANKS = {
    ('climber', 'Points'): {1: 2, 10: 2},
    ('mountain', 'Prominence'): {1: 3, 3: 2},
    ('mountain', 'Height'): {1: 2},
}

DROPPED_TIE_RANKS = {
    ('climber', 'Points'): [1000],
}

DUPLICATE_SHARE = {
    ('mountain', 'Country'): 0.30,
    ('mountain', 'Range'): 0.30,
    ('mountain', 'Name'): 0.30,
    ('climber', 'Time'): 0.30,
}

GROUP_SHAPES = {
    ('mountain', 'Country'): '1,2,3',
    ('climber', 'Mountain_ID'): '1,2,3',
}

NULL_SHARE = {
    ('climber', 'Mountain_ID'): 0.20,
}

TABLE_SIZES = {'mountain': 12, 'climber': 14}

REUSE_SHARE = 0.2

FORMULAS = []

SOFT_FORMULAS = []


def _prominence_le_height(row: dict) -> bool:
    h, p = row.get('Height'), row.get('Prominence')
    if h is None or p is None:
        return True
    return p <= h


def _height_positive(row: dict) -> bool:
    h = row.get('Height')
    return h is None or h > 0


def _prominence_positive(row: dict) -> bool:
    p = row.get('Prominence')
    return p is None or p > 0


def _points_nonneg(row: dict) -> bool:
    p = row.get('Points')
    return p is None or p >= 0


FORMULAS.append((('mountain', 'Height'), _height_positive))
FORMULAS.append((('mountain', 'Prominence'), _prominence_positive))
FORMULAS.append((('climber', 'Points'), _points_nonneg))
SOFT_FORMULAS.append((('mountain', 'Prominence'), _prominence_le_height))


def formula_ok(table: str, row: dict) -> bool:
    """True if every HARD formula on (table, *) holds for non-NULL operands (SQL 3VL: NULL never fails)."""
    for (t, _c), fn in FORMULAS:
        if t == table and not fn(row):
            return False
    return True


def soft_formula_ok(table: str, row: dict) -> bool:
    """True if every SOFT formula on (table, *) holds for non-NULL operands."""
    for (t, _c), fn in SOFT_FORMULAS:
        if t == table and not fn(row):
            return False
    return True


def bound_values(table: str, column: str) -> list:
    return list(BOUNDARIES.get((table, column), []))


def enum_values(table: str, column: str):
    return ENUMS.get((table, column))


def range_of(table: str, column: str):
    return RANGES.get((table, column))


def tie_top(table: str, column: str) -> int:
    return TIE_TOP.get((table, column), 0)


def tie_ranks(table: str, column: str) -> dict:
    return dict(TIE_RANKS.get((table, column), {}))


def duplicate_share(table: str, column: str) -> float:
    return DUPLICATE_SHARE.get((table, column), 0.0)


def group_shape(table: str, column: str) -> str:
    return GROUP_SHAPES.get((table, column), '')


def null_share(table: str, column: str, fallback: float) -> float:
    return NULL_SHARE.get((table, column), fallback)


def table_size(table: str, fallback: int) -> int:
    return TABLE_SIZES.get(table, fallback)


def reuse_share() -> float:
    return REUSE_SHARE
