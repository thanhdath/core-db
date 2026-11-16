"""Specification loading: per-column exceptions, semantic rules, table sizes."""
import json

DEFAULT_SPEC = {
    'table_sizes': {'buildings': 12, 'Companies': 19, 'Office_locations': 16},
    'null_targets': [],
    'enums': {
        'buildings.Status': ['under construction', 'proposed', 'on-hold'],
        'Companies.Industry': ['Banking', 'Conglomerate', 'Oil and gas',
                               'Telecommunications', 'Retailing'],
    },
    'ranges': {
        'buildings.id': (1, None),
        'buildings.Height': (1, None),
        'buildings.Stories': (1, None),
        'Companies.id': (1, None),
        'Companies.Sales_billion': (0.0, None),
        'Companies.Profits_billion': (0.0, None),
        'Companies.Assets_billion': (0.0, None),
        'Companies.Market_Value_billion': (0.0, None),
        'Office_locations.move_in_year': (1900, 2100),
    },
    'boundaries': {
        'buildings.Height': [-1, 0, 1],
        'Companies.Headquarters': ['China', 'china'],
        'buildings.Status': ['on-hold', 'ON-HOLD'],
        'Companies.Industry': ['Banking', 'banking'],
    },
    'group_sizes': ['Office_locations.building_id', 'Companies.Industry', 'buildings.id',
                    'buildings.name'],
    'distinct_dups': ['Companies.Industry', 'buildings.name', 'Companies.name'],
    'order_ties': {'Companies.Industry': {'rank': 1, 'direction': 'ASC'},
                   'Companies.Market_Value_billion': {'rank': 100, 'direction': 'DESC'}},
    'parent_without_children': ['buildings.id', 'Companies.id'],
    'child_null_fk': [],
    'aggregate_boundary': ['Office_locations.building_id', 'buildings.id',
                           'Office_locations.company_id'],
    'comparison_boundary': [('Office_locations.building_id', 'buildings.id'),
                            ('buildings.id', 'Office_locations.building_id')],
    'rows_with_different_values': ['buildings.Height', 'Companies.Sales_billion'],
}


def _filter_null_targets(spec: dict, schema) -> None:
    """Keep only genuinely nullable columns as NULL targets (schema is the authority)."""
    keep = []
    for key in spec.get('null_targets') or []:
        if '.' not in key:
            continue
        t, c = key.split('.', 1)
        tm = schema.tables.get(t)
        if tm is None:
            continue
        cm = next((x for x in tm.columns if x.name == c), None)
        if cm is None:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        keep.append(key)
    spec['null_targets'] = keep


def load_specification(path: str, schema=None) -> dict:
    """Read specification.json and merge it over DEFAULT_SPEC (shallow, per key)."""
    with open(path) as f:
        raw = json.load(f)
    spec = dict(DEFAULT_SPEC)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in ('generic_sampling_rules', 'supporting_evidence', 'uncertainty',
                     'dependencies', 'semantic_rules_and_formulas', 'per_column_exceptions'):
                continue
            spec[k] = v
        for exc in raw.get('per_column_exceptions', []) or []:
            col = exc.get('column')
            tgt = exc.get('targets') or {}
            if not col:
                continue
            if 'values' in tgt:
                spec.setdefault('boundaries', {})[col] = list(tgt['values'])
            if 'group_sizes' in tgt:
                if col not in spec.setdefault('group_sizes', []):
                    spec['group_sizes'].append(col)
            if 'duplicate_share' in tgt:
                if col not in spec.setdefault('distinct_dups', []):
                    spec['distinct_dups'].append(col)
            if 'tie_at_rank' in tgt:
                spec.setdefault('order_ties', {})[col] = {
                    'rank': (tgt.get('tie_at_rank') or [1])[0],
                    'direction': tgt.get('direction', 'ASC')}
            if tgt.get('parent_rows_without_children'):
                if col not in spec.setdefault('parent_without_children', []):
                    spec['parent_without_children'].append(col)
            if tgt.get('child_rows_with_null_fk'):
                if col not in spec.setdefault('child_null_fk', []):
                    spec['child_null_fk'].append(col)
            if 'aggregate' in tgt:
                if col not in spec.setdefault('aggregate_boundary', []):
                    spec['aggregate_boundary'].append(col)
        for rule in raw.get('semantic_rules_and_formulas', []) or []:
            t, c = rule.get('table'), rule.get('column')
            f = (rule.get('formula') or '').strip()
            if not t or not c:
                continue
            key = '%s.%s' % (t, c)
            if ' IN (' in f.upper():
                inner = f[f.index('(') + 1:f.rindex(')')]
                vals = [x.strip().strip("'\"") for x in inner.split(',') if x.strip()]
                spec.setdefault('enums', {})[key] = vals
            elif 'BETWEEN' in f.upper():
                lo, hi = f.upper().split('BETWEEN')[1].split('AND')
                spec.setdefault('ranges', {})[key] = (float(lo), float(hi))
            elif '>=' in f:
                spec.setdefault('ranges', {})[key] = (float(f.split('>=')[1]), None)
            elif '>' in f:
                spec.setdefault('ranges', {})[key] = (float(f.split('>')[1]) + 1, None)
        if 'table_sizes_per_instance' in raw:
            spec['table_sizes'] = raw['table_sizes_per_instance']
        if 'null_targets' in raw:
            spec['null_targets'] = raw['null_targets']
    if schema is not None:
        _filter_null_targets(spec, schema)
    return spec
