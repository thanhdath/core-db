"""Specification as data: table sizes, per-column patterns, semantic rules, NULL targets."""
import json
import os

_DEFAULT = {
    'table_sizes': {'Student': 34, 'Dorm': 7, 'Dorm_amenity': 12, 'Has_amenity': 40, 'Lives_in': 31},
    'table_size_variation': {'keep_prob': 0.5, 'jitter': 3, 'random_max': 230},
    'semantic_rules': [
        {'table': 'Student', 'column': 'Age', 'kind': 'between', 'lo': 16, 'hi': 26},
        {'table': 'Student', 'column': 'Sex', 'kind': 'in', 'values': ['F', 'M']},
        {'table': 'Dorm', 'column': 'gender', 'kind': 'in', 'values': ['X', 'M', 'F']},
        {'table': 'Dorm', 'column': 'student_capacity', 'kind': 'gt', 'value': 0},
        {'table': 'Lives_in', 'column': 'room_number', 'kind': 'gt', 'value': 0},
    ],
    'null_targets': [
        'Student.LName', 'Student.Fname', 'Student.Age', 'Student.Sex', 'Student.Major',
        'Student.Advisor', 'Student.city_code', 'Dorm.dorm_name',
        'Dorm.student_capacity', 'Dorm.gender', 'Dorm_amenity.amenity_name',
        'Has_amenity.dormid', 'Has_amenity.amenid', 'Lives_in.stuid', 'Lives_in.dormid',
        'Lives_in.room_number',
    ],
    'per_column': {
        'Dorm.dormid': {'patterns': ['unmatched_join_rows', 'group_sizes', 'ties_for_order_limit'],
                        'group_sizes': '1,2,3+'},
        'Has_amenity.dormid': {'patterns': ['unmatched_join_rows', 'duplicates_for_distinct',
                                            'comparison_boundary', 'ties_for_order_limit'],
                               'duplicate_share': (0.2, 0.5)},
        'Dorm_amenity.amenity_name': {'patterns': ['comparison_boundary', 'duplicates_for_distinct'],
                                      'values': ['TV Lounge', 'tv lounge', 'Study Room', 'study room'],
                                      'duplicate_share': (0.2, 0.5)},
        'Has_amenity.amenid': {'patterns': ['unmatched_join_rows']},
        'Dorm_amenity.amenid': {'patterns': ['unmatched_join_rows']},
        'Dorm.student_capacity': {'patterns': ['rows_with_different_values']},
        'Student.StuID': {'patterns': ['unmatched_join_rows']},
        'Lives_in.dormid': {'patterns': ['unmatched_join_rows']},
        'Lives_in.stuid': {'patterns': ['unmatched_join_rows', 'duplicates_for_distinct'],
                           'duplicate_share': (0.2, 0.5)},
        'Student.Fname': {'patterns': ['duplicates_for_distinct'], 'duplicate_share': (0.2, 0.5)},
        'Student.LName': {'patterns': ['duplicates_for_distinct'], 'duplicate_share': (0.2, 0.5)},
        'Student.Major': {'patterns': ['group_sizes', 'rows_with_different_values', 'ties_for_order_limit'],
                          'group_sizes': '1,2,3+'},
        'Dorm.dorm_name': {'patterns': ['group_sizes', 'like_near_variant'],
                           'group_sizes': '1,2,3+', 'like_variants': ['%onor%', '%Donor%']},
        'Student.Sex': {'patterns': ['comparison_boundary'], 'values': ['M', 'm']},
        'Student.Age': {'patterns': ['rows_with_different_values']},
        'Dorm.gender': {'patterns': ['comparison_boundary'], 'values': ['F', 'f']},
        'Student.city_code': {'patterns': ['duplicates_for_distinct'], 'duplicate_share': (0.2, 0.5)},
    },
    'dependencies': [
        {'child_column': 'Has_amenity.dormid', 'parent_table': 'Dorm', 'parent_column': 'dormid'},
        {'child_column': 'Has_amenity.amenid', 'parent_table': 'Dorm_amenity', 'parent_column': 'amenid'},
        {'child_column': 'Lives_in.stuid', 'parent_table': 'Student', 'parent_column': 'StuID'},
        {'child_column': 'Lives_in.dormid', 'parent_table': 'Dorm', 'parent_column': 'dormid'},
    ],
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_spec(schema=None) -> dict:
    """Load specification.json next to this module if present, else the embedded default."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'specification.json')
    spec = dict(_DEFAULT)
    if os.path.exists(path):
        try:
            with open(path) as f:
                spec = _merge(_DEFAULT, json.load(f))
        except Exception:
            pass
    pc = {}
    for k, v in spec.get('per_column', {}).items():
        if '.' in k:
            t, c = k.split('.', 1)
            pc[(t, c)] = v
    spec['per_column'] = pc
    nt = set()
    for k in spec.get('null_targets', []):
        if '.' in k:
            t, c = k.split('.', 1)
            nt.add((t, c))
    spec['null_targets'] = nt
    deps = {}
    for d in spec.get('dependencies', []):
        cc = d['child_column']
        if '.' in cc:
            ct, ccol = cc.split('.', 1)
            deps[(ct, ccol)] = (d['parent_table'], d['parent_column'])
    spec['dependencies'] = deps
    return spec
