"""Specification loading and per-column exception routing."""
import json
import re

_DEFAULT_ENUMS = {
    ('Community_Area', 'side'): ['Far North', 'North', 'Central', 'Northwest', 'West', 'South',
                                 'Far Southeast', 'Southwest'],
    ('FBI_Code', 'crime_against'): ['Persons', 'Property', 'Society', 'Persons and Society'],
    ('IUCR', 'index_code'): ['I', 'N'],
    ('Crime', 'arrest'): ['TRUE', 'FALSE'],
    ('Crime', 'domestic'): ['TRUE', 'FALSE'],
}
_DEFAULT_RANGES = {
    ('Community_Area', 'community_area_no'): (1, 77),
    ('District', 'district_no'): (1, 25),
    ('District', 'zip_code'): (60000, 60999),
    ('Ward', 'ward_no'): (1, 50),
    ('Ward', 'Population'): (0, 100000),
    ('Crime', 'beat'): (1, 3000),
    ('Crime', 'report_no'): (1, 10 ** 7),
    ('Crime', 'latitude'): (41.6, 42.1),
    ('Crime', 'longitude'): (-87.95, -87.5),
}
_DEFAULT_NULLS = {
    ('Crime', 'case_number'): 0.15,
    ('Crime', 'location_description'): 0.05,
    ('Crime', 'latitude'): 0.05,
    ('Crime', 'longitude'): 0.05,
    ('District', 'tty'): 0.05,
    ('Ward', 'alderman_name_suffix'): 0.90,
    ('Ward', 'ward_office_address'): 0.05,
    ('Ward', 'ward_office_zip'): 0.05,
    ('Ward', 'ward_email'): 0.10,
    ('Ward', 'ward_office_phone'): 0.06,
    ('Ward', 'ward_office_fax'): 0.56,
    ('Ward', 'city_hall_office_phone'): 0.24,
    ('Ward', 'city_hall_office_fax'): 0.46,
}
_DEFAULT_DUP = {
    ('Crime', 'case_number'): 0.30,
    ('District', 'commander'): 0.30,
    ('Neighborhood', 'neighborhood_name'): 0.30,
}
_DEFAULT_JOIN = {
    ('Crime', 'district_no'), ('Crime', 'community_area_no'), ('Crime', 'fbi_code_no'),
    ('Crime', 'ward_no'), ('Crime', 'iucr_no'), ('Neighborhood', 'community_area_no'),
}
_DEFAULT_TIES = {
    ('District', 'district_no'), ('District', 'district_name'), ('Ward', 'ward_no'),
    ('Ward', 'ward_office_address'), ('Community_Area', 'community_area_no'),
}


def _key(t, c):
    return (str(t), str(c))


def _parse_targets(targets):
    """Split a target list into (boundary literals, like patterns, numeric bounds)."""
    bounds, likes, nums = [], [], []
    for t in targets or []:
        s = str(t)
        if '%' in s:
            likes.append(s)
        elif re.fullmatch(r'-?\d+(?:\.\d+)?', s):
            nums.append(float(s) if '.' in s else int(s))
        else:
            bounds.append(s)
    return bounds, likes, nums


def load_specification(path: str) -> dict:
    """Read specification.json and normalise it into the sampler lookup structure."""
    with open(path) as f:
        raw = json.load(f)
    return normalise(raw)


def spec_from_columns(schema) -> dict:
    """Derive a minimal specification from the compact database (no file available)."""
    raw = {'per_column_exceptions': [], 'null_targets': [], 'table_sizes_per_instance': {}}
    for t, tm in schema.tables.items():
        raw['table_sizes_per_instance'][t] = max(1, min(230, schema.original_sizes.get(t, 30)))
    return normalise(raw)


def normalise(raw: dict) -> dict:
    """Build {enums, ranges, nulls, dups, joins, ties, boundaries, likes, sizes, fk_null}."""
    spec = {
        'enums': dict(_DEFAULT_ENUMS),
        'ranges': dict(_DEFAULT_RANGES),
        'nulls': dict(_DEFAULT_NULLS),
        'dups': dict(_DEFAULT_DUP),
        'joins': set(_DEFAULT_JOIN),
        'ties': set(_DEFAULT_TIES),
        'boundaries': {},
        'likes': {},
        'sizes': {},
        'fk_null': 0.05,
        'fk_orphan': 0.0,
    }
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            spec['sizes'][str(t)] = int(n)
        except (TypeError, ValueError):
            pass
    for nt in raw.get('null_targets') or []:
        if '.' in str(nt):
            t, c = str(nt).split('.', 1)
            spec['nulls'].setdefault(_key(t, c), 0.05)
    for ex in raw.get('per_column_exceptions') or []:
        col = str(ex.get('column', ''))
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        k = _key(t, c)
        pat = ex.get('pattern')
        bounds, likes, nums = _parse_targets(ex.get('targets'))
        if pat == 'comparison_boundary':
            spec['boundaries'].setdefault(k, [])
            for b in bounds:
                if b not in spec['boundaries'][k]:
                    spec['boundaries'][k].append(b)
            for n in nums:
                if n not in spec['boundaries'][k]:
                    spec['boundaries'][k].append(n)
        elif pat == 'like_near_variant':
            spec['likes'].setdefault(k, [])
            for l in likes:
                if l not in spec['likes'][k]:
                    spec['likes'][k].append(l)
        elif pat == 'duplicates_for_distinct':
            spec['dups'][k] = 0.30
        elif pat == 'unmatched_join_rows':
            spec['joins'].add(k)
        elif pat == 'ties_for_order_limit':
            spec['ties'].add(k)
        elif pat == 'null_in_count_column':
            spec['nulls'][k] = 0.15
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c = str(rule.get('table', '')), str(rule.get('column', ''))
        f = str(rule.get('formula', ''))
        m = re.search(r"\bIN\s*\(([^)]*)\)", f, re.I)
        if m and 'SELECT' not in f.upper():
            vals = [x.strip().strip("'\"") for x in m.group(1).split(',')]
            if vals:
                spec['enums'][_key(t, c)] = vals
        m = re.search(r"BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", f, re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if '.' in m.group(1) or '.' in m.group(2):
                spec['ranges'][_key(t, c)] = (lo, hi)
            else:
                spec['ranges'][_key(t, c)] = (int(lo), int(hi))
        m = re.search(r">=\s*(-?\d+(?:\.\d+)?)", f)
        if m and _key(t, c) not in spec['ranges']:
            lo = float(m.group(1))
            spec['ranges'][_key(t, c)] = (int(lo) if lo == int(lo) else lo, 10 ** 6)
    return spec


def column_spec(spec: dict, table: str, column: str) -> dict:
    """Per-column view of the specification (empty dict when nothing is declared)."""
    k = _key(table, column)
    return {
        'enum': spec['enums'].get(k),
        'range': spec['ranges'].get(k),
        'null_share': spec['nulls'].get(k),
        'dup_share': spec['dups'].get(k),
        'join': k in spec['joins'],
        'tie': k in spec['ties'],
        'boundaries': spec['boundaries'].get(k, []),
        'likes': spec['likes'].get(k, []),
    }
