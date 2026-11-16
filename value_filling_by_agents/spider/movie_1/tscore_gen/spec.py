"""Specification loading and per-column exception lookup."""
import json
import re


def _norm_table(t: str) -> str:
    return str(t).strip().strip('"`[]')


def _norm_col(c: str) -> str:
    return str(c).strip().strip('"`[]')


def load_specification(path: str) -> dict:
    """Read specification.json and index per-column exceptions / null targets / sizes."""
    with open(path) as f:
        raw = json.load(f)
    exc: dict = {}
    for e in raw.get('per_column_exceptions', []) or []:
        key = (_norm_table(e.get('table', '')), _norm_col(e.get('column', '')))
        exc.setdefault(key, []).append(e)
    nulls = set()
    for n in raw.get('null_targets', []) or []:
        if isinstance(n, str) and '.' in n:
            t, c = n.split('.', 1)
            nulls.add((_norm_table(t), _norm_col(c)))
    sizes = {}
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            sizes[_norm_table(t)] = int(n)
        except (TypeError, ValueError):
            pass
    deps = []
    for d in raw.get('dependencies', []) or []:
        deps.append(((_norm_table(d.get('table', '')), _norm_col(d.get('column', ''))),
                     (_norm_table(d.get('parent_table', '')), _norm_col(d.get('parent_column', '')))))
    formulas = []
    for f in raw.get('semantic_rules_and_formulas', []) or []:
        formulas.append(((_norm_table(f.get('table', '')), _norm_col(f.get('column', ''))),
                         str(f.get('formula', ''))))
    return {'raw': raw, 'exceptions': exc, 'null_targets': nulls, 'sizes': sizes,
            'dependencies': deps, 'formulas': formulas,
            'generic': raw.get('generic_sampling_rules', {}) or {}}


def spec_from_columns(schema) -> dict:
    """Fallback spec: no exceptions, null targets = nullable columns, sizes = compact sizes."""
    nulls = set()
    for t, tm in schema.tables.items():
        for c in tm.columns:
            if not c.notnull and c.pk_pos == 0:
                nulls.add((t, c.name))
    return {'raw': {}, 'exceptions': {}, 'null_targets': nulls,
            'sizes': dict(schema.original_sizes), 'dependencies': [], 'formulas': [], 'generic': {}}


def exceptions_for(spec: dict, table: str, column: str) -> list:
    """All per-column exception entries for (table, column)."""
    if not spec:
        return []
    return spec.get('exceptions', {}).get((table, column), [])


def has_pattern(spec: dict, table: str, column: str, pattern: str) -> bool:
    """True if the spec lists `pattern` for this column."""
    return any(e.get('pattern') == pattern for e in exceptions_for(spec, table, column))


def pattern_targets(spec: dict, table: str, column: str, pattern: str) -> dict:
    """Merged targets dict for one pattern (first non-empty wins per key)."""
    out: dict = {}
    for e in exceptions_for(spec, table, column):
        if e.get('pattern') == pattern:
            for k, v in (e.get('targets') or {}).items():
                out.setdefault(k, v)
    return out


def is_null_target(spec: dict, table: str, column: str) -> bool:
    """True if the column is a declared NULL target."""
    return bool(spec) and (table, column) in spec.get('null_targets', set())


def formula_for(spec: dict, table: str, column: str) -> str:
    """The semantic formula string for a column ('' if none)."""
    for (t, c), f in (spec or {}).get('formulas', []):
        if t == table and c == column:
            return f
    return ''


def parse_int_range(formula: str):
    """Extract (lo, hi) from 'col BETWEEN a AND b' or 'col > a' / 'col >= a' / 'col < b' / 'col <= b'."""
    if not formula:
        return None
    m = re.search(r'between\s+(-?\d+)\s+and\s+(-?\d+)', formula, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    lo = hi = None
    m = re.search(r'>=\s*(-?\d+)', formula)
    if m:
        lo = int(m.group(1))
    else:
        m = re.search(r'>\s*(-?\d+)', formula)
        if m:
            lo = int(m.group(1)) + 1
    m = re.search(r'<=\s*(-?\d+)', formula)
    if m:
        hi = int(m.group(1))
    else:
        m = re.search(r'<\s*(-?\d+)', formula)
        if m:
            hi = int(m.group(1)) - 1
    if lo is not None or hi is not None:
        return lo, hi
    return None
