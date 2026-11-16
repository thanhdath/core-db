"""Specification -> construction rules (enumerations, NULL shares, duplicates, boundaries)."""
import json
import re

_DEFAULT_ENUMS = {
    ('Ref_Characteristic_Types', 'characteristic_type_code'): ['Grade', 'Purity'],
    ('Ref_Colors', 'color_code'): ['1', '2', '3', '4', '5', '7', '8', '9'],
    ('Ref_Product_Categories', 'product_category_code'): ['Herbs', 'Seeds', 'Spices'],
    ('Ref_Product_Categories', 'unit_of_measure'): ['Handful', 'Weight - pound,kilo.'],
    ('Characteristics', 'characteristic_type_code'): ['Grade', 'Purity'],
    ('Products', 'color_code'): ['1', '2', '3', '4', '5', '7', '8', '9'],
    ('Products', 'product_category_code'): ['Herbs', 'Seeds', 'Spices'],
    ('Product_Characteristics', 'product_characteristic_value'): ['low', 'medium', 'high'],
}

_DEFAULT_ENUM_STRICT = {
    ('Ref_Characteristic_Types', 'characteristic_type_code'),
    ('Ref_Colors', 'color_code'),
    ('Ref_Product_Categories', 'product_category_code'),
    ('Characteristics', 'characteristic_type_code'),
    ('Products', 'color_code'),
    ('Products', 'product_category_code'),
    ('Product_Characteristics', 'product_characteristic_value'),
}

_DEFAULT_BOUNDARIES = {
    ('Product_Characteristics', 'characteristic_id'): ['slow', 'SLOW'],
    ('Ref_Product_Categories', 'product_category_code'): ['Spices', 'spices', 'Herbs', 'herbs'],
    ('Products', 'product_category_code'): ['Seeds', 'seeds', 'Spices', 'spices', 'Herbs', 'herbs'],
    ('Characteristics', 'characteristic_name'): ['slow', 'SLOW', 'hot', 'HOT', '', 'x'],
    ('Products', 'product_id'): ['flax', 'FLAX'],
    ('Products', 'product_name'): ['flax', 'FLAX', 'sesame', 'SESAME', 'f', 'F'],
    ('Ref_Product_Categories', 'product_category_description'): ['Seeds', 'seeds', 'Herbs', 'herbs',
                                                                  'Spices', 'spices'],
    ('Ref_Colors', 'color_description'): ['red', 'RED', 'white', 'WHITE', 'wh', 'WH'],
    ('Characteristics', 'characteristic_type_code'): ['Grade', 'grade'],
    ('Ref_Characteristic_Types', 'characteristic_type_code'): ['Grade', 'grade'],
    ('Ref_Product_Categories', 'unit_of_measure'): ['Handful', 'handful'],
}

_DEFAULT_QUERY_ONLY = {
    ('Product_Characteristics', 'characteristic_id'): {'slow', 'SLOW'},
    ('Products', 'product_id'): {'flax', 'FLAX'},
    ('Characteristics', 'characteristic_name'): {'', 'x'},
    ('Products', 'product_name'): {'f', 'F'},
}

_DEFAULT_DUP = {
    ('Product_Characteristics', 'characteristic_id'): 0.35,
    ('Characteristics', 'characteristic_name'): 0.35,
    ('Products', 'product_name'): 0.35,
    ('Product_Characteristics', 'product_characteristic_value'): 0.35,
    ('Products', 'product_description'): 0.35,
}

_DEFAULT_AGG = {
    ('Product_Characteristics', 'characteristic_id'),
    ('Products', 'product_id'),
    ('Ref_Colors', 'color_description'),
}

_DEFAULT_TIE = {('Characteristics', 'characteristic_name')}

_DEFAULT_GROUP = {
    ('Characteristics', 'characteristic_id'),
    ('Characteristics', 'characteristic_name'),
    ('Products', 'color_code'),
    ('Ref_Colors', 'color_code'),
    ('Characteristics', 'characteristic_type_code'),
    ('Ref_Characteristic_Types', 'characteristic_type_code'),
}

_DEFAULT_FORCE_NULL = {
    ('Product_Characteristics', 'characteristic_id'),
    ('Ref_Colors', 'color_code'),
}

_DEFAULT_FK_NULL = set()

_DEFAULT_UNMATCHED_PARENTS = {
    'Ref_Colors', 'Ref_Product_Categories', 'Ref_Characteristic_Types',
    'Products', 'Characteristics',
}

_DEFAULT_ALL_NULL = {
    ('Characteristics', 'other_characteristic_details'),
    ('Products', 'other_product_details'),
}


def _norm_key(t: str, c: str) -> tuple:
    return (str(t), str(c))


def load_specification(path: str) -> dict:
    """Read the pipeline's specification.json (tolerant: any missing part falls back)."""
    with open(path) as f:
        return json.load(f)


def _parent_of(joins_with: str):
    """'joins_with:Products.product_category_code' -> ('Products', 'product_category_code')."""
    s = joins_with.split(':', 1)[-1].strip()
    t, _, c = s.partition('.')
    return (t, c) if t and c else (None, None)


def _from_json(spec: dict) -> dict:
    """Translate the JSON specification into construction rules."""
    out = {'enums': {}, 'enum_strict': set(), 'boundaries': {}, 'query_only': {},
           'dup': {}, 'agg': set(), 'tie': set(), 'group': set(), 'force_null': set(),
           'fk_null': set(), 'unmatched_parents': set(), 'all_null': set(),
           'null_share': {}, 'sizes': {}, 'formulas': {}}
    for rule in spec.get('semantic_rules_and_formulas', []) or []:
        t, c, f = rule.get('table'), rule.get('column'), rule.get('formula', '')
        if not t or not c:
            continue
        k = _norm_key(t, c)
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m and 'IS NULL OR' not in f.upper():
            vals = [x.strip().strip("'\"") for x in m.group(1).split(',')]
            out['enums'][k] = [v for v in vals if v != '']
            out['enum_strict'].add(k)
        out['formulas'][k] = f
    for exc in spec.get('per_column_exceptions', []) or []:
        pat = exc.get('pattern')
        for col, targets in (exc.get('targets') or {}).items():
            t, _, c = col.partition('.')
            k = _norm_key(t, c)
            if pat == 'enum_strict':
                out['enum_strict'].add(k)
            elif pat == 'comparison_boundary':
                out['boundaries'][k] = [str(x) for x in targets]
            elif pat == 'query_only_boundaries':
                out['query_only'][k] = {str(x) for x in targets}
            elif pat == 'duplicates_for_distinct':
                out['dup'][k] = 0.35
            elif pat == 'aggregate_boundary':
                out['agg'].add(k)
            elif pat == 'ties_for_order_limit':
                out['tie'].add(k)
            elif pat == 'group_sizes':
                out['group'].add(k)
            elif pat == 'null_rows':
                out['force_null'].add(k)
            elif pat == 'null_in_count_column':
                out['force_null'].add(k)
            elif pat == 'intentionally_all_null':
                out['all_null'].add(k)
            elif pat == 'unmatched_join_rows':
                if isinstance(targets, list):
                    for tg in targets:
                        if isinstance(tg, str) and tg.startswith('joins_with:'):
                            pt, _pc = _parent_of(tg)
                            if pt:
                                out['unmatched_parents'].add(pt)
                        if isinstance(tg, str) and tg.startswith('child_rows_with_null_fk'):
                            out['fk_null'].add(k)
                elif isinstance(targets, dict):
                    if targets.get('parent_rows_without_children'):
                        for tg in targets.get('joins_with', []) or []:
                            pt, _pc = _parent_of(tg)
                            if pt:
                                out['unmatched_parents'].add(pt)
                    if targets.get('child_rows_with_null_fk'):
                        out['fk_null'].add(k)
    for t, n in (spec.get('table_sizes_per_instance') or {}).items():
        out['sizes'][t] = int(n)
    return out


def build_spec(schema, spec_json: dict) -> dict:
    """Merge JSON rules with the built-in defaults and the compact database's NULL shares."""
    rules = _from_json(spec_json or {})
    enums = dict(_DEFAULT_ENUMS)
    enums.update(rules['enums'])
    enum_strict = set(_DEFAULT_ENUM_STRICT) | rules['enum_strict']
    boundaries = dict(_DEFAULT_BOUNDARIES)
    boundaries.update(rules['boundaries'])
    query_only = {k: set(v) for k, v in _DEFAULT_QUERY_ONLY.items()}
    for k, v in rules['query_only'].items():
        query_only.setdefault(k, set()).update(v)
    dup = dict(_DEFAULT_DUP)
    dup.update(rules['dup'])
    all_null = set(_DEFAULT_ALL_NULL) | rules['all_null']
    null_share = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            vals = schema.original_values.get((t, cm.name), [])
            if not vals:
                null_share[(t, cm.name)] = 0.0
                continue
            null_share[(t, cm.name)] = sum(1 for v in vals if v is None) / float(len(vals))
    low = {(t.lower(), c.name.lower()): (t, c.name) for t, tm in schema.tables.items() for c in tm.columns}

    def remap(d):
        out = {}
        for (t, c), v in d.items():
            k = low.get((t.lower(), c.lower()))
            if k is not None:
                out[k] = v
        return out

    def remap_set(s):
        out = set()
        for (t, c) in s:
            k = low.get((t.lower(), c.lower()))
            if k is not None:
                out.add(k)
        return out

    unmatched_parents = set(_DEFAULT_UNMATCHED_PARENTS)
    unmatched_parents |= {t for t in rules['unmatched_parents'] if t in schema.tables}
    return {
        'enums': remap(enums),
        'enum_strict': remap_set(enum_strict),
        'boundaries': remap(boundaries),
        'query_only': {k: v for k, v in remap(query_only).items()},
        'dup': remap(dup),
        'agg': remap_set(rules['agg']),
        'tie': remap_set(rules['tie']),
        'group': remap_set(rules['group']),
        'force_null': remap_set(rules['force_null']),
        'fk_null': remap_set(rules['fk_null']),
        'unmatched_parents': unmatched_parents,
        'all_null': remap_set(all_null),
        'null_share': null_share,
        'sizes': rules['sizes'],
        'formulas': remap(rules['formulas']),
    }
