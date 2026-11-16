"""The generation specification (specification.json) as a Python object."""
import json
import os
import re

DEFAULT_SPEC = {
    "table_sizes": {"EMPLOYEE": 40, "DEPARTMENT": 12, "COURSE": 8, "CLASS": 15,
                    "STUDENT": 10, "PROFESSOR": 24, "ENROLL": 8},
    "size_mode": "random",
    "null_share": 0.15,
    "duplicate_share": 0.3,
    "enumeration": {
        "COURSE.CRS_CREDIT": [3.0, 4.0],
        "STUDENT.STU_CLASS": ["Fr", "So", "Jr", "Sr"],
        "STUDENT.STU_TRANSFER": [0, 1],
        "EMPLOYEE.EMP_JOBCODE": ["CUST", "TECH", "PROF", "CLRK"],
        "PROFESSOR.PROF_HIGH_DEGREE": ["Ph.D.", "MA", "DBA", "MBA"],
        "ENROLL.ENROLL_GRADE": ["A", "B", "C", "D", "F"],
        "CLASS.CLASS_SECTION": ["1", "2", "3"],
    },
    "ranges": {
        "STUDENT.STU_GPA": [0.0, 4.0],
        "STUDENT.STU_HRS": [0, None],
    },
    "formulas": [
        {"table": "EMPLOYEE", "column": "EMP_HIREDATE", "formula": "EMP_HIREDATE > EMP_DOB"},
    ],
    "null_targets": [],
    "null_shares": {"PROFESSOR.PROF_HIGH_DEGREE": 0.15},
    "comparison_boundary": {
        "DEPARTMENT.DEPT_NAME": ["History", "history", "Accounting", "accounting", "Biology", "biology"],
        "DEPARTMENT.DEPT_CODE": ["HIST", "hist", "BIOL", "biol", "ACCT", "acct"],
        "CLASS.CRS_CODE": ["ACCT-211", "acct-211", "CIS-220", "cis-220", "QM-261", "qm-261"],
        "COURSE.CRS_CODE": ["ACCT-211", "acct-211"],
        "PROFESSOR.DEPT_CODE": ["BIOL", "biol", "HIST", "hist", "ACCT", "acct"],
        "CLASS.CLASS_CODE": ["10017", "10018", "10019"],
        "ENROLL.CLASS_CODE": ["10017", "10018", "10019"],
        "EMPLOYEE.EMP_LNAME": ["Heffington", "heffington", "Graztevski", "graztevski"],
        "COURSE.CRS_DESCRIPTION": ["Accounting I", "accounting i"],
        "EMPLOYEE.EMP_JOBCODE": ["PROF", "prof"],
    },
    "group_sizes": {
        "DEPARTMENT.DEPT_CODE": [1, 2, 3],
        "STUDENT.DEPT_CODE": [1, 2, 3],
        "COURSE.DEPT_CODE": [1, 2, 3],
    },
    "ties": {
        "STUDENT.DEPT_CODE": True,
        "EMPLOYEE.EMP_FNAME": True,
    },
    "unmatched_join": {},
    "dependencies": [
        {"child": "CLASS.CRS_CODE", "parent": "COURSE.CRS_CODE"},
        {"child": "CLASS.PROF_NUM", "parent": "EMPLOYEE.EMP_NUM"},
        {"child": "COURSE.DEPT_CODE", "parent": "DEPARTMENT.DEPT_CODE"},
        {"child": "DEPARTMENT.EMP_NUM", "parent": "EMPLOYEE.EMP_NUM"},
        {"child": "ENROLL.CLASS_CODE", "parent": "CLASS.CLASS_CODE"},
        {"child": "ENROLL.STU_NUM", "parent": "STUDENT.STU_NUM"},
        {"child": "PROFESSOR.EMP_NUM", "parent": "EMPLOYEE.EMP_NUM"},
        {"child": "PROFESSOR.DEPT_CODE", "parent": "DEPARTMENT.DEPT_CODE"},
        {"child": "STUDENT.DEPT_CODE", "parent": "DEPARTMENT.DEPT_CODE"},
        {"child": "STUDENT.PROF_NUM", "parent": "PROFESSOR.EMP_NUM"},
    ],
}

_RULE_ENUMS = {
    "COURSE.CRS_CREDIT": [3.0, 4.0],
    "STUDENT.STU_CLASS": ["Fr", "So", "Jr", "Sr"],
    "STUDENT.STU_TRANSFER": [0, 1],
    "EMPLOYEE.EMP_JOBCODE": ["CUST", "TECH", "PROF", "CLRK"],
    "PROFESSOR.PROF_HIGH_DEGREE": ["Ph.D.", "MA", "DBA", "MBA"],
    "ENROLL.ENROLL_GRADE": ["A", "B", "C", "D", "F"],
    "CLASS.CLASS_SECTION": ["1", "2", "3"],
}
_RULE_RANGES = {
    "STUDENT.STU_GPA": [0.0, 4.0],
    "STUDENT.STU_HRS": [0, None],
}

_IN_LIST = re.compile(r"\bIN\s*\(([^()]*)\)", re.I)
_GE = re.compile(r">=\s*(-?\d+(?:\.\d+)?)")
_GT = re.compile(r">\s*(-?\d+(?:\.\d+)?)")
_BETWEEN = re.compile(r"BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", re.I)


def _parse_rule_values(formula: str):
    """Extract an enumeration or a range from a rule text (IN (...), >= c, BETWEEN a AND b)."""
    m = _IN_LIST.search(formula)
    if m:
        vals = []
        for it in m.group(1).split(','):
            it = it.strip().strip("'\"")
            if not it:
                continue
            try:
                vals.append(float(it) if '.' in it else int(it))
            except ValueError:
                vals.append(it)
        if vals:
            return 'enum', vals
    m = _BETWEEN.search(formula)
    if m:
        return 'range', [float(m.group(1)), float(m.group(2))]
    m = _GE.search(formula)
    if m:
        return 'range', [float(m.group(1)), None]
    m = _GT.search(formula)
    if m:
        return 'range', [float(m.group(1)) + 1, None]
    return None, None


def _share_from_text(txt) -> float:
    """'5-30 %' -> 0.15 (midpoint); 'none (NOT NULL column)' -> 0.0; float -> itself."""
    if isinstance(txt, (int, float)):
        return float(txt)
    if not isinstance(txt, str):
        return 0.15
    if 'none' in txt.lower():
        return 0.0
    nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', txt)]
    if not nums:
        return 0.15
    if len(nums) >= 2:
        return (nums[0] + nums[1]) / 200.0
    return nums[0] / 100.0


def _norm_key(k: str) -> str:
    return k.strip().upper()


def normalize(raw: dict) -> dict:
    """Map the delivered specification structure onto the flat schema."""
    spec = {
        "table_sizes": {},
        "size_mode": "random",
        "null_share": 0.15,
        "duplicate_share": 0.3,
        "enumeration": {},
        "ranges": {},
        "formulas": [],
        "null_targets": [],
        "null_shares": {},
        "comparison_boundary": {},
        "group_sizes": {},
        "ties": {},
        "unmatched_join": {},
        "dependencies": [],
    }
    if not isinstance(raw, dict):
        return spec

    sizes = raw.get('table_sizes_per_instance') or raw.get('table_sizes') or {}
    for t, n in sizes.items():
        try:
            spec['table_sizes'][_norm_key(t)] = int(n)
        except (TypeError, ValueError):
            pass
    if raw.get('size_mode'):
        spec['size_mode'] = raw['size_mode']
    if raw.get('null_share') is not None:
        spec['null_share'] = float(raw['null_share'])
    if raw.get('duplicate_share') is not None:
        spec['duplicate_share'] = float(raw['duplicate_share'])

    for k in ('enumeration', 'ranges', 'comparison_boundary', 'group_sizes', 'ties', 'unmatched_join'):
        for col, v in (raw.get(k) or {}).items():
            spec[k][_norm_key(col)] = v
    for f in raw.get('formulas') or []:
        spec['formulas'].append(f)
    for nt in raw.get('null_targets') or []:
        spec['null_targets'].append(_norm_key(nt))
    for col, sh in (raw.get('null_shares') or {}).items():
        spec['null_shares'][_norm_key(col)] = float(sh)
    for d in raw.get('dependencies') or []:
        spec['dependencies'].append(d)

    for rule in raw.get('semantic_rules_and_formulas') or []:
        t = _norm_key(rule.get('table', ''))
        c = _norm_key(rule.get('column', ''))
        if not t or not c:
            continue
        key = '%s.%s' % (t, c)
        formula = rule.get('formula') or ''
        kind, vals = _parse_rule_values(formula)
        if kind == 'enum':
            spec['enumeration'].setdefault(key, vals)
        elif kind == 'range':
            spec['ranges'].setdefault(key, vals)
        if '>' in formula and re.search(r'\b[A-Za-z_]\w*\b\s*>\s*\b[A-Za-z_]\w*\b', formula) \
                and not re.search(r'\d', formula):
            spec['formulas'].append({'table': t, 'column': c, 'formula': formula})
        if 'IS NOT NULL' in formula.upper():
            if key not in spec['null_targets']:
                spec['null_targets'].append(key)

    for exc in raw.get('per_column_exceptions') or []:
        pat = exc.get('pattern')
        targets = exc.get('targets') or {}
        if pat == 'comparison_boundary':
            for col, vals in targets.items():
                spec['comparison_boundary'][_norm_key(col)] = list(vals)
        elif pat == 'unmatched_join_rows':
            for col, info in targets.items():
                spec['unmatched_join'][_norm_key(col)] = info
        elif pat == 'duplicates_for_distinct':
            for col, info in targets.items():
                sh = _share_from_text((info or {}).get('duplicate_share'))
                spec.setdefault('duplicate_shares', {})[_norm_key(col)] = sh
        elif pat == 'group_sizes':
            for col, info in targets.items():
                gs = (info or {}).get('group_sizes', '1, 2 and >= 3')
                spec['group_sizes'][_norm_key(col)] = _parse_group_sizes(gs)
        elif pat == 'ties_for_order_limit':
            for col in targets:
                spec['ties'][_norm_key(col)] = True
        elif pat == 'null_rows':
            for col, info in targets.items():
                spec['null_shares'][_norm_key(col)] = _share_from_text((info or {}).get('null_share'))
                if _norm_key(col) not in spec['null_targets']:
                    spec['null_targets'].append(_norm_key(col))
        elif pat == 'null_in_count_column':
            for col, info in targets.items():
                spec['null_shares'][_norm_key(col)] = _share_from_text((info or {}).get('null_share'))

    for nt in raw.get('null_targets') or []:
        k = _norm_key(nt)
        if k not in spec['null_targets']:
            spec['null_targets'].append(k)

    for key, vals in _RULE_ENUMS.items():
        spec['enumeration'].setdefault(key, list(vals))
    for key, vals in _RULE_RANGES.items():
        spec['ranges'].setdefault(key, list(vals))
    if not any(f.get('formula', '').upper().find('HIREDATE') >= 0 for f in spec['formulas']):
        spec['formulas'].append({'table': 'EMPLOYEE', 'column': 'EMP_HIREDATE',
                                 'formula': 'EMP_HIREDATE > EMP_DOB'})
    return spec


def _parse_group_sizes(txt) -> list:
    """'1, 2 and >= 3' -> [1, 2, 3]."""
    if isinstance(txt, list):
        return [int(x) for x in txt]
    nums = [int(x) for x in re.findall(r'\d+', str(txt))]
    return nums or [1, 2, 3]


def load_spec() -> dict:
    """Load the specification written by the pipeline (normalised), or the default."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specification.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return normalize(raw)
        except Exception:
            pass
    return normalize(DEFAULT_SPEC)
