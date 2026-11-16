"""Specification loader and per-column rule table (tscore_gen/specification.json)."""
import json
import os

_SPEC_PATH = os.path.join(os.path.dirname(__file__), 'specification.json')


def load_specification(path: str = _SPEC_PATH) -> dict:
    """Read the specification JSON; empty dict if absent (generic behaviour only)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _key(t: str, c: str) -> str:
    return '%s.%s' % (t, c)


def column_rules(spec: dict) -> dict:
    """Map 'table.column' -> merged exception targets (lower-case table/column)."""
    out: dict = {}
    for ex in spec.get('per_column_exceptions', []) or []:
        col = ex.get('column', '')
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        k = _key(t.lower(), c.lower())
        d = out.setdefault(k, {'patterns': [], 'values': [], 'bounds': None, 'enum': None,
                               'null_share': None, 'duplicate_share': None, 'group_sizes': None,
                               'unmatched_join': False, 'child_null_fk': False,
                               'parent_without_children': False, 'equal_and_one_step': False,
                               'rows_with_different_values': False, 'aggregate_boundary': None})
        pat = ex.get('pattern')
        d['patterns'].append(pat)
        tg = ex.get('targets', {}) or {}
        if 'values' in tg:
            d['values'].extend(tg['values'])
        if pat == 'comparison_boundary' and 'values' in tg:
            nums = [v for v in tg['values'] if isinstance(v, (int, float))]
            if nums:
                d['bounds'] = (min(nums), max(nums))
        if pat == 'duplicates_for_distinct' and 'duplicate_share' in tg:
            d['duplicate_share'] = tg['duplicate_share']
        if pat == 'null_rows' and 'null_share' in tg:
            d['null_share'] = tg['null_share']
        if pat == 'group_sizes' and 'group_sizes' in tg:
            d['group_sizes'] = tg['group_sizes']
        if pat == 'unmatched_join_rows':
            d['unmatched_join'] = True
            d['parent_without_children'] = bool(tg.get('parent_rows_without_children'))
            d['child_null_fk'] = bool(tg.get('child_rows_with_null_fk'))
        if pat == 'comparison_boundary' and 'equal_and_one_step_from' in tg:
            d['equal_and_one_step'] = True
        if pat == 'rows_with_different_values':
            d['rows_with_different_values'] = True
        if pat == 'aggregate_boundary':
            d['aggregate_boundary'] = tg
    return out


def semantic_rules(spec: dict) -> dict:
    """Map 'table.column' -> list of formula strings (kept for documentation; applied in Python)."""
    out: dict = {}
    for r in spec.get('semantic_rules_and_formulas', []) or []:
        k = _key(str(r.get('table', '')).lower(), str(r.get('column', '')).lower())
        out.setdefault(k, []).append(r.get('formula', ''))
    return out


def enum_values(spec: dict) -> dict:
    """Map 'table.column' -> list of allowed values from Type IN (...) formulas."""
    out: dict = {}
    for r in spec.get('semantic_rules_and_formulas', []) or []:
        f = str(r.get('formula', ''))
        if ' IN (' in f.upper():
            vals = []
            body = f[f.upper().index(' IN (') + 5:].strip()
            body = body.rstrip(')')
            for part in body.split(','):
                part = part.strip().strip("'\"")
                if part:
                    vals.append(part)
            if vals:
                out[_key(str(r.get('table', '')).lower(), str(r.get('column', '')).lower())] = vals
    return out


def null_targets(spec: dict) -> set:
    """Set of 'table.column' (lower-case) that must contain NULL rows."""
    return {str(x).lower() for x in spec.get('null_targets', []) or []}


def table_sizes(spec: dict) -> dict:
    """Map table (lower-case) -> target number of generated rows."""
    return {str(k).lower(): int(v) for k, v in (spec.get('table_sizes_per_instance', {}) or {}).items()}


def dependencies(spec: dict) -> list:
    """List of (child_table, child_col, parent_table, parent_col) lower-case."""
    out = []
    for d in spec.get('dependencies', []) or []:
        out.append((str(d.get('child_column', '')).split('.')[0].lower(),
                    str(d.get('child_column', '')).split('.')[-1].lower(),
                    str(d.get('parent_table', '')).lower(),
                    str(d.get('parent_column', '')).lower()))
    return out
