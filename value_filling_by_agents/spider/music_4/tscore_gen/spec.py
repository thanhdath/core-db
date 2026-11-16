"""Specification loader: turns the generation specification into plain Python data."""
import json
import re

_DEFAULT = {
    'table_sizes': {},
    'integer_ranges': {},
    'real_ranges': {},
    'enums': {},
    'boundaries': {},
    'null_targets': [],
    'null_share': 0.15,
    'duplicate_share': 0.30,
    'duplicate_targets': [],
    'orphan_prob': 0.0,
    'fk_null_prob': 0.15,
    'parent_without_child': [],
    'group_sizes': {},
    'aggregate_boundary': {},
    'ties': [],
    'rows_with_different_values': [],
    'dependencies': [],
}


def _key(t, c):
    return '%s.%s' % (t, c)


def _parse_range(formula: str):
    """'Age BETWEEN 18 AND 49' -> (18, 49); 'Weeks_on_Top BETWEEN 1.0 AND 3.0' -> (1.0, 3.0)."""
    m = re.search(r'between\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)', formula, re.I)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return (int(a), int(b)) if a == int(a) and b == int(b) else (a, b)
    return None


def _parse_enum(formula: str):
    """\"Result IN ('Nominated','Awarded') OR Result IS NULL\" -> ['Nominated', 'Awarded']."""
    m = re.search(r'\bin\s*\(([^)]*)\)', formula, re.I)
    if not m:
        return None
    vals = re.findall(r"'((?:[^']|'')*)'", m.group(1))
    return [v.replace("''", "'") for v in vals] if vals else None


def load_specification(path) -> dict:
    """Read specification.json (if any) and normalise it into the dict used by the samplers."""
    spec = json.loads(json.dumps(_DEFAULT))
    raw = {}
    if path and isinstance(path, str):
        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    sizes = raw.get('table_sizes_per_instance') or {}
    if isinstance(sizes, dict):
        spec['table_sizes'] = {str(k): int(v) for k, v in sizes.items() if isinstance(v, (int, float))}

    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c = rule.get('table'), rule.get('column')
        f = rule.get('formula') or ''
        if not t or not c:
            continue
        k = _key(t, c)
        rng = _parse_range(f)
        if rng is not None:
            if isinstance(rng[0], int) and isinstance(rng[1], int):
                spec['integer_ranges'][k] = list(rng)
            else:
                spec['real_ranges'][k] = list(rng)
        en = _parse_enum(f)
        if en:
            spec['enums'][k] = en

    for ex in raw.get('per_column_exceptions') or []:
        pat = ex.get('pattern')
        tg = ex.get('targets') or {}
        cols = tg.get('columns') or []
        if pat == 'null_rows':
            for c in cols:
                if c not in spec['null_targets']:
                    spec['null_targets'].append(c)
        elif pat == 'comparison_boundary':
            for c in cols:
                vals = tg.get('values') or []
                if vals:
                    spec['boundaries'][c] = list(vals)
        elif pat == 'ties_for_order_limit':
            for c in cols:
                if c not in spec['ties']:
                    spec['ties'].append(c)
        elif pat == 'rows_with_different_values':
            for c in cols:
                if c not in spec['rows_with_different_values']:
                    spec['rows_with_different_values'].append(c)
        elif pat == 'group_sizes':
            for c in cols:
                spec['group_sizes'][c] = [1, 2, 3]
        elif pat == 'aggregate_boundary':
            for c in cols:
                spec['aggregate_boundary'][c] = {'gt': 2, 'le': 1}
        elif pat == 'duplicates_for_distinct':
            for c in cols:
                if c not in spec['duplicate_targets']:
                    spec['duplicate_targets'].append(c)
        elif pat == 'unmatched_join_rows':
            rule = tg.get('rule') or ''
            for m in re.finditer(r'one\s+(\w+)\s+with\s+no', rule):
                t = m.group(1)
                if t not in spec['parent_without_child']:
                    spec['parent_without_child'].append(t)

    for d in raw.get('dependencies') or []:
        if d.get('child_column') and d.get('parent_table') and d.get('parent_column'):
            spec['dependencies'].append(d)

    ev = raw.get('supporting_evidence') or {}
    for k, v in ev.items():
        if k.endswith('_range') and isinstance(v, str):
            col = k[:-len('_range')]
            m = re.search(r'min\s+(-?\d+(?:\.\d+)?),\s*max\s+(-?\d+(?:\.\d+)?)', v)
            if m:
                a, b = float(m.group(1)), float(m.group(2))
                if col not in spec['integer_ranges'] and col not in spec['real_ranges']:
                    if a == int(a) and b == int(b):
                        spec['integer_ranges'][col] = [int(a), int(b)]
                    else:
                        spec['real_ranges'][col] = [a, b]
        elif k.endswith('_enum') and isinstance(v, str):
            col = k[:-len('_enum')]
            m = re.search(r'Rows:\s*(.*)$', v)
            if m and col not in spec['enums']:
                vals = [x.strip() for x in m.group(1).split(',') if x.strip()]
                if vals:
                    spec['enums'][col] = vals
    return spec


def spec_for(spec: dict, table: str, column: str) -> dict:
    """Per-column view of the specification (ranges, enum, boundaries, null/dup flags)."""
    k = _key(table, column)
    return {
        'int_range': spec['integer_ranges'].get(k),
        'real_range': spec['real_ranges'].get(k),
        'enum': spec['enums'].get(k),
        'boundaries': spec['boundaries'].get(k),
        'nullable_target': k in spec['null_targets'],
        'duplicate_target': k in spec['duplicate_targets'],
        'tie': k in spec['ties'],
        'different_values': k in spec['rows_with_different_values'],
        'group_sizes': spec['group_sizes'].get(k),
        'aggregate_boundary': spec['aggregate_boundary'].get(k),
    }
