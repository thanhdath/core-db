"""Specification loading and per-column rule tables (implemented by construction)."""
import json
import re

_DEFAULT = {
    'table_sizes': {'editor': 8, 'journal': 8, 'journal_committee': 7},
    'ranges': {
        ('editor', 'Age'): (18.0, 70.0),
        ('journal', 'Sales'): (0, 10 ** 9),
    },
    'enums': {
        ('journal_committee', 'Work_Type'): ['Photo', 'Article', 'Title'],
    },
    'boundaries': {
        ('editor', 'Age'): [23.0, 24.0, 25.0, 26.0],
        ('journal', 'Sales'): [2999, 3000, 3001],
    },
    'null_targets': [],
    'count_columns': [('journal_committee', 'Editor_ID'), ('journal_committee', 'Journal_ID')],
    'pattern_columns': [
        ('editor', 'Name'), ('editor', 'Age'), ('editor', 'Editor_ID'),
        ('journal', 'Theme'),
    ],
    'fresh_share': 0.3,
}


def _parse_range(text: str):
    """'Age BETWEEN 18 AND 70' -> (18.0, 70.0); 'Sales >= 0' -> (0, inf)."""
    m = re.search(r'between\s+(-?[\d.]+)\s+and\s+(-?[\d.]+)', text, re.I)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'>=\s*(-?[\d.]+)', text)
    if m:
        return float(m.group(1)), float('inf')
    m = re.search(r'<=\s*(-?[\d.]+)', text)
    if m:
        return float('-inf'), float(m.group(1))
    return None


def _parse_enum(text: str):
    """Work_Type IN ('Photo', 'Article', 'Title') -> list of values."""
    m = re.search(r'in\s*\((.*)\)', text, re.I | re.S)
    if not m:
        return None
    vals = re.findall(r"'((?:[^']|'')*)'", m.group(1))
    return [v.replace("''", "'") for v in vals] if vals else None


def load_specification(path: str) -> dict:
    """Read specification.json and normalise it into the tables used by the samplers."""
    with open(path) as f:
        raw = json.load(f)
    spec = {
        'table_sizes': dict(_DEFAULT['table_sizes']),
        'ranges': dict(_DEFAULT['ranges']),
        'enums': {k: list(v) for k, v in _DEFAULT['enums'].items()},
        'boundaries': {k: list(v) for k, v in _DEFAULT['boundaries'].items()},
        'null_targets': list(_DEFAULT['null_targets']),
        'count_columns': list(_DEFAULT['count_columns']),
        'pattern_columns': list(_DEFAULT['pattern_columns']),
        'fresh_share': _DEFAULT['fresh_share'],
    }
    sizes = raw.get('table_sizes_per_instance') or {}
    for t, n in sizes.items():
        try:
            spec['table_sizes'][t] = int(n)
        except (TypeError, ValueError):
            pass
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c = rule.get('table'), rule.get('column')
        formula = rule.get('formula') or ''
        if not t or not c:
            continue
        enum = _parse_enum(formula)
        if enum:
            spec['enums'][(t, c)] = enum
            continue
        rng = _parse_range(formula)
        if rng:
            spec['ranges'][(t, c)] = rng
    pattern_cols = set()
    for exc in raw.get('per_column_exceptions') or []:
        col = exc.get('column') or ''
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        targets = exc.get('targets') or ''
        pat = exc.get('pattern')
        if pat == 'comparison_boundary':
            nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', targets)]
            if nums:
                spec['boundaries'][(t, c)] = nums
        elif pat == 'enum':
            vals = [v.strip() for v in targets.split(',') if v.strip()]
            if vals:
                spec['enums'][(t, c)] = vals
        elif pat in ('group_sizes', 'duplicates_for_distinct'):
            pattern_cols.add((t, c))
    if pattern_cols:
        spec['pattern_columns'] = sorted(pattern_cols)
    nt = raw.get('null_targets')
    if isinstance(nt, list) and nt:
        parsed = []
        for x in nt:
            if isinstance(x, str) and '.' in x:
                t, c = x.split('.', 1)
                parsed.append((t, c))
        if parsed:
            spec['null_targets'] = parsed
    return spec
