"""Specification loading and per-column domain construction."""
import re

DEFAULT_NULL_SHARE = 0.0
DEFAULT_DUP_SHARE = 0.35
FRESH_SHARE = 0.6

BOUNDARY_TARGETS = {
    ('teachers', 'Classroom'): [106, 107, 108, 109, 110, 111],
    ('list', 'Classroom'): [106, 107, 108, 109, 110, 111],
    ('list', 'Grade'): [-1, 0, 1, 3, 4, 5, 6],
    ('teachers', 'FirstName'): ['TARRING', 'tarring', 'KAWA', 'kawa', 'LEIA', 'leia',
                                'GORDON', 'gordon', 'LORIA', 'loria', 'COVIN', 'covin'],
    ('teachers', 'LastName'): ['GORDON', 'gordon', 'TARRING', 'tarring', 'LEIA', 'leia',
                               'KAWA', 'kawa', 'ONDERSMA', 'ondersma', 'COVIN', 'covin'],
    ('list', 'FirstName'): ['MADLOCK', 'madlock', 'CHRISSY', 'chrissy', 'RAY', 'ray',
                            'ISS', 'iss', 'SS', 'ss', 'CHRYSSY', 'chryssy'],
    ('list', 'LastName'): ['MADLOCK', 'madlock', 'RAY', 'ray', 'ABOZN', 'abozn',
                           'NABOZNY', 'nabozny'],
}

INT_RANGES = {
    ('list', 'Grade'): (-1, 6),
    ('list', 'Classroom'): (101, 112),
    ('teachers', 'Classroom'): (101, 112),
}

FORCE_ONE_NULL = {('list', 'Grade')}

DUP_COLUMNS = {('teachers', 'FirstName'), ('teachers', 'LastName'),
               ('list', 'FirstName'), ('list', 'LastName')}

GROUP_COLUMNS = {('teachers', 'Classroom'), ('list', 'Classroom'),
                 ('teachers', 'FirstName'), ('teachers', 'LastName')}

SOFT_JOINS = {('list', 'Classroom'): ('teachers', 'Classroom')}

NULL_SHARE_OVERRIDES = {
    ('list', 'Grade'): 0.20,
}
NULL_FLOOR = 0.05


def _norm_key(t: str, c: str) -> tuple:
    return (str(t).lower(), str(c).lower())


def _lookup(d: dict, t: str, c: str, default=None):
    for (tt, cc), v in d.items():
        if tt.lower() == str(t).lower() and cc.lower() == str(c).lower():
            return v
    return default


def load_specification(raw: dict) -> dict:
    """Normalise a specification dict into the internal form used by the samplers."""
    spec = {'boundary': {}, 'int_ranges': {}, 'null_share': {}, 'force_null': set(),
            'dup_share': {}, 'group_cols': set(), 'soft_joins': {}, 'fresh_share': FRESH_SHARE,
            'null_floor': NULL_FLOOR}
    for (t, c), vals in BOUNDARY_TARGETS.items():
        spec['boundary'][(t, c)] = list(vals)
    for (t, c), rng in INT_RANGES.items():
        spec['int_ranges'][(t, c)] = rng
    spec['force_null'] = set(FORCE_ONE_NULL)
    spec['group_cols'] = set(GROUP_COLUMNS)
    spec['soft_joins'] = dict(SOFT_JOINS)
    for (t, c) in DUP_COLUMNS:
        spec['dup_share'][(t, c)] = DEFAULT_DUP_SHARE
    for (t, c), v in NULL_SHARE_OVERRIDES.items():
        spec['null_share'][(t, c)] = v
    if not isinstance(raw, dict):
        return spec
    for exc in raw.get('per_column_exceptions', []) or []:
        pat = exc.get('pattern')
        tg = exc.get('targets', {}) or {}
        for key, val in tg.items():
            if '.' not in key:
                continue
            t, c = key.split('.', 1)
            k = (t, c)
            if pat == 'comparison_boundary' and isinstance(val, list):
                spec['boundary'][k] = list(val)
            elif pat == 'duplicates_for_distinct':
                m = re.search(r'(\d+)\s*-\s*(\d+)', str(val))
                if m:
                    spec['dup_share'][k] = (int(m.group(1)) + int(m.group(2))) / 200.0
                else:
                    spec['dup_share'][k] = DEFAULT_DUP_SHARE
            elif pat == 'group_sizes':
                spec['group_cols'].add(k)
            elif pat == 'null_rows':
                m = re.search(r'(\d+)\s*-\s*(\d+)', str(val))
                if m:
                    spec['null_share'][k] = (int(m.group(1)) + int(m.group(2))) / 200.0
                    spec['force_null'].add(k)
    for dep in raw.get('dependencies', []) or []:
        cc_full = dep.get('child_column', '')
        if '.' in cc_full:
            ct, cc = cc_full.split('.', 1)
            spec['soft_joins'][(ct, cc)] = (dep.get('parent_table'), dep.get('parent_column'))
    return spec


def spec_from_columns(schema) -> dict:
    """Fallback specification derived from the schema when no JSON is available."""
    spec = {'boundary': dict(BOUNDARY_TARGETS), 'int_ranges': dict(INT_RANGES),
            'null_share': dict(NULL_SHARE_OVERRIDES), 'force_null': set(FORCE_ONE_NULL),
            'dup_share': {}, 'group_cols': set(GROUP_COLUMNS), 'soft_joins': dict(SOFT_JOINS),
            'fresh_share': FRESH_SHARE, 'null_floor': NULL_FLOOR}
    for (t, c) in DUP_COLUMNS:
        spec['dup_share'][(t, c)] = DEFAULT_DUP_SHARE
    for (t, c), (pt, pc) in schema.fks.items():
        spec['soft_joins'].setdefault((t, c), (pt, pc))
    return spec


def column_domain(schema, spec: dict, table: str, column: str) -> dict:
    """Return the domain description for one column: kind, range, pool, null share, dup share."""
    cm = next((c for c in schema.tables[table].columns if c.name == column), None)
    t = (cm.type_str or '').lower() if cm else ''
    is_int = any(x in t for x in ('int', 'number', 'real', 'float', 'double', 'decimal', 'numeric'))
    rng = _lookup(spec.get('int_ranges', {}), table, column)
    pool = list(_lookup(spec.get('boundary', {}), table, column, []) or [])
    null_share = _lookup(spec.get('null_share', {}), table, column, None)
    dup_share = _lookup(spec.get('dup_share', {}), table, column, None)
    force_null = any(tt.lower() == table.lower() and cc.lower() == column.lower()
                     for (tt, cc) in spec.get('force_null', set()))
    is_pk = bool(cm and cm.pk_pos > 0)
    return {'kind': 'int' if is_int else 'text', 'range': rng, 'pool': pool,
            'null_share': null_share, 'dup_share': dup_share, 'force_null': force_null,
            'null_floor': spec.get('null_floor', NULL_FLOOR),
            'notnull': bool(cm.notnull) if cm else False,
            'pk': is_pk}
