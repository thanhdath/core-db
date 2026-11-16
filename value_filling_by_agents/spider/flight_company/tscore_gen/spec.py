"""Specification loading: value pools, ranges, enumerations, NULL shares, group/aggregate targets."""
import re

DEFAULT_NULL_SHARE = 0.10
NEAR_VARIANT_PROB = 0.15
DISTINCT_DUP_SHARE = (0.20, 0.50)
GROUP_SIZES = (1, 2, 3)
AGG_BOUNDARY = (0, 1, 2)
AGG_BOUNDARY_GT2 = (1, 2, 3)


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def _split_qualified(x) -> tuple:
    """Accept 'table.column' strings or [table, column] pairs."""
    if isinstance(x, (list, tuple)) and len(x) >= 2:
        return str(x[0]), str(x[1])
    s = str(x)
    if '.' in s:
        t, c = s.split('.', 1)
        return t, c
    return '', s


def load_specification(raw: dict, schema) -> dict:
    """Normalise a specification dict into per-(table, column) rules keyed by real names."""
    out = {'null_share': {}, 'pools': {}, 'ranges': {}, 'enums': {}, 'lengths': {},
           'group_targets': set(), 'agg_targets': {}, 'distinct_targets': set(),
           'fk_null': {}, 'table_sizes': {}, 'formulas': []}
    tmap = {_norm(t): t for t in schema.tables}
    cmap = {(t, _norm(c.name)): c.name for t, tm in schema.tables.items() for c in tm.columns}

    def key(t, c):
        t = tmap.get(_norm(t), t)
        return (t, cmap.get((t, _norm(c)), c))

    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        out['table_sizes'][tmap.get(_norm(t), t)] = int(n)
    for item in (raw.get('null_targets') or []):
        t, c = _split_qualified(item)
        if not t:
            continue
        out['null_share'][key(t, c)] = DEFAULT_NULL_SHARE
    for ex in raw.get('per_column_exceptions') or []:
        k = key(ex.get('table', ''), ex.get('column', ''))
        pat = ex.get('pattern')
        tg = ex.get('targets') or []
        if pat == 'comparison_boundary':
            out['pools'].setdefault(k, [])
            for v in tg:
                if not isinstance(v, str):
                    continue
                if v.startswith(('parent ', 'child ', 'COUNT', 'airport.', 'flight.', 'operate_company.')):
                    continue
                if v in ('<', '>', '=', '<=', '>=', '<>', '!='):
                    continue
                out['pools'][k].append(v)
        elif pat == 'group_sizes':
            out['group_targets'].add(k)
        elif pat == 'aggregate_boundary':
            out['agg_targets'][k] = AGG_BOUNDARY_GT2 if any('> 2' in str(x) for x in tg) else AGG_BOUNDARY
        elif pat == 'duplicates_for_distinct':
            out['distinct_targets'].add(k)
        elif pat == 'unmatched_join_rows':
            out['fk_null'][k] = True
    for r in raw.get('semantic_rules_and_formulas') or []:
        out['formulas'].append(r)
        f = str(r.get('formula', ''))
        k = key(r.get('table', ''), r.get('column', ''))
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m and 'SELECT' not in m.group(1).upper():
            out['enums'][k] = [x.strip().strip("'\"") for x in m.group(1).split(',')]
        m = re.search(r"length\([^)]*\)\s*=\s*(\d+)", f, re.I)
        if m:
            out['lengths'][k] = int(m.group(1))
        m = re.search(r">=\s*(-?\d+(?:\.\d+)?)\s+AND[^<]*<=\s*(-?\d+(?:\.\d+)?)", f, re.I)
        if m:
            out['ranges'][k] = (float(m.group(1)), float(m.group(2)))
        m = re.search(r">=\s*(-?\d+(?:\.\d+)?)", f, re.I)
        if m and k not in out['ranges']:
            out['ranges'][k] = (float(m.group(1)), None)
    return out


def spec_from_schema(schema) -> dict:
    """Conservative default specification derived from the compact database."""
    out = {'null_share': {}, 'pools': {}, 'ranges': {}, 'enums': {}, 'lengths': {},
           'group_targets': set(), 'agg_targets': {}, 'distinct_targets': set(),
           'fk_null': {}, 'table_sizes': {}, 'formulas': []}
    for t, tm in schema.tables.items():
        for c in tm.columns:
            k = (t, c.name)
            if not c.notnull and c.pk_pos == 0:
                out['null_share'][k] = DEFAULT_NULL_SHARE
            if k in schema.fks:
                out['fk_null'][k] = True
            tl = (c.type_str or '').lower()
            if 'int' in tl or 'real' in tl or 'float' in tl or 'double' in tl:
                out['ranges'][k] = (0.0, None)
    return out
