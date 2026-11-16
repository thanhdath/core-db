"""Specification loading and per-column domain description."""
import json
import os

_DEFAULT = {
    'table_sizes': {'Ship': 9, 'captain': 7},
    'null_targets': ['captain.Ship_ID'],
    'columns': {
        'Ship.Ship_ID': {'kind': 'int_pk', 'min': 1, 'tie_at_rank': [1], 'tie_direction': 'DESC'},
        'Ship.Name': {'kind': 'text_name', 'pool': [
            'HMS Manxman', 'HMS Gorgon', 'HM Cutter Avenger', 'HM Schooner Hotspur',
            'HMS Destiny', 'HMS Trojan', 'HM Sloop Sparrow', 'HMS Phalarope'],
            'dup_share': (0.2, 0.5), 'group_sizes': [1, 2, 3]},
        'Ship.Type': {'kind': 'text_enum', 'values': ['Panamax'], 'soft': True,
                      'extra_values': ['Handysize', 'Aframax', 'Suezmax'], 'group_sizes': [1, 2, 3]},
        'Ship.Built_Year': {'kind': 'real_numeric', 'min': 1997.0, 'max': 1998.0, 'soft': True,
                            'integer_like': True, 'group_sizes': [1, 2, 3],
                            'tie_at_rank': [1], 'tie_direction': 'DESC'},
        'Ship.Class': {'kind': 'text_enum', 'values': ['KR', 'GL'], 'soft': True,
                       'extra_values': ['LR', 'NV'], 'group_sizes': [1, 2, 3]},
        'Ship.Flag': {'kind': 'text_enum', 'values': ['Panama', 'Malta'], 'soft': True,
                      'extra_values': ['Liberia', 'Cyprus'],
                      'variants': ['panama', 'malta'], 'dup_share': (0.2, 0.5)},
        'captain.Captain_ID': {'kind': 'int_pk', 'min': 1},
        'captain.Name': {'kind': 'text_name', 'pool': [
            'Captain Sir Henry Langford', 'Captain Beves Conway', 'Lieutenant Hugh Bolitho',
            'Lieutenant Montagu Verling', 'Captain Henry Dumaresq', 'Captain Gilbert Pears',
            'Commander Richard Bolitho'], 'group_sizes': [1, 2, 3], 'order_asc': True},
        'captain.Ship_ID': {'kind': 'int_fk', 'null_share': (0.05, 0.30), 'group_sizes': [1, 2, 3]},
        'captain.age': {'kind': 'text_free', 'min': 18, 'max': 80, 'numeric_text': True,
                        'distinct_per_group': 2},
        'captain.Class': {'kind': 'text_enum', 'values': [
            'Third-rate ship of the line', 'Cutter', 'Armed schooner', 'Frigate', 'Sloop-of-war'],
            'variants': ['armed schooner'], 'dup_share': (0.2, 0.5), 'group_sizes': [1, 2, 3]},
        'captain.Rank': {'kind': 'text_enum', 'values': [
            'Midshipman', 'Lieutenant', 'Commander, junior captain'],
            'variants': ['midshipman'], 'group_sizes': [1, 2, 3]},
    },
    'dependencies': [{'child_table': 'captain', 'child_column': 'Ship_ID',
                      'parent_table': 'Ship', 'parent_column': 'Ship_ID'}],
}


def default_specification() -> dict:
    """Return a deep-ish copy of the built-in default specification."""
    return json.loads(json.dumps(_DEFAULT))


def _norm_key(k: str) -> str:
    return k.strip()


def _split_inner(f: str) -> list:
    """Values inside the first (...) of an IN formula."""
    try:
        inner = f[f.index('(') + 1:f.rindex(')')]
    except ValueError:
        return []
    return [x.strip().strip("'\"") for x in inner.split(',') if x.strip()]


def _is_soft(vals: list, lo=None, hi=None) -> bool:
    """Single-value IN or a two-value / narrow BETWEEN is a small-sample artifact."""
    if vals is not None and len(vals) <= 2:
        return True
    if lo is not None and hi is not None and (hi - lo) <= 2:
        return True
    return False


def load_specification(path: str) -> dict:
    """Read specification.json and normalise it into the sampler-facing dict."""
    with open(path) as f:
        raw = json.load(f)
    if 'columns' in raw and isinstance(raw['columns'], dict):
        spec = json.loads(json.dumps(raw))
        spec.setdefault('table_sizes', {})
        spec.setdefault('dependencies', [])
        spec.setdefault('null_targets', [])
        return spec
    spec = default_specification()
    sizes = raw.get('table_sizes_per_instance') or {}
    if sizes:
        spec['table_sizes'] = dict(sizes)
    deps = raw.get('dependencies') or []
    if deps:
        spec['dependencies'] = deps
    nt = raw.get('null_targets')
    if isinstance(nt, list):
        spec['null_targets'] = [str(x) for x in nt]
    for exc in raw.get('per_column_exceptions') or []:
        cols = exc.get('columns') or []
        tgt = exc.get('targets') or {}
        for c in cols:
            d = spec['columns'].setdefault(_norm_key(c), {'kind': 'text_free'})
            if 'values' in tgt and isinstance(tgt['values'], list):
                vals = [v for v in tgt['values'] if isinstance(v, str)]
                if vals:
                    canon = [v for v in vals if v[:1].isupper()]
                    variants = [v for v in vals if v[:1].islower()]
                    if canon:
                        d['values'] = canon
                    if variants:
                        d['variants'] = variants
            if 'comparison_values' in tgt:
                d['variants'] = list(tgt['comparison_values'])
            if 'duplicate_share' in tgt:
                d['dup_share'] = (0.2, 0.5)
            if 'group_sizes' in tgt:
                d['group_sizes'] = [1, 2, 3]
            if 'null_share' in tgt and 'none' not in str(tgt['null_share']):
                d['null_share'] = (0.05, 0.30)
            if 'qualifying_rows' in tgt or 'distinct_per_group' in tgt:
                d['distinct_per_group'] = 2
            if 'tie_at_rank' in tgt:
                d['tie_at_rank'] = tgt['tie_at_rank']
                d['tie_direction'] = tgt.get('direction', 'DESC')
            if 'direction' in tgt and str(tgt.get('direction')).upper() == 'ASC':
                d['order_asc'] = True
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c = rule.get('table'), rule.get('column')
        f = str(rule.get('formula', ''))
        if not t or not c:
            continue
        d = spec['columns'].setdefault('%s.%s' % (t, c), {'kind': 'text_free'})
        if ' IN (' in f:
            vals = _split_inner(f)
            if vals:
                d['values'] = vals
                d['kind'] = 'text_enum'
                if _is_soft(vals):
                    d['soft'] = True
        if 'BETWEEN' in f.upper():
            try:
                lo = f.upper().index('BETWEEN') + 7
                hi = f.upper().index(' AND ', lo)
                d['min'] = float(f[lo:hi].strip())
                d['max'] = float(f[hi + 5:].strip())
                if _is_soft(None, d['min'], d['max']):
                    d['soft'] = True
            except (ValueError, IndexError):
                pass
    return spec


def column_domain(spec: dict, table: str, column: str) -> dict:
    """Domain descriptor for one column (empty dict when unspecified)."""
    if not spec:
        return {}
    cols = spec.get('columns') or {}
    return cols.get('%s.%s' % (table, column)) or cols.get(column) or {}


def is_null_target(spec: dict, table: str, column: str) -> bool:
    """True when the specification marks this column nullable (NULL rule)."""
    if not spec:
        return False
    nt = spec.get('null_targets') or []
    key = '%s.%s' % (table, column)
    if key in nt or column in nt:
        return True
    d = column_domain(spec, table, column)
    return bool(d.get('null_share'))
