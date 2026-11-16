"""Specification-driven value domains, ranges and NULL rules (tscore_gen/specification.json)."""

COLUMN_RULES = {
    ('company', 'Company_ID'): {'min': 1},
    ('company', 'Rank'): {'min': 1},
    ('company', 'Sales_billion'): {'min': 0.0},
    ('company', 'Profits_billion'): {'min': 0.0},
    ('company', 'Assets_billion'): {'min': 0.0},
    ('company', 'Market_Value'): {'min': 0.0, 'boundary': [99.9, 100.0, 100.1]},
    ('company', 'Main_Industry'): {'enum': ['Oil and gas', 'Conglomerate', 'Banking']},
    ('company', 'Headquarters'): {'literal_pool': ['USA']},
    ('gas_station', 'Station_ID'): {'min': 1},
    ('gas_station', 'Open_Year'): {'range': (1990, 2010), 'boundary': [1999, 2000, 2001, 2004, 2005, 2006]},
    ('station_company', 'Station_ID'): {'min': 1},
    ('station_company', 'Company_ID'): {'min': 1},
    ('station_company', 'Rank_of_the_Year'): {'min': 1},
}

NOT_NULL = {
    ('company', 'Company_ID'),
    ('gas_station', 'Station_ID'),
    ('station_company', 'Station_ID'),
    ('station_company', 'Company_ID'),
}

BASE_SIZES = {'company': 10, 'gas_station': 11, 'station_company': 6}

GROUP_SIZE_TARGETS = {
    ('station_company', 'Company_ID'): '1,2,>=3',
    ('company', 'Company'): '1,2,>=3',
}

DUPLICATE_SHARE = {
    ('gas_station', 'Location'): (0.2, 0.5),
    ('gas_station', 'Manager_Name'): (0.2, 0.5),
    ('company', 'Company'): (0.2, 0.5),
    ('station_company', 'Station_ID'): (0.2, 0.5),
}

TIE_COLUMNS = {
    ('gas_station', 'Open_Year'),
    ('gas_station', 'Station_ID'),
    ('company', 'Profits_billion'),
}

MIN_DISTINCT = {
    ('company', 'Main_Industry'): 2,
}

FRESH_VALUE_SHARE = 0.3


def rule_for(table: str, column: str) -> dict:
    """Return the per-column rule dict (empty if none)."""
    return COLUMN_RULES.get((table, column), {})


def boundary_values(table: str, column: str) -> list:
    """Boundary literals plus one step on each side (numbers only)."""
    r = rule_for(table, column)
    out = []
    for b in r.get('boundary', []):
        if isinstance(b, (int, float)):
            step = 1 if isinstance(b, int) else 0.1
            out += [b - step, b, b + step]
        else:
            out.append(b)
    return out


def in_range(table: str, column: str, v) -> bool:
    """True if v satisfies the column's range/min rule (non-NULL operands only)."""
    r = rule_for(table, column)
    if v is None:
        return True
    if 'range' in r:
        lo, hi = r['range']
        try:
            return lo <= float(v) <= hi
        except (TypeError, ValueError):
            return True
    if 'min' in r:
        try:
            return float(v) >= r['min']
        except (TypeError, ValueError):
            return True
    if 'enum' in r:
        return v in r['enum']
    return True
