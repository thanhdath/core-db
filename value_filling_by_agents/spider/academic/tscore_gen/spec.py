"""Specification tables implemented by construction (no rule is evaluated with SQL)."""
import re

_SIZES = {'organization': 20, 'author': 40, 'conference': 15, 'journal': 15, 'keyword': 30,
          'domain': 10, 'publication': 60, 'writes': 80, 'cite': 40, 'domain_author': 30,
          'domain_conference': 20, 'domain_journal': 20, 'domain_keyword': 25,
          'domain_publication': 30, 'publication_keyword': 50}

_RANGES = {('publication', 'year'): (1900, 2100),
           ('publication', 'citation_num'): (0, 1000),
           ('publication', 'reference_num'): (0, 1000)}

_ENUMS = {
    ('organization', 'continent'): ['North America', 'South America', 'Europe', 'Asia',
                                    'Africa', 'Oceania'],
}

_NEAR = {
    ('publication', 'title'): ['Making database systems usable', 'making database systems usable',
                               ' Making database systems usable ', ' making database systems usable ',
                               'Making database systble', 'making database systble', 'Musable', 'musable'],
    ('author', 'name'): ['H. V. Jagadish', 'h. v. jagadish', 'Divesh Srivastava', 'divesh srivastava',
                         'Yunyao Li', 'yunyao li', 'Cong Yu', 'cong yu'],
    ('journal', 'name'): ['PVLDB', 'pvldb', 'University of Michigan', 'university of michigan',
                          'H. V. Jagadish', 'h. v. jagadish', 'P', 'p'],
    ('organization', 'name'): ['University of Michigan', 'university of michigan', 'North America',
                               'north america', 'Unive of Michigan', 'unive of michigan',
                               'University of Man', 'university of man'],
    ('keyword', 'keyword'): ['Natural Language', 'natural language', 'Keyword search', 'keyword search',
                             'H. V. Jagadish', 'h. v. jagadish', 'Making database systems usable',
                             'making database systems usable'],
    ('conference', 'name'): ['VLDB', 'vldb', 'PVLDB', 'pvldb', 'University of Michigan',
                             'university of michigan', 'L', 'l'],
    ('domain', 'name'): ['Databases', 'databases', 'University of Michigan', 'university of michigan',
                         'b', 'B', 'PVLDB', 'pvldb'],
}

_LIKE = {
    ('publication', 'title'): ['%PVLDB%', '%Keyword search%', '%H. V. Jagadish%'],
    ('journal', 'name'): ['%University of Michigan%'],
    ('keyword', 'keyword'): ['Databases%', 'H. V. Jagadish%'],
    ('conference', 'name'): ['VLDB%', 'PVLDB%'],
    ('domain', 'name'): ['%database%'],
    ('organization', 'name'): ['%Databases%'],
}

_BOUND_NUM = {
    ('publication', 'year'): [1999, 2000, 2001, 2009, 2010, 2011],
    ('publication', 'reference_num'): [1999, 2000, 2001],
}

_DUP = {('publication', 'pid'), ('publication', 'title'), ('author', 'aid'), ('author', 'name'),
        ('author', 'homepage'), ('writes', 'aid'), ('writes', 'pid'), ('journal', 'name'),
        ('organization', 'name'), ('keyword', 'keyword'), ('keyword', 'kid'),
        ('conference', 'name'), ('publication_keyword', 'kid'), ('publication', 'citation_num'),
        ('publication', 'reference_num')}

_FK_BOUNDARY = {('writes', 'aid'), ('writes', 'pid')}


def _norm_key(k) -> tuple:
    if isinstance(k, (list, tuple)) and len(k) == 2:
        return (str(k[0]).lower(), str(k[1]).lower())
    return (None, None)


def _is_int_type(t: str) -> bool:
    t = (t or '').upper()
    return any(k in t for k in ('INT', 'NUMBER', 'REAL', 'FLOAT', 'DOUBLE', 'DECIMAL', 'NUMERIC'))


def _looks_numeric(x) -> bool:
    try:
        if isinstance(x, bool):
            return False
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _compact_null_share(schema, key) -> float:
    """Compact-DB null share for column (t, c); 0.10 fallback (review designer item 6)."""
    vals = schema.original_values.get(key, [])
    if not vals:
        return 0.10
    n_null = sum(1 for v in vals if v is None)
    if n_null == 0:
        return 1.0 / max(1, len(vals)) if len(vals) >= 10 else 0.10
    return max(n_null / len(vals), 1.0 / max(1, len(vals)))


def _base_spec(schema) -> dict:
    """The built-in specification, restricted to columns that exist in the schema."""
    spec = {'sizes': {}, 'ranges': {}, 'enums': {}, 'near_variants': {}, 'like_patterns': {},
            'boundary_numeric': {}, 'boundary_text': {}, 'dup_share': {}, 'null_share': {},
            'unmatched_share': {}, 'orphan_share': {}, 'fk_columns': {}, 'pk_columns': {},
            'notnull': {}, 'types': {}}
    for t, tm in schema.tables.items():
        tl = t.lower()
        spec['sizes'][t] = _SIZES.get(tl, 20)
        spec['pk_columns'][t] = list(tm.primary_key)
        spec['orphan_share'][t] = 0.10
        for c in tm.columns:
            key = (tl, c.name.lower())
            real = (t, c.name)
            is_int = _is_int_type(c.type_str or '')
            spec['notnull'][real] = bool(c.notnull or c.pk_pos > 0)
            spec['types'][real] = (c.type_str or '').upper()
            if key in _RANGES:
                spec['ranges'][real] = _RANGES[key]
            if key in _ENUMS:
                spec['enums'][real] = list(_ENUMS[key])
            if key in _NEAR and not is_int:
                spec['near_variants'][real] = list(_NEAR[key])
            if key in _LIKE and not is_int:
                spec['like_patterns'][real] = list(_LIKE[key])
            if key in _BOUND_NUM and is_int:
                spec['boundary_numeric'][real] = list(_BOUND_NUM[key])
            if key in _DUP:
                spec['dup_share'][real] = 0.35
            if not spec['notnull'][real]:
                spec['null_share'][real] = _compact_null_share(schema, real)
    for (ct, cc), (pt, pc) in schema.fks.items():
        spec['fk_columns'][(ct, cc)] = (pt, pc)
        if not spec['notnull'].get((ct, cc), False):
            spec['unmatched_share'][(ct, cc)] = 0.0
    for key in list(spec['near_variants']):
        if key in spec['enums']:
            del spec['near_variants'][key]
    for key in list(spec['boundary_text']):
        if key in spec['enums']:
            del spec['boundary_text'][key]
    for k, vals in spec['near_variants'].items():
        spec['boundary_text'][k] = list(vals)
    return spec


def spec_from_columns(schema) -> dict:
    """Specification derived from the schema alone (no specification.json)."""
    return _base_spec(schema)


def _route_targets(spec: dict, key: tuple, targets: list) -> dict:
    """Split targets by the column's declared type (review designer item 5)."""
    typ = spec['types'].get(key, '')
    is_int = _is_int_type(typ)
    nums, strs = [], []
    for x in targets:
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            nums.append(int(x))
        elif isinstance(x, str):
            if _looks_numeric(x) and is_int:
                try:
                    nums.append(int(float(x)))
                except ValueError:
                    strs.append(x)
            elif is_int:
                continue
            else:
                strs.append(x)
        else:
            if is_int:
                try:
                    nums.append(int(x))
                except (TypeError, ValueError):
                    pass
    return {'num': nums, 'str': strs}


def load_specification(raw: dict, schema) -> dict:
    """Merge a specification.json (pipeline file) over the built-in table."""
    spec = _base_spec(schema)
    if not isinstance(raw, dict):
        return spec
    sizes = raw.get('table_sizes_per_instance') or {}
    for t, n in sizes.items():
        real = next((x for x in schema.tables if x.lower() == str(t).lower()), None)
        if real is not None:
            try:
                spec['sizes'][real] = int(n)
            except (TypeError, ValueError):
                pass
    enum_cols = set(spec['enums'])
    for exc in raw.get('per_column_exceptions') or []:
        if not isinstance(exc, dict):
            continue
        t = next((x for x in schema.tables if x.lower() == str(exc.get('table', '')).lower()), None)
        if t is None:
            continue
        c = next((x.name for x in schema.tables[t].columns
                  if x.name.lower() == str(exc.get('column', '')).lower()), None)
        if c is None:
            continue
        pat = str(exc.get('pattern', ''))
        tg = [x for x in (exc.get('targets') or []) if isinstance(x, (str, int, float))]
        key = (t, c)
        if pat == 'comparison_boundary':
            routed = _route_targets(spec, key, tg)
            if routed['num']:
                spec['boundary_numeric'][key] = routed['num']
            if routed['str'] and key not in enum_cols:
                spec['near_variants'][key] = routed['str']
                spec['boundary_text'][key] = routed['str']
        elif pat == 'like_near_variant':
            if key in enum_cols:
                continue
            pats = [str(x) for x in tg if '%' in str(x)]
            vals = [str(x) for x in tg if '%' not in str(x)]
            if pats:
                spec['like_patterns'][key] = pats
            if vals:
                spec['near_variants'][key] = vals
        elif pat == 'duplicates_for_distinct':
            spec['dup_share'][key] = 0.35
        elif pat == 'unmatched_join_rows':
            pass
    for rule in raw.get('semantic_rules_and_formulas') or []:
        if not isinstance(rule, dict):
            continue
        t = next((x for x in schema.tables if x.lower() == str(rule.get('table', '')).lower()), None)
        if t is None:
            continue
        c = next((x.name for x in schema.tables[t].columns
                  if x.name.lower() == str(rule.get('column', '')).lower()), None)
        if c is None:
            continue
        f = str(rule.get('formula', ''))
        key = (t, c)
        m = re.search(r'between\s+(-?\d+)\s+and\s+(-?\d+)', f, re.I)
        if m:
            spec['ranges'][key] = (int(m.group(1)), int(m.group(2)))
            continue
        m = re.search(r"in\s*\(([^)]*)\)", f, re.I)
        if m and 'select' not in m.group(1).lower():
            vals = [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]
            if vals:
                spec['enums'][key] = vals
                spec['near_variants'].pop(key, None)
                spec['boundary_text'].pop(key, None)
            continue
        m = re.search(r'>=\s*(-?\d+)', f)
        if m:
            spec['ranges'][key] = (int(m.group(1)), max(1000, int(m.group(1)) + 1000))
            continue
        m = re.search(r'>\s*(-?\d+)', f)
        if m:
            spec['ranges'][key] = (int(m.group(1)) + 1, max(1000, int(m.group(1)) + 1000))
    return spec
