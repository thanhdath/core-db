"""Specification model: value domains, NULL shares, dependencies and semantic rules."""
import re

DEFAULT_NULL_SHARE = 0.10
DEFAULT_DUP_SHARE = 0.30
DEFAULT_GROUP_SIZES = (1, 2, 3)
DEFAULT_AGG_VALUES = (0, 1, 2, 3)

LIKE_BY_COLUMN = {
    'name': (['%Swif%'], ['Swif', 'Swif x', 'SWIF', 'Swift', 'Swiftt']),
    'email': (['%edu%', '%supers%'], ['edu', 'edux', 'EDU', 'supers', 'supersx', 'SUPERS']),
    'text': (['%int%', '%intern%'], ['int', 'inu', 'int x', 'INT', 'intern', 'intero', 'intern x', 'INTERN']),
}

BOUNDARY_BY_COLUMN = {
    'followers': [999, 1000, 1001],
    'f2': [-1, 1],
    'name': ['Iron Man', 'Iron Man ', 'Iron-Man', 'Iron Manx'],
}

DOMAIN_BY_COLUMN = {
    'f2': [-1, 1],
}

AGG_AS_CHILD_COUNT = {('tweets', 'id'), ('user_profiles', 'uid'), ('tweets', 'uid')}


def _norm_col(name: str) -> str:
    return str(name).strip().strip('`"').lower()


def _split_table_col(key: str):
    if '.' in key:
        t, c = key.split('.', 1)
        return _norm_col(t), _norm_col(c)
    return None, _norm_col(key)


def _parse_dt(s: str):
    """Parse a datetime literal from a formula; returns datetime or None."""
    import datetime as dt
    s = str(s).strip().strip("'\"")
    for t in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None


def load_specification(raw: dict) -> dict:
    """Normalise a specification.json (or the embedded spec dict) into sampler parameters."""
    spec = {
        'null_share': {},
        'dup_share': {},
        'group_sizes': {},
        'agg_values': {},
        'like_literals': {},
        'like_variants': {},
        'comparison_boundary': {},
        'domain': {},
        'formulas': {},
        'date_range': {},
        'date_range_soft': set(),
        'table_sizes': {},
        'ties_order': {},
        'rows_diff_values': {},
        'unmatched_parents': set(),
        'nullable': set(),
        'raw': raw,
    }
    if not isinstance(raw, dict):
        return spec
    for c in raw.get('null_targets') or []:
        t, col = _split_table_col(c)
        spec['nullable'].add((t, col))
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        spec['table_sizes'][_norm_col(t)] = int(n)
    for ex in raw.get('per_column_exceptions') or []:
        t = _norm_col(ex.get('table', ''))
        c = _norm_col(ex.get('column', ''))
        pat = ex.get('pattern', '')
        if pat == 'group_sizes':
            spec['group_sizes'][(t, c)] = DEFAULT_GROUP_SIZES
        elif pat == 'aggregate_boundary':
            spec['agg_values'][(t, c)] = DEFAULT_AGG_VALUES
        elif pat == 'duplicates_for_distinct':
            spec['dup_share'][(t, c)] = 0.30
        elif pat == 'unmatched_join_rows':
            spec['unmatched_parents'].add((t, c))
        elif pat == 'rows_with_different_values':
            spec['rows_diff_values'][(t, c)] = True
        elif pat == 'ties_for_order_limit':
            spec['ties_order'][(t, c)] = 'asc'
        elif pat == 'comparison_boundary':
            spec['comparison_boundary'][(t, c)] = list(BOUNDARY_BY_COLUMN.get(c, [-1, 0, 1]))
        elif pat == 'like_near_variant':
            lits, vars_ = LIKE_BY_COLUMN.get(c, (['%int%', '%intern%'],
                                                 ['int', 'inu', 'int x', 'INT', 'intern', 'intero', 'intern x', 'INTERN']))
            spec['like_literals'][(t, c)] = list(lits)
            spec['like_variants'][(t, c)] = list(vars_)
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t = _norm_col(rule.get('table', ''))
        c = _norm_col(rule.get('column', ''))
        f = rule.get('formula', '')
        if f:
            spec['formulas'][(t, c)] = f
    for (t, c) in list(spec['formulas']):
        if c in DOMAIN_BY_COLUMN:
            spec['domain'][(t, c)] = list(DOMAIN_BY_COLUMN[c])
        if c in BOUNDARY_BY_COLUMN:
            spec['comparison_boundary'].setdefault((t, c), list(BOUNDARY_BY_COLUMN[c]))
    for (t, c), f in list(spec['formulas'].items()):
        m = re.search(r">=\s*'([^']+)'.*?<\s*'([^']+)'", f)
        if m:
            lo, hi = _parse_dt(m.group(1)), _parse_dt(m.group(2))
            if lo is not None and hi is not None:
                spec['date_range'][(t, c)] = (lo, hi)
                if 'uncertain' in str(raw.get('uncertainty', '')).lower() and c == 'createdate':
                    spec['date_range_soft'].add((t, c))
    return spec


def spec_from_columns(stats: dict) -> dict:
    """Fallback: derive a minimal spec from column statistics (no per-column exceptions)."""
    return load_specification({'table_sizes_per_instance': {}, 'per_column_exceptions': [],
                               'semantic_rules_and_formulas': [], 'null_targets': []})


def formula_kind(formula: str) -> str:
    """Classify a formula string into a sampler constraint kind."""
    f = (formula or '').lower()
    if 'is not null or' in f:
        return 'nullable'
    if re.search(r'>=\s*\'', f) and re.search(r'<\s*\'', f):
        return 'between'
    if re.search(r'>\s*0', f):
        return 'positive'
    if re.search(r'>=\s*0', f):
        return 'nonneg'
    if re.search(r'<>\s*0', f):
        return 'nonzero'
    if 'length(' in f and '<=' in f:
        return 'maxlen'
    return 'none'


def maxlen_of(formula: str, default: int = 140) -> int:
    m = re.search(r'<=\s*(\d+)', formula or '')
    return int(m.group(1)) if m else default
