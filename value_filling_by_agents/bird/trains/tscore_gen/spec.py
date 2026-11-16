"""Specification of the generation rules, implemented by construction."""

ENUM_POOLS = {
    ('trains', 'direction'): ['east', 'west'],
    ('cars', 'shape'): ['rectangle', 'bucket', 'u_shaped', 'hexagon', 'ellipse'],
    ('cars', 'len'): ['short', 'long'],
    ('cars', 'sides'): ['not_double', 'double'],
    ('cars', 'roof'): ['none', 'peaked', 'flat', 'arc', 'jagged'],
    ('cars', 'load_shape'): ['circle', 'hexagon', 'triangle', 'rectangle', 'diamond'],
}

INT_POOLS = {
    ('cars', 'position'): [1, 2, 3, 4],
    ('cars', 'wheels'): [2, 3],
    ('cars', 'load_num'): [0, 1, 2, 3],
}

INT_RANGES = {
    ('cars', 'position'): (1, 4),
    ('cars', 'wheels'): (2, 3),
    ('cars', 'load_num'): (0, 3),
}

COLUMN_EXCEPTIONS = {
    ('trains', 'direction'): ['east', 'EAST', 'west', 'WEST'],
    ('cars', 'shape'): ['rectangle', 'bucket', 'elipse', 'BUCKET', 'ELIPSE', 'RECTANGLE',
                        'ele', 'ELE', 'eli', 'ELI'],
    ('cars', 'len'): ['short', 'SHORT'],
    ('cars', 'sides'): ['double'],
    ('cars', 'roof'): ['flat', 'FLAT', 'none', 'NONE'],
    ('cars', 'load_shape'): ['circle', 'CIRCLE'],
}

LIKE_PATTERNS = {
    ('cars', 'shape'): ['bucket', 'elipse'],
}

INT_BOUNDARY = {
    ('trains', 'id'): [0, 1, 2],
    ('cars', 'id'): [4],
    ('cars', 'position'): [0, 1, 2, 3, 4, 5],
    ('cars', 'wheels'): [2, 3],
    ('cars', 'load_num'): [3],
}

TABLE_SIZES = {'trains': 6, 'cars': 12}

NULL_RULE = 'one_per_column'

GROUP_SIZE_TARGETS = {'sizes': [1, 2, 3], 'min_large': 4}

DIRECTION_TIE = True


def enum_pool(table: str, column: str) -> list:
    """Observed enumerated pool only (near-variants are query literals only)."""
    return list(ENUM_POOLS.get((table, column), []))


def int_pool(table: str, column: str) -> list:
    """Small integer pool, intersected with the column's semantic range."""
    base = list(INT_POOLS.get((table, column), []))
    rng = INT_RANGES.get((table, column))
    if rng is not None:
        lo, hi = rng
        base = [v for v in base if lo <= v <= hi]
    return sorted(set(base))


def int_range(table: str, column: str):
    """Inclusive integer range for a column, or None."""
    return INT_RANGES.get((table, column))


def like_patterns(table: str, column: str) -> list:
    """LIKE patterns (without '%') for a column (query literals only)."""
    return list(LIKE_PATTERNS.get((table, column), []))
