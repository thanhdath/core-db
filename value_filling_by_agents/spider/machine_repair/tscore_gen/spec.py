"""Specification loading: domains, planted literals, fixed sizes and NULL targets."""
import copy
import json
import re

_DEFAULT = {
    'table_sizes': {'machine': 8, 'repair': 8, 'technician': 8, 'repair_assignment': 8},
    'literal_pool': {'machine.value_points': [70]},
    'boundary_values': {'technician.Age': [35, 36, 37, 38]},
    'null_targets': {'technician.Team': [0.05, 0.30], 'machine.Machine_series': [0.05, 0.30]},
    'ranges': {
        'machine.Making_Year': [1991, 1998],
        'machine.value_points': [0.0, 238.0],
        'machine.quality_rank': [1, 13],
        'technician.Age': [18, 80],
        'technician.Starting_Year': [1990.0, 2020.0],
    },
    'duplicate_targets': ['technician.Team', 'technician.Name'],
    'group_sizes_targets': ['technician.Name'],
    'tie_targets': ['technician.technician_id', 'technician.Starting_Year'],
    'not_null': ['repair.Launch_Date'],
    'soft_rules': [],
}


def _norm_key(k: str) -> tuple:
    """'table.col' -> (table, col); keeps the column spelling used by the schema."""
    if '.' in k:
        t, c = k.split('.', 1)
        return t, c
    return '', k


def default_spec() -> dict:
    """Deep enough copy of the built-in spec."""
    return copy.deepcopy(_DEFAULT)


def _extract_boundary(text: str):
    """'plant values 35, 36, 37, 38; ...' -> [ints]."""
    m = re.search(r'plant values\s+([0-9., \-]+)', text or '')
    if not m:
        return []
    vals = []
    for tok in re.split(r'[,\s]+', m.group(1).strip()):
        tok = tok.strip()
        if re.fullmatch(r'-?\d+(?:\.\d+)?', tok):
            vals.append(int(tok) if re.fullmatch(r'-?\d+', tok) else float(tok))
    return vals


def _share_band(text: str) -> list:
    """'5-30 %' -> [0.05, 0.30]."""
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*%', text or '')
    if m:
        return [int(m.group(1)) / 100.0, int(m.group(2)) / 100.0]
    return [0.05, 0.10]


def load_spec(path: str) -> dict:
    """Read a JSON spec and normalise its keys into {(table, column): ...} Python structures."""
    with open(path) as f:
        raw = json.load(f)
    spec = default_spec()
    if not isinstance(raw, dict):
        return spec
    if isinstance(raw.get('table_sizes_per_instance'), dict):
        spec['table_sizes'] = dict(raw['table_sizes_per_instance'])
    sizes = raw.get('table_sizes')
    if isinstance(sizes, dict):
        spec['table_sizes'].update(sizes)
    lp = {}
    for item in raw.get('literal_pool_other_columns') or []:
        col = item.get('column')
        if col:
            lp.setdefault(col, [])
            lp[col].extend(item.get('literals') or [])
    for col, vals in (raw.get('literal_pool') or {}).items():
        lp.setdefault(col, [])
        lp[col].extend(vals if isinstance(vals, list) else [vals])
    if lp:
        spec['literal_pool'] = {k: list(v) for k, v in lp.items()}
    bv = dict(raw.get('boundary_values') or {})
    for item in raw.get('per_column_exceptions') or []:
        if item.get('pattern') == 'comparison_boundary':
            col = item.get('column')
            vals = _extract_boundary(item.get('targets', ''))
            if isinstance(col, str) and vals:
                bv[col] = vals
    if bv:
        spec['boundary_values'] = bv
    nt = {}
    if isinstance(raw.get('null_targets'), list):
        for col in raw['null_targets']:
            nt[col] = [0.05, 0.10]
    for item in raw.get('per_column_exceptions') or []:
        if item.get('pattern') == 'null_rows' and isinstance(item.get('column'), str):
            nt[item['column']] = _share_band(item.get('targets', ''))
    if nt:
        spec['null_targets'] = nt
    rng = dict(raw.get('ranges') or {})
    soft = list(spec.get('soft_rules') or [])
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c = rule.get('table', ''), rule.get('column', '')
        f = rule.get('formula', '')
        if not (t and c):
            continue
        key = t + '.' + c
        m = re.search(r'between\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)', f, re.I)
        if m:
            rng[key] = [float(m.group(1)), float(m.group(2))]
            soft.append({'column': key, 'formula': f, 'kind': 'range'})
            continue
        m = re.search(r'>=\s*(-?\d+(?:\.\d+)?)', f)
        if m:
            lo = float(m.group(1))
            hi = rng.get(key, [None, None])[1]
            rng[key] = [lo, hi if hi is not None else lo + 1000.0]
            soft.append({'column': key, 'formula': f, 'kind': 'min'})
            continue
        m = re.search(r'>\s*(-?\d+(?:\.\d+)?)', f)
        if m:
            lo = float(m.group(1)) + 1.0
            hi = rng.get(key, [None, None])[1]
            rng[key] = [lo, hi if hi is not None else lo + 1000.0]
            soft.append({'column': key, 'formula': f, 'kind': 'min'})
            continue
        if re.search(r'is\s+not\s+null', f, re.I):
            spec.setdefault('not_null', [])
            if key not in spec['not_null']:
                spec['not_null'].append(key)
            soft.append({'column': key, 'formula': f, 'kind': 'not_null'})
    if rng:
        for k, v in rng.items():
            spec['ranges'][k] = v
    spec['soft_rules'] = soft
    dup, grp, tie = set(), set(), set()
    for item in raw.get('per_column_exceptions') or []:
        col = item.get('column')
        pat = item.get('pattern')
        if not isinstance(col, str):
            continue
        if pat == 'duplicates_for_distinct':
            dup.add(col)
        elif pat == 'group_sizes':
            grp.add(col)
        elif pat == 'ties_for_order_limit':
            tie.add(col)
    if dup:
        spec['duplicate_targets'] = sorted(dup)
    if grp:
        spec['group_sizes_targets'] = sorted(grp)
    if tie:
        spec['tie_targets'] = sorted(tie)
    return spec
