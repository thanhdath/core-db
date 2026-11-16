"""Specification loading: value pools, boundaries, LIKE variants, sizes, NULL targets, semantic rules, group-size /
duplicate-share / tie / boundary construction targets."""
import json
import os

SPEC_PATH = os.path.join(os.path.dirname(__file__), 'specification.json')

_BUILTIN = {
    'table_sizes': {'cinema': 10, 'film': 5, 'schedule': 7},
    'null_targets': ['cinema.Name', 'cinema.Openning_year', 'cinema.Capacity', 'cinema.Location',
                     'film.Rank_in_series', 'film.Number_in_season', 'film.Title', 'film.Directed_by',
                     'film.Original_air_date', 'film.Production_code', 'schedule.Date',
                     'schedule.Show_times_per_day', 'schedule.Price'],
    'boundary_literals': {
        'cinema.Capacity': [299, 300, 301, 302, 706, 707, 708, 799, 800, 801],
        'film.Film_ID': [1, 2, 3, 4, 5],
        'schedule.Film_ID': [4, 5],
        'cinema.Openning_year': [2011],
    },
    'like_literals': {'film.Title': ['%Dummy%', '%Dumm%', '% Dummy%']},
    'like_variants': {'film.Title': ['Dummy', 'Dummz', 'Dummy x', 'dummy', 'Dumm', 'Dumn', 'Dumm x', 'dumm']},
    'enum_columns': {
        'cinema.Location': ['County Wicklow', 'County Cork', 'County Dublin', 'County Clare',
                            'County Tipperary', 'County Laois', 'County Louth'],
        'film.Directed_by': ['Bill Schreiner', 'Jesus Salvador Trevi\u00f1o'],
        'film.Title': ['The Case of the Mystery Weekend', 'The Case of the Smart Dummy',
                       'The Case: Off the Record', 'The Case of the Bermuda Triangle',
                       'The Case of the Piggy Banker'],
        'film.Original_air_date': ['September 21\u201325, 1992', 'September 28\u2013October 2, 1992',
                                   'October 5\u20139, 1992', 'October 12\u201316, 1992',
                                   'October 19\u201323, 1992'],
        'film.Production_code': ['50021\u201350025', '50231\u201350235', '50011\u201350015',
                                 '50251\u201350255', '50241\u201350245'],
        'schedule.Date': ['21 May', '21 Jun', '11 July', '2 Aug', '20 May', '19 May'],
    },
    'int_ranges': {
        'cinema.Capacity': (203, 1200),
        'cinema.Openning_year': (1900, 2100),
        'film.Rank_in_series': (26, 30),
        'film.Number_in_season': (1, 5),
        'schedule.Show_times_per_day': (2, 5),
    },
    'float_ranges': {'schedule.Price': (0.0, 16.0)},
    'rules': [
        {'table': 'cinema', 'column': 'Capacity', 'kind': 'gt', 'value': 0},
        {'table': 'cinema', 'column': 'Openning_year', 'kind': 'between', 'value': (1900, 2100)},
        {'table': 'film', 'column': 'Rank_in_series', 'kind': 'gt', 'value': 0},
        {'table': 'film', 'column': 'Number_in_season', 'kind': 'gt', 'value': 0},
        {'table': 'schedule', 'column': 'Show_times_per_day', 'kind': 'gt', 'value': 0},
        {'table': 'schedule', 'column': 'Price', 'kind': 'ge', 'value': 0},
    ],
    'duplicate_share': 0.35,
    'fresh_share': 0.2,
    'group_size_pattern': [1, 2, 3],
    'tie_target': {'direction': 'DESC', 'tie_at_rank': 1},
    'group_size_columns': [
        'cinema.Name', 'film.Title', 'film.Directed_by',
    ],
    'duplicate_columns': {
        'cinema.Location': 0.35, 'cinema.Name': 0.35,
    },
    'tie_columns': {
        'cinema.Capacity': {'direction': 'DESC'},
        'cinema.Location': {'direction': 'DESC'},
        'film.Directed_by': {'direction': 'ASC and DESC'},
    },
    'aggregate_tie_columns': {
        'film.Directed_by': {'tie_on': ['SUM(schedule.show_times_per_day)', 'COUNT(*)'],
                             'tie_at_rank': [1]},
    },
    'comparison_boundary_columns': {
        'cinema.Capacity': [299, 300, 301, 302, 706, 707, 708, 799, 800, 801],
        'film.Film_ID': [1, 2, 3, 4, 5],
        'schedule.Film_ID': [4, 5],
    },
    'post_fill_boundary_columns': {
        'film.Film_ID': [1, 2, 3, 4, 5],
        'schedule.Film_ID': [4, 5],
    },
    'like_columns': ['film.Title'],
    'aggregate_boundary_columns': {
        'cinema.Location': {'aggregate': 'COUNT(*)', 'values': [1, 2, 3]},
        'cinema.Name': {'aggregate': 'COUNT(DISTINCT cinema.name)', 'values': [1, 2, 3]},
    },
}


def _key(k: str):
    t, c = k.split('.', 1)
    return (t.lower(), c.lower())


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_spec(schema, pool: dict) -> dict:
    """Return the effective spec; additionally merge pool literals into boundary/enum pools."""
    spec = dict(_BUILTIN)
    try:
        with open(SPEC_PATH) as f:
            disk = json.load(f)
        if isinstance(disk, dict):
            spec = _merge(spec, disk)
    except (OSError, ValueError):
        pass
    spec['boundary'] = {_key(k): list(v) for k, v in spec.get('boundary_literals', {}).items()}
    spec['like'] = {_key(k): list(v) for k, v in spec.get('like_literals', {}).items()}
    spec['like_variants'] = {_key(k): list(v) for k, v in spec.get('like_variants', {}).items()}
    spec['enum'] = {_key(k): [str(x) for x in v] for k, v in spec.get('enum_columns', {}).items()}
    spec['int_range'] = {_key(k): tuple(v) for k, v in spec.get('int_ranges', {}).items()}
    spec['float_range'] = {_key(k): tuple(v) for k, v in spec.get('float_ranges', {}).items()}
    spec['null_set'] = {_key(k) for k in spec.get('null_targets', [])}
    spec['table_size'] = {k.lower(): int(v) for k, v in spec.get('table_sizes', {}).items()}
    rules = []
    for r in spec.get('rules', []):
        rr = dict(r)
        rr['key'] = (rr['table'].lower(), rr['column'].lower())
        rules.append(rr)
    spec['rules_list'] = rules
    spec['rule_by_key'] = {}
    for rr in rules:
        spec['rule_by_key'].setdefault(rr['key'], []).append(rr)
    spec['group_size_set'] = {_key(k) for k in spec.get('group_size_columns', [])}
    spec['duplicate_targets'] = {_key(k): float(v) for k, v in spec.get('duplicate_columns', {}).items()}
    spec['tie_targets'] = {_key(k): dict(v) for k, v in spec.get('tie_columns', {}).items()}
    spec['aggregate_tie_targets'] = {_key(k): dict(v) for k, v in spec.get('aggregate_tie_columns', {}).items()}
    spec['boundary_targets'] = {_key(k): list(v) for k, v in spec.get('comparison_boundary_columns', {}).items()}
    spec['post_fill_boundary_targets'] = {_key(k): list(v)
                                          for k, v in spec.get('post_fill_boundary_columns', {}).items()}
    spec['like_columns_set'] = {_key(k) for k in spec.get('like_columns', [])}
    spec['aggregate_boundary_targets'] = {_key(k): dict(v)
                                          for k, v in spec.get('aggregate_boundary_columns', {}).items()}
    for (t, c), vals in pool.items():
        spec['boundary'].setdefault((t.lower(), c.lower()), [])
        for v in vals:
            spec['boundary'][(t.lower(), c.lower())].append(v)
    return spec


def like_variant_set(spec: dict, key) -> list:
    """Near-variants for a LIKE literal: '%Dummy%' -> 'Dummy', 'Dummz', 'Dummy x', 'dummy', ..."""
    body_list = []
    for lit in spec['like'].get(key, []):
        body = lit.strip('%')
        if body:
            body_list.append(body)
    body_list += spec['like_variants'].get(key, [])
    out = []
    for body in body_list:
        if body and body != body.lower() and body.lower() in out:
            continue
        out.append(body)
        if body and body[0].lower() + body[1:] not in out:
            out.append(body[0].lower() + body[1:])
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def satisfies_rule(rule: dict, v) -> bool:
    """Evaluate one semantic rule in Python; a NULL operand is SQL-unknown -> holds."""
    if v is None:
        return True
    try:
        val = float(v)
    except (TypeError, ValueError):
        return True
    kind = rule.get('kind')
    ref = rule.get('value')
    if kind == 'gt':
        return val > float(ref)
    if kind == 'ge':
        return val >= float(ref)
    if kind == 'lt':
        return val < float(ref)
    if kind == 'le':
        return val <= float(ref)
    if kind == 'between':
        return float(ref[0]) <= val <= float(ref[1])
    if kind == 'in':
        return val in [float(x) for x in ref]
    return True
