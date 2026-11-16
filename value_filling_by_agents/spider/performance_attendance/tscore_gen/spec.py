"""Specification model: the generation specification as a Python object."""
import json
import os

SPEC = {
    "enums": {
        "member": {"Nationality": ["Uruguay", "Argentina", "United States"],
                   "Role": ["Prime Violin", "Violin", "Viola", "Cello", "Bass"]},
    },
    "ranges": {
        "performance": {"Attendance": [100, 3000], "Performance_ID": [1, 10 ** 6]},
        "member_attendance": {"Num_of_Pieces": [1, 4]},
    },
    "date_formats": {
        "performance": {"Date": ["Month D", "%B %d"]},
    },
    "table_sizes": {"member": 11, "performance": 6, "member_attendance": 8},
    "null_targets": ["performance.Date", "performance.Host", "performance.Location",
                     "performance.Attendance", "member.Name", "member.Nationality",
                     "member.Role", "member_attendance.Num_of_Pieces"],
    "duplicates_for_distinct": {
        "performance.Location": {"duplicate_share": [0.2, 0.5]},
        "member.Name": {"duplicate_share": [0.2, 0.5]},
        "performance.Attendance": {"duplicate_share": [0.2, 0.5]},
        "performance.Date": {"duplicate_share": [0.2, 0.5]},
        "performance.Host": {"duplicate_share": [0.2, 0.5]},
    },
    "group_sizes": {
        "performance.Location": {"group_sizes": [1, 2, 3], "duplicate_share": [0.2, 0.5]},
    },
    "ties_for_order_limit": {
        "performance.Location": {"tie_at_rank": [1], "direction": "DESC", "tie_on": ["COUNT(*)"]},
        "performance.Attendance": {"tie_at_rank": [10], "direction": "DESC"},
        "performance.Date": {"tie_at_rank": "any", "direction": "DESC"},
    },
    "aggregate_boundary": {
        "performance.Location": {"count": [1, 2, 3], "having": [">= 2", "> 1"]},
        "member_attendance.Performance_ID": {"count": [1, 2, 3]},
        "performance.Performance_ID": {"count": [1, 2, 3]},
    },
    "unmatched_join_rows": {
        "member_attendance.Performance_ID": {"parent": "performance.Performance_ID",
                                             "parent_rows_without_children": True,
                                             "child_rows_with_null_fk": False},
        "performance.Performance_ID": {"parent": "member_attendance.Performance_ID",
                                       "parent_rows_without_children": True,
                                       "child_rows_with_null_fk": False},
    },
    "null_rows": {
        "member_attendance.Member_ID": {"not_null": True},
        "member_attendance.Performance_ID": {"not_null": True},
    },
    "formulas": {
        "member.Member_ID": {"length_gt": 0},
        "performance.Performance_ID": {"gt": 0},
        "performance.Attendance": {"between": [100, 3000]},
        "member_attendance.Num_of_Pieces": {"between": [1, 4]},
    },
}


def _find_spec_file() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, 'specification.json')
    return cand if os.path.exists(cand) else ''


def _share_range(x):
    """Parse '20-50 %' / '20-50%' / [0.2,0.5] / 0.25 into (lo, hi) fractions."""
    if isinstance(x, (list, tuple)) and len(x) == 2:
        lo, hi = float(x[0]), float(x[1])
        if hi > 1.0:
            lo, hi = lo / 100.0, hi / 100.0
        return (lo, hi)
    if isinstance(x, (int, float)):
        v = float(x)
        return (v / 100.0, v / 100.0) if v > 1.0 else (v, v)
    if isinstance(x, str):
        import re
        m = re.findall(r'\d+(?:\.\d+)?', x)
        if len(m) >= 2:
            lo, hi = float(m[0]), float(m[1])
            if hi > 1.0:
                lo, hi = lo / 100.0, hi / 100.0
            return (lo, hi)
        if len(m) == 1:
            v = float(m[0])
            return (v / 100.0, v / 100.0) if v > 1.0 else (v, v)
    return (0.2, 0.5)


def _normalise(raw: dict) -> dict:
    """Translate the pipeline's raw specification into the sampler structure."""
    if 'per_column_exceptions' not in raw and 'generic_sampling_rules' not in raw:
        return raw
    out = {
        'enums': {}, 'ranges': {}, 'date_formats': {}, 'table_sizes': {},
        'null_targets': list(raw.get('null_targets', [])),
        'duplicates_for_distinct': {}, 'group_sizes': {}, 'ties_for_order_limit': {},
        'aggregate_boundary': {}, 'unmatched_join_rows': {}, 'null_rows': {}, 'formulas': {},
    }
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        out['table_sizes'][t] = int(n)
    for exc in raw.get('per_column_exceptions', []):
        col = exc.get('column', '')
        pat = exc.get('pattern', '')
        tg = exc.get('targets', {}) or {}
        if pat == 'duplicates_for_distinct':
            out['duplicates_for_distinct'][col] = {
                'duplicate_share': _share_range(tg.get('duplicate_share', '20-50 %'))}
        elif pat == 'group_sizes':
            gs = tg.get('group_sizes', '1, 2 and >= 3')
            sizes = []
            for tok in str(gs).replace('and', ',').split(','):
                tok = tok.strip()
                if tok.startswith('>='):
                    sizes.append(3)
                elif tok.isdigit():
                    sizes.append(int(tok))
            out['group_sizes'][col] = {
                'group_sizes': sizes or [1, 2, 3],
                'duplicate_share': _share_range(tg.get('duplicate_share', '20-50 %'))}
        elif pat == 'ties_for_order_limit':
            out['ties_for_order_limit'][col] = {
                'tie_at_rank': tg.get('tie_at_rank', [1]),
                'direction': tg.get('direction', 'DESC'),
                'tie_on': tg.get('tie_on', [])}
        elif pat == 'aggregate_boundary':
            vals = [v for v in tg.get('values', [1, 2, 3]) if isinstance(v, int)]
            out['aggregate_boundary'][col] = {
                'count': vals or [1, 2, 3],
                'having': tg.get('having', [])}
        elif pat == 'unmatched_join_rows':
            out['unmatched_join_rows'][col] = {
                'parent': (tg.get('joins_with') or [''])[0],
                'parent_rows_without_children': bool(tg.get('parent_rows_without_children', True)),
                'child_rows_with_null_fk': bool(tg.get('child_rows_with_null_fk', False))}
        elif pat == 'null_rows':
            out['null_rows'][col] = {'not_null': 'none' in str(tg.get('null_share', '')).lower()}
    for dep in raw.get('dependencies', []):
        ct, cc = dep.get('child_table'), dep.get('child_column')
        pt, pc = dep.get('parent_table'), dep.get('parent_column')
        if ct and cc and pt and pc:
            out['unmatched_join_rows'].setdefault(
                '%s.%s' % (ct, cc),
                {'parent': '%s.%s' % (pt, pc), 'parent_rows_without_children': True,
                 'child_rows_with_null_fk': False})
    for rule in raw.get('semantic_rules_and_formulas', []):
        t, c = rule.get('table'), rule.get('column')
        f = rule.get('formula', '')
        if not t or not c:
            continue
        key = '%s.%s' % (t, c)
        if 'BETWEEN' in f.upper():
            import re
            m = re.findall(r'-?\d+(?:\.\d+)?', f)
            if len(m) >= 2:
                out['ranges'].setdefault(t, {})[c] = [float(m[0]), float(m[1])]
                out['formulas'][key] = {'between': [float(m[0]), float(m[1])]}
        elif ' IN (' in f.upper():
            import re
            vals = re.findall(r"'([^']*)'", f)
            if vals:
                out['enums'].setdefault(t, {})[c] = vals
        elif 'IS NOT NULL' in f.upper():
            out['formulas'][key] = {'not_null': True}
        elif '> 0' in f:
            out['formulas'][key] = {'gt': 0}
        elif 'length' in f.lower():
            out['formulas'][key] = {'length_gt': 0}
    return out


def load_spec() -> dict:
    """Load specification.json if present (normalised), else the built-in defaults."""
    p = _find_spec_file()
    if p:
        try:
            with open(p) as f:
                return _normalise(json.load(f))
        except Exception:
            pass
    return SPEC


def split_key(qualified: str):
    """'table.column' -> (table, column)."""
    if '.' in qualified:
        t, c = qualified.split('.', 1)
        return t, c
    return None, qualified


def _iter_cols(spec: dict, pattern: str):
    for t, cols in spec.get(pattern, {}).items():
        for c, v in cols.items():
            yield t, c, v


def get_enum(spec: dict, table: str, col: str):
    for t, c, vals in _iter_cols(spec, 'enums'):
        if t.lower() == table.lower() and c.lower() == col.lower():
            return vals
    return None


def get_range(spec: dict, table: str, col: str):
    for t, c, rng in _iter_cols(spec, 'ranges'):
        if t.lower() == table.lower() and c.lower() == col.lower():
            return rng
    return None


def get_date_format(spec: dict, table: str, col: str):
    for t, c, fmt in _iter_cols(spec, 'date_formats'):
        if t.lower() == table.lower() and c.lower() == col.lower():
            return fmt
    return None


def get_formula(spec: dict, table: str, col: str):
    for t, c, f in _iter_cols(spec, 'formulas'):
        if t.lower() == table.lower() and c.lower() == col.lower():
            return f
    return None


def has_pattern(spec: dict, pattern: str, table: str, col: str) -> bool:
    return get_pattern(spec, pattern, table, col) is not None


def get_pattern(spec: dict, pattern: str, table: str, col: str):
    for t, c, v in _iter_cols(spec, pattern):
        if t.lower() == table.lower() and c.lower() == col.lower():
            return v
    return None


def null_targets(spec: dict) -> set:
    out = set()
    for x in spec.get('null_targets', []):
        t, c = split_key(x)
        out.add((t.lower(), c.lower()))
    return out


def is_null_target(spec: dict, table: str, col: str) -> bool:
    return (table.lower(), col.lower()) in null_targets(spec)


def is_not_null_rule(spec: dict, table: str, col: str) -> bool:
    """True if a semantic formula declares the column NOT NULL (overrides null_targets)."""
    f = get_formula(spec, table, col)
    return bool(f and f.get('not_null'))
