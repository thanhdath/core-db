"""Specification loading and per-column exception tables."""
import json
import re

_BUILTIN_EXCEPTIONS = {
    ('Activity', 'activity_name'): {
        'targets': ['Canoeing', 'canoeing', 'Kayaking', 'kayaking', 'Kayakg', 'kayakg'],
        'like_patterns': ['%Canoeing', '%canoeing'],
        'near_variant': True},
    ('Faculty', 'Rank'): {
        'targets': ['Professor', 'professor', 'Proor', 'proor', 'ofessor', 'OFESSOR', 'ssor', 'SSOR'],
        'enum': ['Instructor', 'Professor', 'AssocProf', 'AsstProf'],
        'near_variant': True},
    ('Faculty', 'Sex'): {'targets': ['F', 'f'], 'like_patterns': ['%F', '%f'],
                         'enum': ['M', 'F'], 'near_variant': True},
    ('Faculty', 'Building'): {'targets': ['NEB', 'Barton', 'Krieger'], 'dup_share': (0.2, 0.5)},
    ('Faculty', 'FacID'): {'group_sizes': [1, 2, 3]},
    ('Faculty', 'Fname'): {'dup_share': (0.2, 0.5)},
    ('Faculty', 'Lname'): {'dup_share': (0.2, 0.5)},
    ('Faculty', 'Phone'): {'dup_share': (0.2, 0.5), 'positive': True},
    ('Faculty', 'Room'): {'dup_share': (0.2, 0.5)},
    ('Faculty_Participates_in', 'FacID'): {'null_share': (0.05, 0.30)},
    ('Faculty_Participates_in', 'actid'): {'null_share': (0.05, 0.30),
                                           'targets': ['Canoeing', 'canoeing']},
    ('Participates_in', 'stuid'): {'null_share': (0.0, 0.05)},
    ('Participates_in', 'actid'): {'null_share': (0.0, 0.05)},
    ('Student', 'StuID'): {},
    ('Student', 'Age'): {'boundary': [19, 20, 21], 'range': (16, 30)},
    ('Student', 'Advisor'): {'null_share': (0.0, 0.05)},
    ('Student', 'Fname'): {'dup_share': (0.2, 0.5)},
    ('Student', 'LName'): {'dup_share': (0.2, 0.5)},
}

_BUILTIN_FORMULAS = {
    ('Activity', 'actid'): ('gt', 0),
    ('Faculty', 'FacID'): ('gt', 0),
    ('Faculty', 'Rank'): ('in', ['Instructor', 'Professor', 'AssocProf', 'AsstProf']),
    ('Faculty', 'Sex'): ('in', ['M', 'F']),
    ('Faculty', 'Phone'): ('gt', 0),
    ('Student', 'StuID'): ('gt', 0),
    ('Student', 'Age'): ('between', (16, 30)),
    ('Student', 'Sex'): ('in', ['M', 'F']),
    ('Student', 'Major'): ('gt', 0),
    ('Student', 'city_code'): ('len', 3),
}

_BUILTIN_SIZES = {'Activity': 8, 'Faculty': 16, 'Student': 16,
                  'Participates_in': 16, 'Faculty_Participates_in': 16}

_BUILTIN_NULL_TARGETS = [
    ('Faculty_Participates_in', 'FacID'),
    ('Faculty_Participates_in', 'actid'),
    ('Participates_in', 'stuid'),
    ('Participates_in', 'actid'),
    ('Student', 'Advisor'),
]


def load_specification(path: str) -> dict:
    """Read specification.json and normalise it into the dict the samplers expect."""
    with open(path) as f:
        raw = json.load(f)
    return normalise_spec(raw)


def _split_targets(tg: list) -> tuple:
    """Split specification targets into literal values and LIKE-pattern operands."""
    lits, likes = [], []
    for t in tg:
        s = str(t)
        if s.startswith('LIKE:'):
            likes.append(s[5:])
        elif s.startswith('%'):
            likes.append(s)
        elif re.search(r'\d+-\d+%', s) or 'duplicate share' in s.lower() or 'group size' in s.lower() \
                or 'PK exempt' in s or 'NULL rows' in s or 'unmatched join' in s:
            continue
        else:
            lits.append(s)
    return lits, likes


def normalise_spec(raw: dict) -> dict:
    """Turn the pipeline specification into {exceptions, formulas, sizes, null_targets}."""
    exc: dict = {}
    for e in raw.get('per_column_exceptions', []) or []:
        t, c = e.get('table'), e.get('column')
        if not t or not c:
            continue
        d = dict(_BUILTIN_EXCEPTIONS.get((t, c), {}))
        tg = e.get('targets') or []
        if tg:
            lits, likes = _split_targets(tg)
            if lits:
                d['targets'] = lits
            if likes:
                d['like_patterns'] = likes
        exc[(t, c)] = d
    for k, v in _BUILTIN_EXCEPTIONS.items():
        exc.setdefault(k, dict(v))
    formulas: dict = {}
    for r in raw.get('semantic_rules_and_formulas', []) or []:
        t, c, f = r.get('table'), r.get('column'), (r.get('formula') or '').strip()
        if not t or not c or not f:
            continue
        parsed = _parse_formula(f)
        if parsed is not None:
            formulas[(t, c)] = parsed
    for k, v in _BUILTIN_FORMULAS.items():
        formulas.setdefault(k, v)
    sizes = dict(_BUILTIN_SIZES)
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            sizes[t] = int(n)
        except (TypeError, ValueError):
            pass
    null_targets = []
    for nt in raw.get('null_targets') or []:
        if isinstance(nt, str) and '.' in nt:
            t, c = nt.split('.', 1)
            null_targets.append((t.strip(), c.strip()))
        elif isinstance(nt, (list, tuple)) and len(nt) == 2:
            null_targets.append((nt[0], nt[1]))
    if not null_targets:
        null_targets = list(_BUILTIN_NULL_TARGETS)
    return {'exceptions': exc, 'formulas': formulas, 'sizes': sizes, 'null_targets': null_targets}


def _parse_formula(f: str):
    """Parse the small formula language used by the specification."""
    s = f.strip()
    m = re.fullmatch(r'(\w+)\s*>\s*(-?\d+)', s)
    if m:
        return ('gt', int(m.group(2)))
    m = re.fullmatch(r'(\w+)\s*>=\s*(-?\d+)', s)
    if m:
        return ('ge', int(m.group(2)))
    m = re.fullmatch(r'(\w+)\s+BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', s, re.I)
    if m:
        return ('between', (int(m.group(2)), int(m.group(3))))
    m = re.fullmatch(r'(\w+)\s+IN\s*\((.*)\)', s, re.I)
    if m:
        vals = [x.strip().strip("'\"") for x in m.group(2).split(',') if x.strip()]
        return ('in', vals)
    m = re.fullmatch(r'length\((\w+)\)\s*=\s*(\d+)', s, re.I)
    if m:
        return ('len', int(m.group(2)))
    return None


def spec_from_compact(schema) -> dict:
    """Derive a specification from the compact database when specification.json is missing."""
    exc: dict = {}
    for k, v in _BUILTIN_EXCEPTIONS.items():
        exc[k] = dict(v)
    formulas: dict = {}
    for k, v in _BUILTIN_FORMULAS.items():
        formulas[k] = v
    sizes = {}
    for t, n in schema.original_sizes.items():
        sizes[t] = max(1, min(int(n), 230))
    for t, n in _BUILTIN_SIZES.items():
        sizes.setdefault(t, n)
    null_targets = list(_BUILTIN_NULL_TARGETS)
    return {'exceptions': exc, 'formulas': formulas, 'sizes': sizes, 'null_targets': null_targets}


def exception_for(spec: dict, table: str, column: str) -> dict:
    """Per-column exception dict (empty when none)."""
    return (spec.get('exceptions') or {}).get((table, column), {})


def formula_for(spec: dict, table: str, column: str):
    """Semantic formula tuple or None."""
    return (spec.get('formulas') or {}).get((table, column))


def is_null_target(spec: dict, table: str, column: str) -> bool:
    """True iff (table, column) is listed in the specification's null_targets."""
    for t, c in (spec.get('null_targets') or []):
        if t == table and c == column:
            return True
    return False


def table_size(spec: dict, table: str, rng) -> int:
    """Per-instance table size: base size from the spec, jittered by +-25%."""
    base = int((spec.get('sizes') or {}).get(table, 8))
    lo = max(0, int(base * 0.75))
    hi = max(lo, int(base * 1.25))
    return rng.randint(lo, hi)
