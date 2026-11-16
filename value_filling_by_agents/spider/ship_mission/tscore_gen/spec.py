"""Specification loading and per-column rule extraction (tscore_gen/specification.json)."""
import json
import re

_DEFAULT = {
    'table_sizes_per_instance': {'ship': 8, 'mission': 7},
    'null_targets': ['mission.Ship_ID'],
    'dependencies': [{'child_table': 'mission', 'child_column': 'Ship_ID',
                      'parent_table': 'ship', 'parent_column': 'Ship_ID', 'copied_columns': []}],
    'per_column_exceptions': [
        {'table': 'ship', 'column': 'Ship_ID', 'pattern': 'unmatched_join_rows',
         'targets': {'joins_with': ['mission.Ship_ID'], 'parent_rows_without_children': True,
                     'child_rows_with_null_fk': True}},
        {'table': 'mission', 'column': 'Ship_ID', 'pattern': 'unmatched_join_rows',
         'targets': {'joins_with': ['ship.Ship_ID'], 'parent_rows_without_children': True,
                     'child_rows_with_null_fk': True, 'null_share': '5-30 % of generated rows'}},
        {'table': 'mission', 'column': 'Mission_ID', 'pattern': 'null_rows',
         'targets': {'null_share': 'none (NOT NULL column)'}},
        {'table': 'ship', 'column': 'Nationality', 'pattern': 'duplicates_for_distinct',
         'targets': {'duplicate_share': '20-50 %', 'values': ['United Kingdom', 'United States']}},
        {'table': 'ship', 'column': 'Nationality', 'pattern': 'aggregate_boundary',
         'targets': {'aggregate': ['COUNT(*)'], 'values': [1, 2, 3],
                     'ops': ['HAVING(COUNT(*) > 2)', 'HAVING(COUNT(*) <> 2)']}},
        {'table': 'ship', 'column': 'Nationality', 'pattern': 'group_sizes',
         'targets': {'group_sizes': '1, 2 and >= 3'}},
        {'table': 'ship', 'column': 'Nationality', 'pattern': 'ties_for_order_limit',
         'targets': {'tie_at_rank': 'any (no LIMIT)', 'direction': 'ASC'}},
        {'table': 'ship', 'column': 'Name', 'pattern': 'duplicates_for_distinct',
         'targets': {'duplicate_share': '20-50 %'}},
        {'table': 'ship', 'column': 'Name', 'pattern': 'aggregate_boundary',
         'targets': {'aggregate': ['COUNT(DISTINCT ship.name)'], 'values': [1, 2, 3],
                     'ops': ['HAVING(COUNT(DISTINCT ship.name) > 2)']}},
        {'table': 'ship', 'column': 'Type', 'pattern': 'ties_for_order_limit',
         'targets': {'tie_at_rank': [1], 'direction': 'ASC and DESC',
                     'tie_on': ['COUNT(ship.type)', 'COUNT(*)']}},
        {'table': 'ship', 'column': 'Type', 'pattern': 'duplicates_for_distinct',
         'targets': {'duplicate_share': '20-50 %', 'values': ['Cargo ship', 'Battle ship']}},
        {'table': 'ship', 'column': 'Type', 'pattern': 'group_sizes',
         'targets': {'group_sizes': '1, 2 and >= 3'}},
        {'table': 'ship', 'column': 'Tonnage', 'pattern': 'comparison_boundary',
         'targets': {'values': [3999, 4000, 4001, 5999, 6000, 6001],
                     'ops': ['PRED(ship.tonnage < 4000)', 'PRED(ship.tonnage > 6000)']}},
        {'table': 'ship', 'column': 'Tonnage', 'pattern': 'rows_with_different_values',
         'targets': {'qualifying_rows': '>= 2 per group with different values',
                     'ops': ['scalar:SELECT(MAX(ship.tonnage))']}},
        {'table': 'mission', 'column': 'Launched_Year', 'pattern': 'literal_pool',
         'targets': {'literals': [1928]}},
    ],
    'semantic_rules_and_formulas': [
        {'table': 'ship', 'column': 'Ship_ID', 'formula': 'Ship_ID > 0'},
        {'table': 'ship', 'column': 'Tonnage', 'formula': 'Tonnage > 0'},
        {'table': 'ship', 'column': 'Type', 'formula': "Type IN ('Cargo ship', 'Battle ship')"},
        {'table': 'ship', 'column': 'Nationality',
         'formula': "Nationality IN ('United Kingdom', 'United States')"},
        {'table': 'mission', 'column': 'Mission_ID', 'formula': 'Mission_ID > 0'},
        {'table': 'mission', 'column': 'Launched_Year', 'formula': 'Launched_Year BETWEEN 1900 AND 1960'},
        {'table': 'mission', 'column': 'Speed_knots', 'formula': 'Speed_knots > 0'},
        {'table': 'mission', 'column': 'Ship_ID',
         'formula': 'Ship_ID IS NULL OR Ship_ID IN (SELECT Ship_ID FROM ship)'},
    ],
}

_NUM = r'-?\d+(?:\.\d+)?'
_IN = re.compile(r'^\s*(\w+)\s+IN\s*\((.*)\)\s*$', re.I)
_BETWEEN = re.compile(r'^\s*(\w+)\s+BETWEEN\s+(' + _NUM + r')\s+AND\s+(' + _NUM + r')\s*$', re.I)
_CMP = re.compile(r'^\s*(\w+)\s*(>=|<=|<>|!=|>|<|=)\s*(' + _NUM + r')\s*$')
_ISNULL = re.compile(r'^\s*(\w+)\s+IS\s+(NOT\s+)?NULL\s*$', re.I)


def load_specification(path: str) -> dict:
    """Read specification.json; merge over the built-in default so missing keys still work."""
    with open(path) as f:
        raw = json.load(f)
    spec = json.loads(json.dumps(_DEFAULT))
    for k, v in raw.items():
        if k in ('per_column_exceptions', 'semantic_rules_and_formulas', 'dependencies'):
            spec[k] = v
        elif k == 'table_sizes_per_instance':
            spec[k] = v
        elif k == 'null_targets':
            spec[k] = v
        else:
            spec[k] = v
    return spec


def spec_from_columns(schema) -> dict:
    """Fallback: derive a minimal specification from the compact database itself."""
    spec = json.loads(json.dumps(_DEFAULT))
    sizes = {}
    for t, tm in schema.tables.items():
        sizes[t] = max(1, min(230, schema.original_sizes.get(t, 0) or 1))
    spec['table_sizes_per_instance'] = sizes
    return spec


def _parse_share(s) -> float:
    """'5-30 %' -> 0.175 (midpoint); 'none ...' -> 0.0; float -> itself."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s)
    if 'none' in s.lower():
        return 0.0
    m = re.findall(r'\d+(?:\.\d+)?', s)
    if not m:
        return None
    vals = [float(x) for x in m]
    if '%' in s:
        vals = [v / 100.0 for v in vals]
    return sum(vals) / len(vals)


def _parse_share_range(s):
    """'5-30 %' -> (0.05, 0.30); 'none' -> (0.0, 0.0); None -> None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return (float(s), float(s))
    s = str(s)
    if 'none' in s.lower():
        return (0.0, 0.0)
    m = re.findall(r'\d+(?:\.\d+)?', s)
    if not m:
        return None
    vals = [float(x) for x in m]
    if '%' in s:
        vals = [v / 100.0 for v in vals]
    if len(vals) == 1:
        return (vals[0], vals[0])
    return (min(vals), max(vals))


def _parse_group_sizes(s) -> list:
    """'1, 2 and >= 3' -> [1, 2, 3] (the '>= 3' bucket is represented by 3)."""
    if not s:
        return []
    out = []
    for m in re.finditer(r'(>=\s*)?(\d+)', str(s)):
        out.append(int(m.group(2)))
    return sorted(set(out))


def _parse_duplicate_share(s) -> float:
    v = _parse_share(s)
    return 0.35 if v is None else v


def column_rules(spec: dict) -> dict:
    """(table, column) -> rule dict built from per_column_exceptions + semantic formulas."""
    rules: dict = {}

    def slot(t, c):
        return rules.setdefault((t, c), {'enum': None, 'range': None, 'boundary': [], 'literals': [],
                                         'null_share': None, 'null_range': None, 'dup_share': None,
                                         'group_sizes': [], 'not_null': False, 'positive': False,
                                         'unmatched': False, 'max_tie': False, 'order_tie': False})

    for ex in spec.get('per_column_exceptions', []):
        t, c = ex.get('table'), ex.get('column')
        if not t or not c:
            continue
        r = slot(t, c)
        tg = ex.get('targets') or {}
        pat = ex.get('pattern')
        if 'values' in tg and pat in ('duplicates_for_distinct',):
            r['enum'] = list(tg['values'])
        if 'values' in tg and pat == 'comparison_boundary':
            r['boundary'] = [int(v) for v in tg['values']]
        if 'literals' in tg:
            r['literals'] = list(tg['literals'])
        if 'null_share' in tg:
            r['null_share'] = _parse_share(tg['null_share'])
            r['null_range'] = _parse_share_range(tg['null_share'])
        if 'duplicate_share' in tg:
            r['dup_share'] = _parse_duplicate_share(tg['duplicate_share'])
        if 'group_sizes' in tg:
            r['group_sizes'] = _parse_group_sizes(tg['group_sizes'])
        if pat == 'unmatched_join_rows':
            r['unmatched'] = True
        if pat == 'rows_with_different_values':
            r['max_tie'] = True
        if pat == 'ties_for_order_limit':
            r['order_tie'] = True
        if pat == 'null_rows' and _parse_share(tg.get('null_share')) == 0.0:
            r['not_null'] = True

    for f in spec.get('semantic_rules_and_formulas', []):
        t, c, fml = f.get('table'), f.get('column'), f.get('formula') or ''
        if not t or not c:
            continue
        r = slot(t, c)
        m = _IN.match(fml)
        if m:
            vals = [x.strip().strip("'\"") for x in m.group(2).split(',')]
            r['enum'] = vals
            continue
        m = _BETWEEN.match(fml)
        if m:
            r['range'] = (int(float(m.group(2))), int(float(m.group(3))))
            continue
        m = _CMP.match(fml)
        if m:
            op, v = m.group(2), float(m.group(3))
            if op in ('>', '>='):
                r['positive'] = True
                r['range'] = (int(v) + (1 if op == '>' else 0), None)
            elif op in ('<', '<='):
                r['range'] = (None, int(v) - (1 if op == '<' else 0))
            continue
        if _ISNULL.match(fml):
            continue
    return rules


def table_sizes(spec: dict, schema, rng) -> dict:
    """Per-instance table sizes: the specification's sizes, jittered by +-1 (0-230 cap)."""
    base = spec.get('table_sizes_per_instance') or {}
    out = {}
    for t in schema.tables:
        n = int(base.get(t, max(1, schema.original_sizes.get(t, 1))))
        j = rng.choice([-1, 0, 0, 1])
        out[t] = max(0, min(230, n + j))
    return out
