"""Specification implemented by construction (round 1)."""
import re

DUPLICATE_COLUMNS = {
    ('region', 'Region_name'): (0.35, (1, 2, 3)),
    ('region', 'Region_id'): (0.30, (1, 2, 3)),
    ('storm', 'Name'): (0.35, (1, 2, 3)),
    ('storm', 'Dates_active'): (0.30, (1, 2, 3)),
    ('storm', 'Max_speed'): (0.30, (1, 2, 3)),
}

NUMERIC_BOUNDARIES = {
    ('storm', 'Number_Deaths'): [0, 1, 2, 9, 10, 11],
    ('affected_region', 'Number_city_affected'): [0, 1, 2, 9, 10, 11],
}

STRING_BOUNDARIES = {
    ('region', 'Region_name'): ['Afghanistan', 'Albania'],
}

SUM_BOUNDARY = {('affected_region', 'Number_city_affected'): [9.0, 10.0, 11.0]}


def _case_variants(s: str) -> list:
    return [s, s.lower(), s.upper(), s[:1].lower() + s[1:], s[:1].upper() + s[1:]]


def boundary_values(table: str, column: str) -> list:
    """Extra pool values for a column from the comparison/aggregate boundaries."""
    out = []
    for c in NUMERIC_BOUNDARIES.get((table, column), []):
        out += [c - 1, c, c + 1]
    for c in SUM_BOUNDARY.get((table, column), []):
        out += [c - 1, c, c + 1]
    for s in STRING_BOUNDARIES.get((table, column), []):
        out += _case_variants(s)
    return out


def duplicate_plan(table: str, column: str) -> tuple:
    """(share, group_size_targets) for a column, or (0.0, ()) when it is not a duplicate column."""
    return DUPLICATE_COLUMNS.get((table, column), (0.0, ()))


def null_share(schema, table: str, column: str) -> float:
    """NULL share of the compact database for a nullable column (0.0 for NOT NULL columns)."""
    cm = next((c for c in schema.tables[table].columns if c.name == column), None)
    if cm is None or cm.notnull or cm.pk_pos > 0:
        return 0.0
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def is_like_pattern(v: str) -> bool:
    return isinstance(v, str) and '%' in v


def strip_like(v: str) -> str:
    return re.sub(r'%', '', v) if isinstance(v, str) else v
