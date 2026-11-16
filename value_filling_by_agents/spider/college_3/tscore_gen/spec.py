"""Specification loader: value domains, ranges, enums, dependencies, table sizes, NULL targets."""
import json
import os
import re

DEFAULT_SPEC = {
    "tables": {
        "GradeDomain": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"],
        "GradeValue": {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
                       "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "D-": 0.7, "F": 0.0},
        "Division": ["AS", "EN"],
        "Rank": ["Instructor", "Professor", "AssocProf", "AsstProf"],
        "Sex": ["F", "M"],
        "ApptType": ["Primary", "Secondary"],
        "Credits": [1, 2, 3, 4],
        "Age": [16, 26],
        "Gradepoint": [0.0, 4.0],
        "CityCode": ["BAL", "HKG", "WAS", "CHI", "YYZ", "PIT", "HOU", "PHL", "NYC"],
        "Building": ["Mergenthaler", "Mudd", "Remsen", "Gilman", "Krieger", "Macaulay",
                     "Bloomberg", "Ames", "NEB", "Barton"],
        "Days": ["MTW", "Th", "ThF", "MW", "W", "M", "T", "MT", "F", "WTh", "TTh"],
        "Hours": ["1", "2", "3", "4", "9", "10", "11", "12", "1-2:15", "1-2:30", "10:30-12"],
        "CIDPrefix": ["050", "520", "550", "600"],
        "DNOBoundary": [139, 140, 141, 519, 520, 521],
        "DNOObserved": [10, 20, 30, 40, 50, 60, 70, 90],
        "DNOExtra": [100, 140, 190, 520, 530, 540, 550, 600],
        "FacIDObserved": [1082, 1121, 1148, 1172, 1177, 1193, 1823, 2028],
        "StuIDObserved": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008],
    },
    "ranges": {
        "Student.Age": [16, 26],
        "Course.Credits": [1, 4],
        "Gradeconversion.gradepoint": [0.0, 4.0],
    },
    "enums": {
        "Student.Sex": ["F", "M"],
        "Faculty.Sex": ["F", "M"],
        "Faculty.Rank": ["Instructor", "Professor", "AssocProf", "AsstProf"],
        "Department.Division": ["AS", "EN"],
        "Member_of.Appt_Type": ["Primary", "Secondary"],
        "Enrolled_in.Grade": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"],
    },
    "codes": {
        "Student.city_code": 3,
    },
    "domains": {
        "Department.Building": ["Mergenthaler", "Mudd", "Remsen", "Gilman", "Krieger", "Macaulay",
                                "Bloomberg", "Ames", "NEB", "Barton"],
        "Faculty.Building": ["Mergenthaler", "Mudd", "Remsen", "Gilman", "Krieger", "Macaulay",
                             "Bloomberg", "Ames", "NEB", "Barton"],
        "Course.Days": ["MTW", "Th", "ThF", "MW", "W", "M", "T", "MT", "F", "WTh", "TTh"],
        "Course.Hours": ["1", "2", "3", "4", "9", "10", "11", "12", "1-2:15", "1-2:30", "10:30-12"],
    },
    "cid_prefixes": ["050", "520", "550", "600"],
    "table_sizes": {"Department": 26, "Faculty": 58, "Student": 34, "Course": 76,
                    "Member_of": 63, "Minor_in": 10, "Enrolled_in": 210, "Gradeconversion": 13},
    "null_targets": ["Student.Major", "Student.Advisor", "Student.city_code",
                     "Faculty.Phone", "Faculty.Room", "Faculty.Building",
                     "Department.Division", "Department.Room", "Department.Building", "Department.DPhone",
                     "Course.CName", "Course.Credits", "Course.Instructor", "Course.Days",
                     "Course.Hours", "Course.DNO",
                     "Member_of.FacID", "Member_of.DNO", "Member_of.Appt_Type",
                     "Minor_in.StuID", "Minor_in.DNO",
                     "Enrolled_in.StuID", "Enrolled_in.CID", "Enrolled_in.Grade",
                     "Gradeconversion.gradepoint"],
    "dependencies": [
        {"child": "Student.Major", "parent": "Department", "parent_column": "DNO"},
        {"child": "Student.Advisor", "parent": "Faculty", "parent_column": "FacID"},
        {"child": "Member_of.FacID", "parent": "Faculty", "parent_column": "FacID"},
        {"child": "Member_of.DNO", "parent": "Department", "parent_column": "DNO"},
        {"child": "Course.Instructor", "parent": "Faculty", "parent_column": "FacID"},
        {"child": "Course.DNO", "parent": "Department", "parent_column": "DNO"},
        {"child": "Minor_in.StuID", "parent": "Student", "parent_column": "StuID"},
        {"child": "Minor_in.DNO", "parent": "Department", "parent_column": "DNO"},
        {"child": "Enrolled_in.StuID", "parent": "Student", "parent_column": "StuID"},
        {"child": "Enrolled_in.CID", "parent": "Course", "parent_column": "CID"},
        {"child": "Enrolled_in.Grade", "parent": "Gradeconversion", "parent_column": "lettergrade"},
    ],
    "group_size_columns": ["Department.DNO", "Minor_in.DNO", "Course.CName", "Course.CID",
                           "Enrolled_in.CID"],
    "aggregate_boundary": {"columns": ["Course.CName", "Course.CID", "Enrolled_in.CID",
                                       "Enrolled_in.StuID"],
                           "values": [4, 5, 6]},
    "distinct_columns": ["Department.DNO", "Faculty.Lname", "Student.Fname", "Student.LName",
                         "Department.DName", "Department.Room", "Faculty.Room"],
    "order_tie_columns": ["Department.DNO", "Minor_in.DNO", "Course.Instructor", "Faculty.Rank"],
    "unmatched_join_columns": ["Minor_in.DNO", "Member_of.DNO", "Course.DNO", "Course.Instructor"],
    "comparison_boundary": {
        "Department.Division": ["EN", "en"],
    },
    "boundary_probe_columns": ["Department.DNO", "Minor_in.DNO", "Member_of.DNO"],
    "duplicate_share": [0.20, 0.50],
    "null_share": 0.10,
}

_KEY_COLUMNS = {
    "Department.DNO", "Faculty.FacID", "Student.StuID", "Course.CID",
    "Gradeconversion.lettergrade",
    "Student.Major", "Student.Advisor", "Member_of.FacID", "Member_of.DNO",
    "Course.Instructor", "Course.DNO", "Minor_in.StuID", "Minor_in.DNO",
    "Enrolled_in.StuID", "Enrolled_in.CID", "Enrolled_in.Grade",
}

_RANGE_RE = re.compile(r'^\s*([\w.]+)\s+BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)\s*$', re.I)
_IN_RE = re.compile(r"^\s*([\w.]+)\s+IN\s*\((.*)\)\s*$", re.I)
_ITEM_RE = re.compile(r"'((?:[^']|'')*)'|(-?\d+(?:\.\d+)?)")


def _parse_formula(formula: str):
    """Translate one semantic formula into (kind, column, payload) or None."""
    m = _RANGE_RE.match(formula)
    if m:
        col, lo, hi = m.group(1), m.group(2), m.group(3)
        if '.' in lo or '.' in hi:
            return ('range', col, [float(lo), float(hi)])
        return ('range', col, [int(lo), int(hi)])
    m = _IN_RE.match(formula)
    if m:
        col, inner = m.group(1), m.group(2)
        if inner.strip().lower().startswith('select'):
            return None
        vals = []
        for it in _ITEM_RE.finditer(inner):
            if it.group(1) is not None:
                vals.append(it.group(1).replace("''", "'"))
            else:
                v = it.group(2)
                vals.append(float(v) if '.' in v else int(v))
        if vals:
            return ('enum', col, vals)
    return None


def _apply_semantic_rules(spec: dict, rules: list) -> None:
    """Fold semantic_rules_and_formulas into ranges/enums (by construction)."""
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        f = r.get('formula')
        if not isinstance(f, str):
            continue
        parsed = _parse_formula(f)
        if parsed is None:
            continue
        kind, col, payload = parsed
        if kind == 'range':
            spec.setdefault('ranges', {})[col] = payload
        else:
            spec.setdefault('enums', {})[col] = payload


def _apply_atomic_ops(spec: dict, ops: dict) -> None:
    """Fold the atomic-operation column list into the sampler structures."""
    for c in (ops or {}).get('columns', []) or []:
        col = c.get('column')
        pats = c.get('patterns', {}) or {}
        if not col:
            continue
        if 'group_sizes' in pats:
            spec.setdefault('group_size_columns', [])
            if col not in spec['group_size_columns']:
                spec['group_size_columns'].append(col)
        if 'aggregate_boundary' in pats:
            ab = spec.setdefault('aggregate_boundary', {'columns': [], 'values': [4, 5, 6]})
            if col not in ab['columns']:
                ab['columns'].append(col)
            for t in pats['aggregate_boundary'].get('targets', {}).get('values', []) or []:
                if isinstance(t, int) and t not in ab['values']:
                    ab['values'].append(t)
        if 'duplicates_for_distinct' in pats:
            spec.setdefault('distinct_columns', [])
            if col not in spec['distinct_columns']:
                spec['distinct_columns'].append(col)
        if 'ties_for_order_limit' in pats:
            spec.setdefault('order_tie_columns', [])
            if col not in spec['order_tie_columns']:
                spec['order_tie_columns'].append(col)
        if 'unmatched_join_rows' in pats and col not in _KEY_COLUMNS:
            spec.setdefault('unmatched_join_columns', [])
            if col not in spec['unmatched_join_columns']:
                spec['unmatched_join_columns'].append(col)
        if 'comparison_boundary' in pats:
            vals = pats['comparison_boundary'].get('targets', {}).get('values', []) or []
            if col in _KEY_COLUMNS:
                spec.setdefault('boundary_probe_columns', [])
                if col not in spec['boundary_probe_columns']:
                    spec['boundary_probe_columns'].append(col)
            else:
                spec.setdefault('comparison_boundary', {})[col] = list(vals)


def load_spec(path: str) -> dict:
    """Load specification.json if present, else the built-in default; merge over default."""
    spec = json.loads(json.dumps(DEFAULT_SPEC))
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                user = json.load(f)
            if isinstance(user, dict):
                for k, v in user.items():
                    if k in ('semantic_rules_and_formulas', 'atomic_operations',
                             'table_sizes_per_instance', 'generic_sampling_rules',
                             'per_column_exceptions', 'supporting_evidence', 'uncertainty',
                             'null_targets', 'dependencies'):
                        continue
                    if isinstance(v, dict) and isinstance(spec.get(k), dict):
                        spec[k].update(v)
                    else:
                        spec[k] = v
                if isinstance(user.get('table_sizes_per_instance'), dict):
                    spec['table_sizes'] = dict(user['table_sizes_per_instance'])
                if isinstance(user.get('null_targets'), list):
                    spec['null_targets'] = list(user['null_targets'])
                if isinstance(user.get('dependencies'), list):
                    spec['dependencies'] = list(user['dependencies'])
                _apply_semantic_rules(spec, user.get('semantic_rules_and_formulas'))
                _apply_atomic_ops(spec, user.get('atomic_operations'))
        except Exception:
            pass
    return spec
