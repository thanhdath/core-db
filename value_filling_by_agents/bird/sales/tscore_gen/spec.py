"""Specification data (embedded default) and the specification.json loader."""
import re


def _build_embedded():
    return {
        'value_pools': {
            'Customers': {
                'FirstName': ['Aaron', 'Abby', 'Abe', 'Abhijit', 'Abigail', 'Abraham', 'Adam', 'Adina',
                              'Albert', 'Al', 'Madison', 'Joe', 'Maria', 'John', 'Susan'],
                'MiddleInitial': ['A', 'B', 'C', 'E', 'J', 'K', 'L', 'M', 'I', 'R', 'L', 'i'],
                'LastName': ['Alexander', 'Bryant', 'Butler', 'Chen', 'Coleman', 'Con', 'Edwards', 'Flores',
                             'Ringer', 'Lopez', 'Smith', 'Brown', 'Garcia', 'Johnson'],
            },
            'Employees': {
                'FirstName': ['Abraham', 'Reginald', 'Cheryl', 'Michel', 'Innes', 'Ann', 'Marjorie',
                              'Morningstar', 'Albert', 'e', 'E'],
                'MiddleInitial': ['e', 'l', 'a', 'u', 'r', 'o', 'c', 'i', 'I', 'E'],
                'LastName': ['Bennet', 'Blotchet-Halls', 'Carson', 'DeFrance', 'del Castillo', 'Dull',
                             'Green', 'Greene', 'Ringer', 'ringer'],
            },
            'Products': {
                'Name': ['Adjustable Race', 'Bearing Ball', 'BB Ball Bearing', 'Headset Ball Bearings',
                         'Blade', 'blade', 'LL Crankarm', 'ML Crankarm', 'HL Crankarm',
                         'ML Bottom Bracket', 'ml bottom bracket',
                         'HL Mountain Frame - Black, 42', 'hl mountain frame - black, 42',
                         'HL Mountain Frame - Silver, 42', 'HL Touring Frame', 'C', 'D', 'C x', 'c',
                         'HL Touring Framf', 'HL Touring Frame x', 'hl touring frame'],
            },
        },
        'numeric_ranges': {
            'Products': {'Price': [0.0, 400.0]},
            'Sales': {'Quantity': [1, 500]},
        },
        'null_targets': {
            'Customers': {'MiddleInitial': 0.422},
            'Employees': {'MiddleInitial': 0.0},
        },
        'table_sizes': {
            'Customers': [200, 200],
            'Employees': [22, 22],
            'Products': [200, 200],
            'Sales': [2000, 2000],
        },
        'boundary_values': {
            'Customers': {'CustomerID': [1, 2, 79, 80, 81],
                          'FirstName': ['Albert', 'albert', 'madison', 'MADISON', 'Madison'],
                          'MiddleInitial': ['L', 'l', 'I', 'i', 'M', 'm'],
                          'LastName': ['Ringer', 'ringer', 'lopez', 'LOPEZ', 'Lopez']},
            'Products': {'ProductID': [399, 400, 401, 499, 500, 501],
                         'Name': ['Blade', 'blade', 'ML Bottom Bracket', 'ml bottom bracket',
                                  'HL Mountain Frame - Black, 42', 'hl mountain frame - black, 42'],
                         'Price': [0.0, 0.001, 199.999, 200.0, 200.001]},
            'Sales': {'SalesID': [1, 2, 9, 10, 11],
                      'CustomerID': [1, 2, 79, 80, 81],
                      'ProductID': [399, 400, 401, 499, 500, 501],
                      'Quantity': [499, 500, 501],
                      'SalesPersonID': [1, 2]},
            'Employees': {'LastName': ['Ringer', 'ringer'], 'FirstName': ['Albert', 'albert', 'e', 'E'],
                          'MiddleInitial': ['I', 'i', 'e', 'E']},
        },
        'semantic_rules': {
            'Sales': {'Quantity': {'type': 'gt', 'value': 0}},
            'Products': {'Price': {'type': 'ge', 'value': 0.0}},
            'Customers': {'CustomerID': {'type': 'gt', 'value': 0}},
            'Employees': {'EmployeeID': {'type': 'gt', 'value': 0}},
            'Products': {'ProductID': {'type': 'gt', 'value': 0}},
            'Sales': {'SalesID': {'type': 'gt', 'value': 0}},
        },
        'duplicate_share': {
            'Products': {'Name': 0.2},
            'Customers': {'LastName': 0.2},
        },
        'unmatched_parents': {
            'Customers': {'CustomerID': True},
            'Products': {'ProductID': True},
            'Employees': {'EmployeeID': True},
        },
    }


def build_spec():
    return _build_embedded()


_RULE = re.compile(r'^\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*$')


def _parse_formula(s: str):
    """Parse 'Table.Column OP number' into (table, column, rule dict) or None."""
    m = _RULE.match(s or '')
    if not m:
        return None
    t, c, op, v = m.group(1), m.group(2), m.group(3), m.group(4)
    kind = {'>': 'gt', '>=': 'ge', '<': 'lt', '<=': 'le', '=': 'eq'}[op]
    val = float(v) if '.' in v else int(v)
    return t, c, {'type': kind, 'value': val}


def _rule_ok(rule, v) -> bool:
    """True if value v satisfies the semantic rule (None always passes: NULL is a value)."""
    if v is None or not rule:
        return True
    kind, val = rule.get('type'), rule.get('value')
    try:
        if kind == 'gt':
            return v > val
        if kind == 'ge':
            return v >= val
        if kind == 'lt':
            return v < val
        if kind == 'le':
            return v <= val
        if kind == 'eq':
            return v == val
    except TypeError:
        return True
    return True


def _filter_boundaries(bv: dict, rules: dict) -> dict:
    """Drop boundary literals that violate the column's own semantic rule."""
    out = {}
    for t, cols in bv.items():
        for c, vals in cols.items():
            rule = (rules.get(t) or {}).get(c)
            kept = [v for v in vals if _rule_ok(rule, v)]
            if kept:
                out.setdefault(t, {})[c] = kept
    return out


def _null_rate_from_stats(stats: dict, t: str, c: str):
    """Read the NULL share from the compact statistics; None if unavailable."""
    try:
        col = stats[t]['columns'][c]
    except (KeyError, TypeError):
        return None
    if isinstance(col, dict):
        if 'null_rate' in col:
            try:
                return float(col['null_rate'])
            except (TypeError, ValueError):
                pass
        ns = col.get('null_share')
        if isinstance(ns, (int, float)):
            return float(ns)
        if isinstance(ns, str):
            m = re.search(r'(\d+(?:\.\d+)?)\s*%', ns)
            if m:
                return float(m.group(1)) / 100.0
            if ns.strip().lower().startswith('none'):
                return 0.0
    return None


def normalize_spec(raw: dict) -> dict:
    """Convert the generation specification's shape to the internal shape."""
    if not isinstance(raw, dict):
        return _build_embedded()
    out = _build_embedded()
    ts = raw.get('table_sizes_per_instance') or raw.get('table_sizes')
    if isinstance(ts, dict):
        norm = {}
        for t, v in ts.items():
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                norm[t] = [int(v[0]), int(v[1])]
            elif isinstance(v, (int, float)):
                norm[t] = [int(v), int(v)]
        if norm:
            out['table_sizes'] = norm
    nt = raw.get('null_targets')
    if isinstance(nt, list):
        rates = {}
        stats = raw.get('column_statistics') or {}
        for item in nt:
            if not isinstance(item, str) or '.' not in item:
                continue
            t, c = item.split('.', 1)
            rate = _null_rate_from_stats(stats, t, c)
            if rate is None:
                rate = (out.get('null_targets', {}).get(t, {}) or {}).get(c, 0.0)
            rates.setdefault(t, {})[c] = rate
        if rates:
            out['null_targets'] = rates
    rules = raw.get('semantic_rules_and_formulas')
    if isinstance(rules, list):
        parsed = {}
        for item in rules:
            f = item.get('formula') if isinstance(item, dict) else item
            p = _parse_formula(f)
            if p:
                t, c, r = p
                parsed.setdefault(t, {})[c] = r
        if parsed:
            out['semantic_rules'] = parsed
    exc = raw.get('per_column_exceptions')
    if isinstance(exc, list):
        bv, dup = {}, {}
        for e in exc:
            if not isinstance(e, dict):
                continue
            t, c, pat = e.get('table'), e.get('column'), e.get('pattern')
            tg = e.get('targets') or {}
            if pat == 'comparison_boundary' and tg.get('values'):
                bv.setdefault(t, {})[c] = list(tg['values'])
            if pat == 'duplicates_for_distinct':
                dup.setdefault(t, {})[c] = 0.3
        if bv:
            out['boundary_values'] = bv
        if dup:
            out['duplicate_share'] = dup
    deps = raw.get('dependencies')
    if isinstance(deps, list):
        parents = {}
        for d in deps:
            if isinstance(d, dict) and d.get('parent_table') and d.get('parent_column'):
                parents.setdefault(d['parent_table'], {})[d['parent_column']] = True
        if parents:
            out['unmatched_parents'] = parents
    out['boundary_values'] = _filter_boundaries(out.get('boundary_values', {}), out.get('semantic_rules', {}))
    return out
