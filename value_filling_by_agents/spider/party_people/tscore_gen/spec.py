"""Specification model: value domains, ranges, dependencies, NULL rule, semantic formulas."""
import json
import re

DEFAULT_SPEC = {
    "table_sizes_per_instance": {"region": 5, "party": 5, "member": 15, "party_events": 8},
    "null_targets": ["party_events.Party_ID", "party_events.Member_in_charge_ID"],
    "enums": {
        "party.Party_name": ["Convention Peoples Party", "Progress Party", "3",
                             "Convention Union Party", "Sinefine Party"],
        "region.Region_name": ["United Kingdom", "Japan", "United States"],
        "member.Party_ID": ["1", "2", "3"],
        "party_events.Event_Name": ["Annaual Meeting", "Conference", "Budget Meeting", "Election Meeting"],
    },
    "ranges": {
        "party.Took_office": [1957, 1961],
        "party.Left_office": [1958, 1962],
    },
    "near_variants": {
        "party.Party_name": ["Progress  Party", "Progress Party "],
        "region.Region_name": ["United  Kingdom", "United Kingdom "],
    },
    "comparison_boundary": {
        "party.Party_name": ["Progress Party", "progress party"],
        "region.Region_name": ["United Kingdom", "united kingdom"],
    },
    "group_sizes": {
        "party.Party_name": "1, 2 and >= 3",
        "party.Party_ID": "1, 2 and >= 3",
        "party_events.Party_ID": "1, 2 and >= 3",
        "member.Party_ID": "1, 2 and >= 3",
        "member.Member_Name": "1, 2 and >= 3",
        "party_events.Event_Name": "1, 2 and >= 3",
        "party_events.Member_in_charge_ID": "1, 2 and >= 3",
    },
    "duplicate_share": {
        "party.Party_name": [0.2, 0.5],
        "member.Member_Name": [0.2, 0.5],
        "party.Minister": [0.2, 0.5],
        "region.Region_ID": [0.2, 0.5],
    },
    "ties": {
        "party.Party_ID": {"direction": "DESC", "tie_at_rank": [1]},
        "member.Party_ID": {"direction": "DESC", "tie_at_rank": [1]},
        "party.Left_office": {"direction": "ASC and DESC", "tie_at_rank": [1]},
        "party.Region_ID": {"direction": "ASC", "tie_at_rank": "any"},
    },
    "unmatched_join": {
        "party.Party_ID": ["party_events.Party_ID", "member.Party_ID"],
        "party_events.Party_ID": ["party.Party_ID", "member.Party_ID", "party.Region_ID"],
        "member.Party_ID": ["party.Party_ID", "party_events.Party_ID"],
    },
    "aggregate_boundary": {
        "party_events.Party_ID": {"aggregate": "COUNT(*)", "values": [1, 2, 3]},
    },
    "rows_with_different_values": {
        "party.Left_office": ">= 2 per group with different values",
    },
    "formulas": [
        {"table": "party", "column": "Party_ID", "kind": "gt0"},
        {"table": "party", "column": "Took_office", "kind": "int_range", "lo": 1957, "hi": 1961},
        {"table": "party", "column": "Left_office", "kind": "int_range", "lo": 1958, "hi": 1962},
        {"table": "party", "column": "Left_office", "kind": "gt_column", "other": "Took_office"},
        {"table": "party", "column": "Party_name", "kind": "enum"},
        {"table": "region", "column": "Region_ID", "kind": "gt0"},
        {"table": "region", "column": "Region_name", "kind": "enum"},
        {"table": "member", "column": "Member_ID", "kind": "gt0"},
        {"table": "member", "column": "Party_ID", "kind": "enum"},
        {"table": "party_events", "column": "Event_ID", "kind": "gt0"},
        {"table": "party_events", "column": "Event_Name", "kind": "enum"},
    ],
}


def _split_key(k: str):
    if '.' in k:
        t, c = k.split('.', 1)
        return t, c
    return None, k


def _norm_key(k: str, schema) -> str:
    """Normalise 'table.column' to the schema's actual table/column spelling."""
    t, c = _split_key(k)
    if t is None:
        return k
    tl = {x.lower(): x for x in schema.tables}
    tt = tl.get(t.lower(), t)
    cl = {x.name.lower(): x.name for x in schema.tables.get(tt, schema.tables.get(t)).columns} \
        if (tt in schema.tables or t in schema.tables) else {}
    cc = cl.get(c.lower(), c)
    return '%s.%s' % (tt, cc)


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_specification(path: str) -> dict:
    """Read the pipeline-written specification JSON (may be partial)."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _formulas_from_spec(raw: dict) -> list:
    """Translate the specification's semantic_rules_and_formulas into internal formula records."""
    out = []
    for r in raw.get('semantic_rules_and_formulas', []) or []:
        t, c = r.get('table'), r.get('column')
        f = (r.get('formula') or '').strip()
        if not t or not c:
            continue
        m = re.fullmatch(r'CAST\((\w+) AS INTEGER\) BETWEEN (\d+) AND (\d+)', f, re.I)
        if m:
            out.append({'table': t, 'column': c, 'kind': 'int_range', 'lo': int(m.group(2)), 'hi': int(m.group(3))})
            continue
        m = re.fullmatch(r'CAST\((\w+) AS INTEGER\) > CAST\((\w+) AS INTEGER\)', f, re.I)
        if m:
            out.append({'table': t, 'column': c, 'kind': 'gt_column', 'other': m.group(2)})
            continue
        m = re.fullmatch(r'(\w+) > 0', f)
        if m:
            out.append({'table': t, 'column': c, 'kind': 'gt0'})
            continue
        m = re.fullmatch(r"(\w+) IN \((.*)\)", f, re.I | re.S)
        if m:
            vals = re.findall(r"'((?:[^']|'')*)'", m.group(2))
            out.append({'table': t, 'column': c, 'kind': 'enum', 'values': [v.replace("''", "'") for v in vals]})
            continue
    return out


def build_spec(raw: dict, schema) -> dict:
    """Merge the JSON specification with the fallback and normalise keys to the schema."""
    spec = _merge(DEFAULT_SPEC, {})
    if raw:
        enums = dict(spec['enums'])
        for r in raw.get('semantic_rules_and_formulas', []) or []:
            f = (r.get('formula') or '')
            m = re.fullmatch(r"(\w+) IN \((.*)\)", f.strip(), re.I | re.S)
            if m and r.get('table') and r.get('column'):
                vals = [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", m.group(2))]
                if vals:
                    enums['%s.%s' % (r['table'], r['column'])] = vals
        spec['enums'] = enums
        if raw.get('table_sizes_per_instance'):
            spec['table_sizes_per_instance'] = dict(raw['table_sizes_per_instance'])
        if raw.get('null_targets'):
            spec['null_targets'] = list(raw['null_targets'])
        for ex in raw.get('per_column_exceptions', []) or []:
            col = ex.get('column')
            pat = ex.get('pattern')
            tg = ex.get('targets') or {}
            if not col:
                continue
            if pat == 'comparison_boundary':
                spec['comparison_boundary'][col] = list(tg.get('values') or [])
                if tg.get('near_variants'):
                    spec['near_variants'][col] = list(tg['near_variants'])
            elif pat == 'group_sizes':
                spec['group_sizes'][col] = tg.get('group_sizes', '1, 2 and >= 3')
            elif pat == 'duplicates_for_distinct':
                spec['duplicate_share'][col] = [0.2, 0.5]
            elif pat == 'ties_for_order_limit':
                spec['ties'][col] = {'direction': tg.get('direction', 'ASC'),
                                     'tie_at_rank': tg.get('tie_at_rank', 'any')}
            elif pat == 'unmatched_join_rows':
                spec['unmatched_join'][col] = list(tg.get('joins_with') or [])
            elif pat == 'aggregate_boundary':
                spec['aggregate_boundary'][col] = {'aggregate': (tg.get('aggregate') or ['COUNT(*)'])[0],
                                                   'values': list(tg.get('values') or [1, 2, 3])}
            elif pat == 'rows_with_different_values':
                spec['rows_with_different_values'][col] = tg.get('qualifying_rows', '>= 2')
            elif pat == 'null_rows':
                if col not in spec['null_targets']:
                    spec['null_targets'].append(col)
        f = _formulas_from_spec(raw)
        if f:
            spec['formulas'] = f
    for key in ('enums', 'ranges', 'near_variants', 'comparison_boundary', 'group_sizes',
                'duplicate_share', 'ties', 'unmatched_join', 'aggregate_boundary',
                'rows_with_different_values'):
        spec[key] = {_norm_key(k, schema): v for k, v in spec.get(key, {}).items()}
    spec['null_targets'] = [_norm_key(k, schema) for k in spec.get('null_targets', [])]
    spec['formulas'] = [dict(r, table=_norm_key('%s.%s' % (r['table'], r['column']), schema).split('.')[0],
                             column=_norm_key('%s.%s' % (r['table'], r['column']), schema).split('.')[1])
                        for r in spec.get('formulas', [])]
    return spec


def formulas_for(spec: dict, table: str, column: str) -> list:
    """All formula records that constrain (table, column)."""
    return [r for r in spec.get('formulas', []) if r['table'] == table and r['column'] == column]


def enum_for(spec: dict, table: str, column: str):
    """Enumerated value list for a column, or None."""
    return spec.get('enums', {}).get('%s.%s' % (table, column))


def range_for(spec: dict, table: str, column: str):
    """(lo, hi) integer range for a column, or None."""
    return spec.get('ranges', {}).get('%s.%s' % (table, column))


def null_share_for(spec: dict, table: str, column: str, observed: float) -> float:
    """NULL share: observed share, but at least one NULL row per instance for nullable columns."""
    key = '%s.%s' % (table, column)
    if key in spec.get('null_targets', []):
        return max(observed, 0.08)
    return observed
