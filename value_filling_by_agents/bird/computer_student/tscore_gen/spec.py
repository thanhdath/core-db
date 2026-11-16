"""Specification loading: value domains, per-column exceptions, table sizes, NULL targets."""
import json

_DEFAULT = {
    'table_sizes': {'course': 40, 'person': 80, 'taughtBy': 60, 'advisedBy': 30},
    'domains': {
        'course.courseLevel': ['Level_300', 'Level_400', 'Level_500'],
        'person.professor': [0, 1],
        'person.student': [0, 1],
        'person.hasPosition': ['0', 'Faculty', 'Faculty_adj', 'Faculty_eme', 'Faculty_aff'],
        'person.inPhase': ['0', 'Post_Quals', 'Post_Generals', 'Pre_Quals'],
        'person.yearsInProgram': ['0', 'Year_1', 'Year_2', 'Year_3', 'Year_4', 'Year_5',
                                  'Year_6', 'Year_7', 'Year_8', 'Year_9', 'Year_10', 'Year_11'],
    },
    'boundary_values': {
        'course.course_id': [17, 18, 19, 129, 130, 131],
        'person.p_id': [39, 40, 41, 49, 50, 51],
        'taughtBy.p_id': [39, 40, 41, 49, 50, 51],
        'taughtBy.course_id': [10, 11, 12, 17, 18, 19],
        'person.professor': [0, 1, 2],
        'person.student': [-1, 0, 1, 2],
        'course.courseLevel': ['Level_300', 'level_300', 'Level_400', 'level_400',
                               'Level_500', 'level_500', 'Level_0', 'level_0'],
        'person.hasPosition': ['Faculty_eme', 'faculty_eme', 'FACULTY_EME'],
        'person.yearsInProgram': ['Year_1', 'year_1', 'Year_2', 'year_2'],
    },
    'boundary_probe_only': {
        'person.professor': [2],
        'person.student': [-1, 2],
    },
    'null_targets': ['course.courseLevel', 'person.professor', 'person.student',
                     'person.hasPosition', 'person.inPhase', 'person.yearsInProgram'],
    'null_share': 0.05,
    'duplicate_share': 0.35,
    'group_sizes': [1, 2, 3],
    'tie_ranks': {'taughtBy.p_id': [1, 3, 5], 'taughtBy.course_id': [1]},
    'aggregate_boundaries': {
        'taughtBy.p_id': {'thresholds': [2, 3, 4, 5], 'distinct_threshold': None},
        'taughtBy.course_id': {'thresholds': [2, 3, 4, 5], 'distinct_threshold': 3},
    },
    'duplicates_for_distinct': ['course.courseLevel', 'person.p_id', 'taughtBy.p_id',
                                'advisedBy.p_id', 'advisedBy.p_id_dummy'],
    'group_sizes_targets': ['course.course_id', 'person.p_id', 'taughtBy.p_id', 'taughtBy.course_id',
                            'course.courseLevel', 'person.hasPosition'],
    'fk_boundary_targets': {'taughtBy.p_id': 'person.p_id', 'taughtBy.course_id': 'course.course_id'},
    'advisedby_no_self': True,
}


def default_specification() -> dict:
    """Return a deep-ish copy of the built-in default."""
    return json.loads(json.dumps(_DEFAULT))


def load_specification(path: str) -> dict:
    """Load specification.json and merge it over the default (missing keys keep defaults)."""
    with open(path) as f:
        raw = json.load(f)
    spec = default_specification()
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v
    return spec


def key(table: str, column: str) -> str:
    """Canonical 'table.column' key."""
    return '%s.%s' % (table, column)
