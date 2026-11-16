"""Specification loading and normalisation (tscore_gen/specification.json)."""
import re

_NUM = re.compile(r'-?\d+(?:\.\d+)?')
_QUOTED = re.compile(r"'([^']*)'")


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_boundary_targets(targets) -> list:
    """Extract numeric literals from a comparison_boundary target description."""
    out = []
    if isinstance(targets, dict):
        for v in _as_list(targets.get('values')):
            n = _num(v)
            if n is not None:
                out.append(n)
    elif isinstance(targets, str):
        for m in _NUM.finditer(targets):
            out.append(float(m.group(0)))
    return out


def _parse_string_targets(targets) -> list:
    """Extract quoted string literals from a target description."""
    out = []
    if isinstance(targets, str):
        for m in _QUOTED.finditer(targets):
            out.append(m.group(1))
    elif isinstance(targets, dict):
        for v in _as_list(targets.get('values')):
            if isinstance(v, str):
                out.append(v)
    return out


def _parse_relative_pairs(targets) -> list:
    """Parse 'equal to and one step (0.1) from Jul and Oct' -> [(column, step), ...]."""
    out = []
    if not isinstance(targets, str):
        return out
    m = re.search(r'one step \(([\d.]+)\) from\s+(.+?)(?:;|$)', targets, re.I)
    if not m:
        return out
    step = float(m.group(1))
    cols = re.findall(r'([A-Z][a-z]+)', m.group(2))
    for c in cols:
        out.append((c, step))
    return out


def load_specification(raw: dict) -> dict:
    """Normalise the JSON specification into sampler-friendly structures."""
    spec = {'table_sizes': {}, 'null_targets': set(), 'exceptions': {},
            'dependencies': [], 'formulas': [], 'literal_pool': {},
            'boundary_pairs': {}, 'duplicate_targets': {}, 'group_targets': {},
            'raw': raw}
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            spec['table_sizes'][t] = int(n)
        except (TypeError, ValueError):
            pass
    for nt in _as_list(raw.get('null_targets')):
        if isinstance(nt, str) and '.' in nt:
            t, c = nt.split('.', 1)
            spec['null_targets'].add((t, c))
    for dep in _as_list(raw.get('dependencies')):
        try:
            spec['dependencies'].append((dep['child_table'], dep['child_column'],
                                         dep['parent_table'], dep['parent_column']))
        except (KeyError, TypeError):
            pass
    for exc in _as_list(raw.get('per_column_exceptions')):
        t, c = exc.get('table'), exc.get('column')
        if not t or not c:
            continue
        spec['exceptions'].setdefault((t, c), []).append(exc)
        pat = exc.get('pattern', '')
        tg = exc.get('targets')
        if pat == 'comparison_boundary':
            nums = _parse_boundary_targets(tg)
            strs = _parse_string_targets(tg)
            if nums:
                spec['literal_pool'].setdefault((t, c), []).extend(str(n) for n in nums)
            if strs:
                spec['literal_pool'].setdefault((t, c), []).extend(strs)
            pairs = _parse_relative_pairs(tg)
            if pairs:
                spec['boundary_pairs'].setdefault((t, c), []).extend(pairs)
        elif pat == 'duplicates_for_distinct':
            m = re.search(r'(\d+)\s*-\s*(\d+)\s*%', str(tg))
            if m:
                spec['duplicate_targets'][(t, c)] = (int(m.group(1)) / 100.0, int(m.group(2)) / 100.0)
            else:
                spec['duplicate_targets'][(t, c)] = (0.2, 0.5)
        elif pat == 'group_sizes':
            spec['group_targets'][(t, c)] = [1, 2, 3]
    for f in _as_list(raw.get('semantic_rules_and_formulas')):
        t, c, formula = f.get('table'), f.get('column'), f.get('formula', '')
        if not t or not c:
            continue
        spec['formulas'].append((t, c, _classify_formula(formula), formula))
    return spec


def _classify_formula(formula: str) -> str:
    """Classify a formula string into a construction kind."""
    f = (formula or '').strip()
    low = f.lower()
    if 'between' in low:
        return 'between'
    if re.search(r'>\s*0\b', f) and not re.search(r'>=', f):
        return 'positive'
    if re.search(r'>=\s*0\b', f):
        return 'nonnegative'
    return 'other'


def spec_from_columns(schema) -> dict:
    """Fallback specification derived from the compact schema when no JSON is present."""
    spec = {'table_sizes': {}, 'null_targets': set(), 'exceptions': {},
            'dependencies': [], 'formulas': [], 'literal_pool': {},
            'boundary_pairs': {}, 'duplicate_targets': {}, 'group_targets': {},
            'raw': {}}
    for t, tm in schema.tables.items():
        spec['table_sizes'][t] = max(1, schema.original_sizes.get(t, 0))
        for cm in tm.columns:
            if not cm.notnull and cm.pk_pos == 0:
                spec['null_targets'].add((t, cm.name))
    for (ct, cc), (pt, pc) in schema.fks.items():
        spec['dependencies'].append((ct, cc, pt, pc))
    return spec
