"""Specification model: per-column sampling rules, domains, dependencies and semantic rules."""
import re

DEFAULT_SPEC = {
    'table_sizes': {'divisions': 21, 'matchs': 230},
    'columns': {
        'divisions.division': {'pattern': 'primary_key_text', 'distinct': 21, 'nullable': False},
        'divisions.name': {'pattern': 'text_name',
                           'values': ['Bundesliga', 'bundesliga', 'Premier League', 'premier league',
                                      'Liga NOS', 'liga nos', 'LaLiga', 'laliga'],
                           'group_sizes': [1, 2, 3]},
        'divisions.country': {'pattern': 'text_short',
                              'values': ['England', 'england', 'Greece', 'greece']},
        'matchs.Div': {'pattern': 'foreign_key', 'parent': ('divisions', 'division'),
                       'unmatched_prob': 0.15, 'null_share': 0.15},
        'matchs.Date': {'pattern': 'date_iso', 'format': '%Y-%m-%d',
                        'lo': '2020-08-01', 'hi': '2021-06-30',
                        'boundary': ['2020-08-08', '2021-06-30']},
        'matchs.HomeTeam': {'pattern': 'text_name',
                            'values': ['Bradford', 'bradford', 'Augsburg', 'augsburg',
                                       'Mainz', 'mainz', ' Mainz', ' mainz'],
                            'null_share': 0.15},
        'matchs.AwayTeam': {'pattern': 'text_name',
                            'values': ['Bradford', 'bradford', 'Bra', 'bra'],
                            'duplicate_share': 0.35},
        'matchs.FTHG': {'pattern': 'integer_small', 'lo': 0, 'hi': 8, 'boundary': [0, 1, 7, 8]},
        'matchs.FTAG': {'pattern': 'integer_small', 'lo': 0, 'hi': 7, 'boundary': [0, 1, 6, 7],
                        'values': [1, 2, 3, 4]},
        'matchs.FTR': {'pattern': 'enum_short', 'values': ['H', 'h', 'A', 'a', 'D', 'd'],
                       'null_share': 0.15},
        'matchs.season': {'pattern': 'integer_season', 'lo': 2014, 'hi': 2022,
                          'values': [2018, 2019, 2020, 2021, 2022]},
    },
    'dependencies': [{'child': ('matchs', 'Div'), 'parent': ('divisions', 'division')}],
    'rules': [
        {'table': 'divisions', 'column': 'division', 'kind': 'not_null'},
        {'table': 'matchs', 'column': 'FTHG', 'kind': 'between', 'lo': 0, 'hi': 8},
        {'table': 'matchs', 'column': 'FTAG', 'kind': 'between', 'lo': 0, 'hi': 7},
        {'table': 'matchs', 'column': 'FTR', 'kind': 'in', 'values': ['H', 'h', 'A', 'a', 'D', 'd']},
        {'table': 'matchs', 'column': 'season', 'kind': 'between', 'lo': 2014, 'hi': 2022},
        {'table': 'matchs', 'column': 'FTHG', 'kind': 'goal_pair',
         'other': 'FTAG', 'total_lo': 9, 'total_hi': 11},
    ],
    'null_targets': ['matchs.Div', 'matchs.FTR', 'matchs.HomeTeam', 'matchs.AwayTeam',
                     'matchs.FTHG', 'matchs.FTAG', 'matchs.season', 'matchs.Date'],
}

_PATTERN_ALIASES = {
    'text_short': 'text_short', 'text_name': 'text_name', 'integer_small': 'integer_small',
    'integer_season': 'integer_season', 'date_iso': 'date_iso', 'enum_short': 'enum_short',
    'foreign_key': 'foreign_key', 'primary_key_text': 'primary_key_text',
}


def _key(t, c):
    return '%s.%s' % (t, c)


def _split(k):
    t, c = k.split('.', 1)
    return t, c


def _norm_column(spec_col: dict) -> dict:
    out = dict(spec_col)
    out['pattern'] = _PATTERN_ALIASES.get(str(out.get('pattern', 'text_short')).lower(), 'text_short')
    if 'values' in out and out['values'] is not None:
        out['values'] = [str(v) for v in out['values']]
    if 'boundary' in out and out['boundary'] is not None:
        out['boundary'] = list(out['boundary'])
    return out


def load_specification(raw: dict, schema) -> dict:
    """Normalise a specification.json dict; missing columns fall back to type-derived rules."""
    spec = {'table_sizes': {}, 'columns': {}, 'dependencies': [], 'rules': [], 'null_targets': []}
    if isinstance(raw, dict):
        ts = raw.get('table_sizes_per_instance') or raw.get('table_sizes') or {}
        spec['table_sizes'] = {str(k): int(v) for k, v in ts.items()}
        cols = raw.get('columns') or {}
        for k, v in cols.items():
            spec['columns'][k] = _norm_column(v)
        for ex in raw.get('per_column_exceptions') or []:
            k = ex.get('column')
            if not k:
                continue
            cur = spec['columns'].setdefault(k, {})
            cur.update(_norm_column(ex))
            tgt = ex.get('targets') or {}
            if 'values' in tgt:
                cur['values'] = [str(x) for x in tgt['values']]
            if 'range' in tgt:
                cur['lo'], cur['hi'] = tgt['range'][0], tgt['range'][1]
            if 'boundary' in tgt:
                cur['boundary'] = list(tgt['boundary'])
            if 'null_share' in tgt and 'none' not in str(tgt['null_share']):
                cur['null_share'] = 0.15
            if 'duplicate_share' in tgt:
                cur['duplicate_share'] = 0.35
        for d in raw.get('dependencies') or []:
            child = d.get('child_column')
            pt = d.get('parent_table')
            pc = d.get('parent_column')
            if child and pt and pc:
                spec['dependencies'].append({'child': _split(child), 'parent': (pt, pc)})
        for r in raw.get('semantic_rules_and_formulas') or []:
            spec['rules'].append(_norm_rule(r))
        spec['null_targets'] = list(raw.get('null_targets') or [])
    derived = spec_from_columns(schema)
    for k, v in derived['columns'].items():
        spec['columns'].setdefault(k, v)
    for t, n in derived['table_sizes'].items():
        spec['table_sizes'].setdefault(t, n)
    if not spec['dependencies']:
        spec['dependencies'] = derived['dependencies']
    if not spec['rules']:
        spec['rules'] = derived['rules']
    if not spec['null_targets']:
        spec['null_targets'] = derived['null_targets']
    return spec


def _norm_rule(r: dict) -> dict:
    """Map a semantic rule/formula entry to a compiled-rule dict."""
    t, c = r.get('table'), r.get('column')
    f = str(r.get('formula', ''))
    out = {'table': t, 'column': c, 'kind': 'raw', 'formula': f}
    if re.search(r'IS\s+NOT\s+NULL', f, re.I):
        out['kind'] = 'not_null'
    elif re.search(r'BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', f, re.I):
        m = re.search(r'BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', f, re.I)
        out.update(kind='between', lo=int(m.group(1)), hi=int(m.group(2)))
    elif re.search(r'\bIN\s*\(', f, re.I):
        vals = re.findall(r"'([^']*)'", f)
        if vals:
            out.update(kind='in', values=vals)
    elif 'FTAG' in f and 'FTHG' in f:
        out.update(kind='goal_pair', other='FTAG', total_lo=9, total_hi=11)
    return out


def spec_from_columns(schema) -> dict:
    """Derive a specification from the compact database's column types and observed values."""
    spec = {'table_sizes': {}, 'columns': {}, 'dependencies': [], 'rules': [], 'null_targets': []}
    for t, tm in schema.tables.items():
        n = schema.original_sizes.get(t, 0)
        spec['table_sizes'][t] = max(1, min(230, n if n else 20))
    for (ct, cc), (pt, pc) in schema.fks.items():
        spec['dependencies'].append({'child': (ct, cc), 'parent': (pt, pc)})
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            k = _key(t, cm.name)
            ty = (cm.type_str or '').lower()
            ov = [v for v in schema.original_values.get((t, cm.name), []) if v is not None]
            if cm.pk_pos > 0:
                spec['columns'][k] = {'pattern': 'primary_key_text', 'distinct': max(1, len(set(ov))),
                                      'nullable': False}
            elif (t, cm.name) in schema.fks:
                pt, pc = schema.fks[(t, cm.name)]
                spec['columns'][k] = {'pattern': 'foreign_key', 'parent': (pt, pc),
                                      'unmatched_prob': 0.15, 'null_share': 0.15}
            elif 'date' in ty or 'time' in ty:
                spec['columns'][k] = {'pattern': 'date_iso', 'format': '%Y-%m-%d',
                                      'lo': '2020-08-01', 'hi': '2021-06-30', 'boundary': []}
            elif 'int' in ty or 'real' in ty or 'num' in ty:
                nums = [int(v) for v in ov if isinstance(v, (int, float))]
                lo = min(nums) if nums else 0
                hi = max(nums) if nums else 10
                spec['columns'][k] = {'pattern': 'integer_small', 'lo': lo, 'hi': hi,
                                      'boundary': [lo, lo + 1, hi - 1, hi]}
            else:
                vals = sorted({str(v) for v in ov})[:30]
                spec['columns'][k] = {'pattern': 'text_short', 'values': vals}
            if not cm.notnull and cm.pk_pos == 0:
                spec['null_targets'].append(k)
    return spec
