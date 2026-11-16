"""Specification model: value pools, ranges, NULL shares, dependencies and semantic rules."""
import re

BOUNDARY = {
    ('state', 'state_name'): ['rhode island', 'RHODE ISLAND', 'New Mexico', 'new mexico', 'Colorado', 'colorado'],
    ('state', 'capital'): ['boston', 'BOSTON', 'albany', 'ALBANY', 'Boston'],
    ('state', 'country_name'): ['USA', 'usa', 'US', 'us', 'Colorado', 'colorado'],
    ('state', 'density'): ['boston', 'BOSTON', 99, 100, 101],
    ('city', 'city_name'): ['austin', 'AUSTIN', 'springfield', 'SPRINGFIELD', 'Austin', 'Springfield'],
    ('city', 'state_name'): ['texas', 'TEXAS', 149999, 150000, 150001],
    ('city', 'population'): [99999, 100000, 100001, 149999, 150000, 150001],
    ('city', 'country_name'): ['USA', 'usa'],
    ('border_info', 'state_name'): ['colorado', 'COLORADO', 'kentucky', 'KENTUCKY', 'nebraska', 'NEBRASKA'],
    ('border_info', 'border'): ['Colorado', 'colorado', 'New Mexico', 'new mexico', 'Nebraska', 'nebraska'],
    ('highlow', 'state_name'): ['alabama', 'ALABAMA', 'abama', 'ABAMA', 'Alabama'],
    ('river', 'river_name'): ['mississippi', 'MISSISSIPPI', 'colorado', 'COLORADO', 'missouri', 'MISSOURI'],
    ('river', 'traverse'): ['idaho', 'IDAHO', 'ohio', 'OHIO', 'colorado', 'COLORADO'],
    ('river', 'length'): [-467, -466, -465, 749, 750, 751],
}

LIKE_VARIANTS = {('river', 'river_name'): ['%miners%']}

NUMERIC_BOUNDARY = {
    ('city', 'population'): [99999, 100000, 100001, 149999, 150000, 150001],
    ('river', 'length'): [-467, -466, -465, 749, 750, 751],
    ('state', 'density'): [99, 100, 101],
}

TIES = {
    ('state', 'population'): ('ASC', 'DESC'),
    ('state', 'area'): ('DESC',),
    ('state', 'density'): ('DESC',),
    ('city', 'population'): ('DESC',),
    ('highlow', 'highest_elevation'): ('DESC',),
    ('highlow', 'highest_point'): ('DESC',),
    ('highlow', 'lowest_elevation'): ('DESC',),
}

NULL_SHARE = {
    ('state', 'population'): 0.15, ('state', 'area'): 0.15, ('state', 'capital'): 0.15,
    ('state', 'density'): 0.15, ('city', 'population'): 0.15,
    ('highlow', 'highest_elevation'): 0.15, ('highlow', 'lowest_point'): 0.15,
    ('highlow', 'highest_point'): 0.15, ('highlow', 'lowest_elevation'): 0.2,
    ('lake', 'lake_name'): 0.15, ('lake', 'area'): 0.15, ('lake', 'state_name'): 0.15,
    ('mountain', 'mountain_altitude'): 0.15, ('river', 'length'): 0.15, ('river', 'traverse'): 0.15,
}

NUM_RANGE = {
    ('state', 'population'): (500000, 40000000),
    ('state', 'area'): (1000.0, 300000.0),
    ('state', 'density'): (1.0, 1200.0),
    ('city', 'population'): (1000, 9000000),
    ('river', 'length'): (50, 4000),
    ('mountain', 'mountain_altitude'): (100, 6200),
    ('lake', 'area'): (1.0, 60000.0),
}

POSITIVE = {('state', 'population'), ('state', 'area'), ('state', 'density'),
            ('city', 'population'), ('river', 'length'), ('mountain', 'mountain_altitude'),
            ('lake', 'area')}
COUNTRY_ENUM = {'USA', 'US', 'usa', 'us'}
COUNTRY_COLUMNS = {('state', 'country_name'), ('city', 'country_name'),
                   ('river', 'country_name'), ('mountain', 'country_name'), ('lake', 'country_name')}

TABLE_SIZES = {'state': 40, 'city': 60, 'border_info': 30, 'highlow': 20,
               'lake': 15, 'mountain': 20, 'river': 20}

DUP_SHARE = {('state', 'state_name'): 0.3, ('river', 'traverse'): 0.3,
             ('border_info', 'state_name'): 0.3, ('border_info', 'border'): 0.3}


def _key(t, c):
    return (str(t).lower(), str(c).lower())


def load_specification(raw: dict) -> dict:
    """Normalise a specification.json into the dict used by the samplers."""
    spec = {
        'boundary': dict(BOUNDARY), 'like': dict(LIKE_VARIANTS), 'numeric_boundary': dict(NUMERIC_BOUNDARY),
        'ties': dict(TIES), 'null_share': dict(NULL_SHARE), 'num_range': dict(NUM_RANGE),
        'positive': set(POSITIVE), 'country_enum': set(COUNTRY_ENUM), 'country_columns': set(COUNTRY_COLUMNS),
        'sizes': dict(TABLE_SIZES), 'dup_share': dict(DUP_SHARE), 'dependencies': [], 'rules': [],
    }
    if not isinstance(raw, dict):
        return spec
    for ex in raw.get('per_column_exceptions', []) or []:
        k = _key(ex.get('table'), ex.get('column'))
        tg = ex.get('targets') or []
        pat = ex.get('pattern')
        if pat == 'comparison_boundary':
            spec['boundary'].setdefault(k, [])
            for v in tg:
                if v not in spec['boundary'][k]:
                    spec['boundary'][k].append(v)
        elif pat == 'like_near_variant':
            spec['like'].setdefault(k, [])
            for v in tg:
                if v not in spec['like'][k]:
                    spec['like'][k].append(v)
        elif pat == 'ties_for_order_limit':
            spec['ties'].setdefault(k, ('DESC',))
        elif pat == 'null_rows':
            spec['null_share'][k] = 0.2
        elif pat == 'duplicates_for_distinct':
            spec['dup_share'][k] = 0.3
    for d in raw.get('dependencies', []) or []:
        spec['dependencies'].append((_key(*str(d.get('child')).split('.')),
                                     _key(*str(d.get('parent_table')).split('.')[:1] + [d.get('parent_column')])))
    for r in raw.get('semantic_rules_and_formulas', []) or []:
        spec['rules'].append((_key(r.get('table'), r.get('column')), r.get('formula')))
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        spec['sizes'][str(t).lower()] = int(n)
    return spec


def spec_from_columns() -> dict:
    """Fallback specification built from the column summary (no specification.json present)."""
    return load_specification({})


def is_positive(spec: dict, t: str, c: str) -> bool:
    return _key(t, c) in spec['positive']


def is_country(spec: dict, t: str, c: str) -> bool:
    return _key(t, c) in spec['country_columns']


def null_share(spec: dict, t: str, c: str) -> float:
    return spec['null_share'].get(_key(t, c), 0.15)


def num_range(spec: dict, t: str, c: str):
    return spec['num_range'].get(_key(t, c), (1, 1000))


def boundary_values(spec: dict, t: str, c: str) -> list:
    return list(spec['boundary'].get(_key(t, c), []))


def like_values(spec: dict, t: str, c: str) -> list:
    return list(spec['like'].get(_key(t, c), []))


def tie_directions(spec: dict, t: str, c: str):
    return spec['ties'].get(_key(t, c), ())


def dup_share(spec: dict, t: str, c: str) -> float:
    return spec['dup_share'].get(_key(t, c), 0.0)


def table_size(spec: dict, t: str, rng) -> int:
    """Per-instance table size: specification size with a small random variation (0-230 cap)."""
    base = spec['sizes'].get(str(t).lower(), 20)
    lo = max(0, int(base * 0.6))
    hi = min(230, max(lo + 1, int(base * 1.4)))
    return rng.randint(lo, hi)


def _is_num(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def coerce_literal(value, type_str: str):
    """Type a pool literal for a column: numbers for numeric columns, text otherwise."""
    t = (type_str or '').lower()
    numeric = any(k in t for k in ('int', 'double', 'float', 'real', 'decimal', 'numeric', 'number'))
    if numeric:
        if _is_num(value):
            try:
                return int(float(value)) if 'int' in t else float(value)
            except (TypeError, ValueError):
                return None
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return str(value)


def string_variants(v: str) -> list:
    """Prefix / suffix / dropped-character variants of a text literal."""
    out = []
    if not v:
        return out
    n = len(v)
    if n >= 2:
        out.append(v[1:])
        out.append(v[:-1])
    if n >= 3:
        out.append(v[1:-1])
    out.append(v + 'x')
    out.append('x' + v)
    return [x for x in out if x and x != v]


def like_body(v: str) -> str:
    """Strip '%' from a LIKE pattern to obtain a plain text value."""
    return re.sub(r'%', '', str(v))
