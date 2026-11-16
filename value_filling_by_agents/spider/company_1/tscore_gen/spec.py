"""Specification loading and the built-in default specification."""

DEFAULT_SPEC = {
    'table_sizes': {'department': 3, 'employee': 8, 'project': 6, 'works_on': 16,
                    'dependent': 7, 'dept_locations': 5},
    'size_variation': True,
    'null_share': {'employee.Super_ssn': 0.125, 'works_on.Hours': 0.062},
    'duplicate_share': {'dependent.Dependent_name': 0.30},
    'enum_pools': {'employee.Sex': ['M', 'F'],
                   'dependent.Sex': ['M', 'F'],
                   'dependent.Relationship': ['Daughter', 'Son', 'Spouse']},
    'literal_pools': {'dept_locations.Dlocation': ['Houston', 'houston', 'Houston ']},
    'comparison_boundaries': {'employee.Salary': [49999, 50000, 50001, 50002]},
    'numeric_ranges': {'employee.Salary': [25000, 55000], 'works_on.Hours': [5.0, 40.0]},
    'date_ranges': {'employee.Bdate': ['1900-01-01', '1999-12-31'],
                    'dependent.Bdate': ['1900-01-01', '1999-12-31'],
                    'department.Mgr_start_date': ['1900-01-01', '1999-12-31']},
    'planted_orphans': {'dependent.Essn': 1, 'works_on.Essn': 1},
    'parent_rows_without_children': ['employee.Ssn'],
    'semantic_rules': [{'table': 'employee', 'column': 'Salary', 'op': '>=', 'value': 0},
                       {'table': 'works_on', 'column': 'Hours', 'op': '>', 'value': 0},
                       {'table': 'employee', 'column': 'Bdate', 'op': '>=', 'value': '1900-01-01'},
                       {'table': 'dependent', 'column': 'Bdate', 'op': '>=', 'value': '1900-01-01'},
                       {'table': 'department', 'column': 'Mgr_start_date', 'op': '>=', 'value': '1900-01-01'},
                       {'table': 'employee', 'column': 'Sex', 'op': 'in', 'value': ['M', 'F']},
                       {'table': 'dependent', 'column': 'Sex', 'op': 'in', 'value': ['M', 'F']},
                       {'table': 'dependent', 'column': 'Relationship', 'op': 'in',
                        'value': ['Daughter', 'Son', 'Spouse']}],
}


def load_specification(path: str) -> dict:
    """Read specification.json and merge it over the built-in defaults."""
    import json
    with open(path) as f:
        raw = json.load(f)
    spec = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
            for k, v in DEFAULT_SPEC.items()}
    if not isinstance(raw, dict):
        return spec
    for k in ('table_sizes', 'null_share', 'duplicate_share', 'enum_pools', 'literal_pools',
              'comparison_boundaries', 'numeric_ranges', 'date_ranges', 'planted_orphans'):
        if isinstance(raw.get(k), dict):
            spec[k] = dict(raw[k])
    if isinstance(raw.get('parent_rows_without_children'), list):
        spec['parent_rows_without_children'] = list(raw['parent_rows_without_children'])
    if isinstance(raw.get('semantic_rules'), list):
        spec['semantic_rules'] = list(raw['semantic_rules'])
    if isinstance(raw.get('table_sizes_per_instance'), dict):
        spec['table_sizes'] = dict(raw['table_sizes_per_instance'])
    if isinstance(raw.get('null_targets'), list):
        for key in raw['null_targets']:
            spec['null_share'].setdefault(key, 0.1)
    for exc in raw.get('per_column_exceptions') or []:
        pat = exc.get('pattern')
        tg = exc.get('targets') or {}
        if pat == 'duplicates_for_distinct':
            for key in tg:
                if key == 'dependent.Dependent_name':
                    spec['duplicate_share'].setdefault(key, 0.30)
        elif pat == 'comparison_boundary':
            for key in tg:
                spec['comparison_boundaries'].setdefault(key, [49999, 50000, 50001, 50002])
        elif pat == 'enum':
            for key, expr in tg.items():
                vals = [x.strip().strip("'") for x in str(expr).replace('IN', '').replace('(', '')
                        .replace(')', '').split(',') if x.strip()]
                if vals:
                    spec['enum_pools'][key] = vals
        elif pat == 'literal_pool':
            for key, txt in tg.items():
                spec['literal_pools'].setdefault(key, [])
                for tok in str(txt).replace("'", ' ').split():
                    if tok and tok not in spec['literal_pools'][key]:
                        spec['literal_pools'][key].append(tok)
        elif pat == 'unmatched_join_rows':
            for key in tg:
                spec['planted_orphans'].setdefault(key, 1)
    return spec


def default_specification() -> dict:
    """Deep-ish copy of the built-in specification."""
    return {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
            for k, v in DEFAULT_SPEC.items()}
