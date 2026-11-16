"""Specification loading and per-column exception lookup."""
import json
import os

_DEFAULT = {
    'generic_sampling_rules': {},
    'per_column_exceptions': [],
    'dependencies': [],
    'semantic_rules_and_formulas': [],
    'table_sizes_per_instance': {},
    'null_targets': [],
}


def load_specification(path: str) -> dict:
    """Load specification.json; fall back to an empty spec when absent."""
    if not path or not os.path.exists(path):
        return dict(_DEFAULT)
    try:
        with open(path) as f:
            spec = json.load(f)
    except (OSError, ValueError):
        return dict(_DEFAULT)
    out = dict(_DEFAULT)
    out.update(spec or {})
    return out


def _norm(s: str) -> str:
    return str(s).strip().strip('"`').lower()


def exceptions_for(spec: dict, table: str, column: str) -> list:
    """All per-column exceptions matching table/column (case-insensitive)."""
    t, c = _norm(table), _norm(column)
    out = []
    for ex in spec.get('per_column_exceptions', []) or []:
        if _norm(ex.get('table', '')) == t and _norm(ex.get('column', '')) == c:
            out.append(ex)
    return out


def exception_targets(spec: dict, table: str, column: str, pattern: str) -> list:
    """Targets dicts for a given pattern name on a column."""
    return [ex.get('targets', {}) for ex in exceptions_for(spec, table, column)
            if _norm(ex.get('pattern', '')) == _norm(pattern)]


def table_size(spec: dict, table: str, rng, default: int = 0) -> int:
    """Per-instance TOTAL table size from the spec (compact + appended); jittered by rng."""
    sizes = spec.get('table_sizes_per_instance', {}) or {}
    base = sizes.get(table)
    if base is None:
        for k, v in sizes.items():
            if _norm(k) == _norm(table):
                base = v
                break
    if base is None:
        base = default
    try:
        base = int(base)
    except (TypeError, ValueError):
        base = default
    if base <= 0:
        return 0
    lo = max(0, base - max(2, base // 4))
    hi = base + max(2, base // 4)
    return rng.randint(lo, hi)


def dependencies(spec: dict) -> list:
    """FK dependencies declared in the spec."""
    return list(spec.get('dependencies', []) or [])


def semantic_rules(spec: dict) -> list:
    """Semantic rules/formulas declared in the spec."""
    return list(spec.get('semantic_rules_and_formulas', []) or [])


def null_targets(spec: dict) -> set:
    """Columns explicitly targeted for NULL planting (table.column lowercased)."""
    return {_norm(x) for x in (spec.get('null_targets', []) or [])}


def is_null_target(spec: dict, table: str, column: str) -> bool:
    """True when the column is named in null_targets (table.column)."""
    return _norm(table) + '.' + _norm(column) in null_targets(spec)
