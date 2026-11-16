"""Specification-driven column domains (generation specification -> Python samplers)."""
import math
import re

BOUNDARY_VALUES = [-1396, -1395, -1394, -849, -848, -847, 1849, 1850, 1851, 1852,
                   19998, 19999, 20000, 20001]
FOUNDED_BOUNDARY = [1849, 1850, 1851, 1852]
ENROLLMENT_BOUNDARY = [19998, 19999, 20000, 20001]
AFFILIATION_LITERALS = ['Public', 'public']
LOCATION_LIKE_LITERALS = ['%NY%', '%Y%']
LOCATION_VARIANTS = ['NY', 'NZ', 'NY x', 'ny', 'Y', 'Z', 'Y x', 'y']

DUP_SHARE_COLUMNS = {('basketball_match', 'School_ID'), ('university', 'School_ID'),
                     ('basketball_match', 'Team_Name'), ('university', 'School')}
TIE_COLUMNS = {('university', 'Founded'), ('basketball_match', 'ACC_Percent'),
               ('university', 'Enrollment'), ('basketball_match', 'All_Games'),
               ('basketball_match', 'All_Neutral'), ('university', 'Nickname')}

_TAGS = {
    'team_name': r'(team_?name|school)',
    'nickname': r'nickname',
    'location': r'location',
    'affiliation': r'affiliation',
    'conference': r'primary_conference|conference',
    'percent_str': r'percent',
    'score': r'(acc_home|acc_road|all_home|all_road|all_neutral|regular_season|all_games)\b',
    'founded': r'founded',
    'enrollment': r'enrollment',
}


def load_spec(path: str) -> dict:
    """Read specification.json (tolerant: missing file -> empty dict)."""
    import json
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def classify_column(table: str, column: str, type_str: str) -> set:
    """Semantic tags for a column (lower-case matching on the column name)."""
    c = column.lower()
    t = (type_str or '').lower()
    tags = set()
    if 'date' in t or re.search(_TAGS['founded'], c):
        tags.add('founded')
    if re.search(_TAGS['enrollment'], c):
        tags.add('enrollment')
    if re.search(r'percent', c):
        tags.add('percent_str')
        tags.add('percent')
    if re.search(_TAGS['score'], c) or c.endswith('_season'):
        tags.add('score')
    if re.search(r'school_id|team_id', c):
        tags.add('id')
        if c.endswith('school_id'):
            tags.add('school_id')
        if c.endswith('team_id'):
            tags.add('team_id')
    if re.search(_TAGS['location'], c):
        tags.add('location')
    if re.search(_TAGS['affiliation'], c):
        tags.add('affiliation')
    if re.search(_TAGS['conference'], c):
        tags.add('conference')
    if re.search(_TAGS['nickname'], c):
        tags.add('nickname')
    if re.search(_TAGS['team_name'], c) or c in ('school', 'team_name'):
        tags.add('name')
    return tags


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t


def _col_values(schema, table, column):
    return [v for v in schema.original_values.get((table, column), []) if v is not None]


def _numeric_stats(schema, table, column):
    vals = []
    for v in _col_values(schema, table, column):
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            pass
    if not vals:
        return None
    return min(vals), max(vals)


def _null_share(schema, table, column) -> float:
    """Observed NULL fraction of a column in the compact database (floor 1/10)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.1
    n_null = sum(1 for v in vals if v is None)
    return max(0.1, n_null / float(len(vals)))


def build_column_specs(schema, spec: dict) -> dict:
    """Per column (table, column) -> domain dict consumed by the instance sampler."""
    out = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            tag = classify_column(t, cm.name, cm.type_str)
            d = {'tags': tag, 'is_int': _is_int_type(cm.type_str), 'notnull': cm.notnull or cm.pk_pos > 0,
                 'pk': cm.pk_pos > 0, 'boundary': [], 'enum': [], 'like_literals': [], 'variants': [],
                 'tie': False, 'fresh': 0.3, 'dup_share': 0.0,
                 'null_share': _null_share(schema, t, cm.name)}
            st = _numeric_stats(schema, t, cm.name)
            if st is not None and d['is_int']:
                lo, hi = st
                d['lo'], d['hi'] = int(math.floor(lo)) - 1, int(math.ceil(hi)) + 1
            elif st is not None:
                lo, hi = st
                d['lo'], d['hi'] = lo - 1.0, hi + 1.0
            if 'founded' in tag:
                d['lo'], d['hi'] = 1600.0, 2100.0
                d['boundary'] = list(FOUNDED_BOUNDARY)
            if 'enrollment' in tag:
                d['lo'], d['hi'] = 0.0, max(d.get('hi', 60000.0), 60000.0)
                d['boundary'] = list(ENROLLMENT_BOUNDARY)
            if 'school_id' in tag or 'team_id' in tag:
                d['boundary'] = [1, 2, 3, 4, 5, 6]
            if 'percent_str' in tag:
                d['form'] = 'percent'
            if 'score' in tag:
                d['form'] = 'score'
            if 'affiliation' in tag:
                d['enum'] = list(AFFILIATION_LITERALS) + ['Private', 'Private/Methodist']
            if 'location' in tag:
                d['like_literals'] = list(LOCATION_LIKE_LITERALS)
                d['variants'] = list(LOCATION_VARIANTS)
            if (t, cm.name) in TIE_COLUMNS:
                d['tie'] = True
            if (t, cm.name) in DUP_SHARE_COLUMNS:
                d['dup_share'] = 0.3
            if cm.unique:
                d['tie'] = False
            out[(t, cm.name)] = d
    return out


def mild_ranges(schema) -> dict:
    """Soft numeric range per numeric column from the compact rows (stats-based +/-1)."""
    out = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            st = _numeric_stats(schema, t, cm.name)
            if st is not None:
                out[(t, cm.name)] = st
    return out
