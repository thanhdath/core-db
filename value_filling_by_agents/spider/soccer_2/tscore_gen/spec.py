"""Specification loading and literal routing (tscore_gen/specification.json)."""
import json
import re

_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def load_specification(path: str) -> dict:
    """Read the specification JSON and normalise it into a dict keyed by (table, column)."""
    with open(path) as f:
        raw = json.load(f)
    return normalise_spec(raw)


def _key(t: str, c: str) -> tuple:
    return (t, c)


def normalise_spec(raw: dict) -> dict:
    """Flatten per_column_exceptions / semantic rules / sizes into lookup tables."""
    out = {'columns': {}, 'sizes': {}, 'deps': [], 'formulas': {}, 'null_targets': set(),
           'like_literals': {}, 'near_variants': {}, 'tie_targets': {}, 'group_sizes': {},
           'parent_without_children': set(), 'child_null_fk': set(), 'having_gt': {},
           'qualifying_rows': {}, 'duplicate_share': {}, 'boundary_values': {},
           'boundary_numeric': {}, 'boundary_text': {}, 'order_tie': {}, 'raw': raw}
    for ex in raw.get('per_column_exceptions', []) or []:
        t, c = ex.get('table'), ex.get('column')
        if not t or not c:
            continue
        k = _key(t, c)
        tg = ex.get('targets', {}) or {}
        out['columns'][k] = {'pattern': ex.get('pattern', ''), 'targets': tg}
        if 'values' in tg:
            out['boundary_values'][k] = [str(v) for v in tg['values']]
        if 'null_share' in tg:
            out['null_targets'].add(k)
        if 'duplicate_share' in tg:
            out['duplicate_share'][k] = tg['duplicate_share']
        if 'like_literals' in tg:
            out['like_literals'][k] = list(tg['like_literals'])
        if 'near_variants' in tg:
            out['near_variants'][k] = list(tg['near_variants'])
        if 'tie_at_rank' in tg:
            out['tie_targets'][k] = tg['tie_at_rank']
        if 'group_sizes' in tg:
            out['group_sizes'][k] = tg['group_sizes']
        if tg.get('parent_rows_without_children'):
            out['parent_without_children'].add(k)
        if tg.get('child_rows_with_null_fk'):
            out['child_null_fk'].add(k)
        if 'having_count_gt' in tg:
            out['having_gt'][k] = tg['having_count_gt']
        if 'qualifying_rows' in tg:
            out['qualifying_rows'][k] = tg['qualifying_rows']
    for d in raw.get('dependencies', []) or []:
        out['deps'].append((d['child_table'], d['child_column'], d['parent_table'], d['parent_column']))
    for r in raw.get('semantic_rules_and_formulas', []) or []:
        out['formulas'][_key(r['table'], r['column'])] = r.get('formula', '')
    for t, n in (raw.get('table_sizes_per_instance', {}) or {}).items():
        out['sizes'][t] = int(n)
    for nt in raw.get('null_targets', []) or []:
        if '.' in nt:
            t, c = nt.split('.', 1)
            out['null_targets'].add(_key(t, c))
    return out


def _numeric_literals(values: list) -> list:
    out = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def spec_pool_literals(spec: dict, schema) -> dict:
    """Route specification literals to (table, column) pools."""
    pool: dict = {}
    tlow = {t.lower(): t for t in schema.tables}
    clow = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            clow.setdefault(cm.name.lower(), []).append((t, cm.name))

    def add(k, v):
        pool.setdefault(k, [])
        if v not in pool[k]:
            pool[k].append(v)

    for k, vals in spec.get('boundary_values', {}).items():
        t, c = k
        if t not in schema.tables:
            continue
        nums = _numeric_literals(vals)
        if nums and all(_NUM.fullmatch(str(v)) for v in vals):
            for n in nums:
                for d in (-1, 0, 1):
                    add(k, int(n + d) if float(n + d).is_integer() else n + d)
        else:
            for v in vals:
                add(k, v)
                add(k, v.upper())
                add(k, v.lower())
    for k, lits in spec.get('like_literals', {}).items():
        for lit in lits:
            body = lit[:-1] if lit.endswith('%') else lit
            for v in (body, body.lower(), body + 'a', body + 'x'):
                add(k, v)
    for k, nv in spec.get('near_variants', {}).items():
        for v in nv:
            add(k, v)
    for k, vals in list(pool.items()):
        t, c = k
        if t not in schema.tables:
            for tt, cc in clow.get(c.lower(), []):
                for v in vals:
                    add((tt, cc), v)
    return pool
