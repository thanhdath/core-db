"""Specification loading and per-column pattern lookup."""
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


def _norm_table(t: str) -> str:
    return str(t).strip().strip('"`').lower()


def _norm_col(c: str) -> str:
    return str(c).strip().strip('"`').lower()


def _parse_null_target(x):
    """Accept 'table.column' or [table, column]; return (table, column) or None."""
    if isinstance(x, (list, tuple)) and len(x) == 2:
        return (_norm_table(x[0]), _norm_col(x[1]))
    if isinstance(x, str) and '.' in x:
        t, c = x.rsplit('.', 1)
        return (_norm_table(t), _norm_col(c))
    return None


class Specification:
    """Read-only view of the generation specification."""

    def __init__(self, raw: dict):
        self.raw = raw or {}
        self.generic = self.raw.get('generic_sampling_rules') or {}
        self.sizes = {_norm_table(k): int(v) for k, v in (self.raw.get('table_sizes_per_instance') or {}).items()}
        self.null_targets = set()
        for x in (self.raw.get('null_targets') or []):
            k = _parse_null_target(x)
            if k is not None:
                self.null_targets.add(k)
        self.exceptions: dict = {}
        for ex in self.raw.get('per_column_exceptions') or []:
            key = (_norm_table(ex.get('table', '')), _norm_col(ex.get('column', '')))
            self.exceptions.setdefault(key, []).append(ex)
        self.formulas: dict = {}
        for f in self.raw.get('semantic_rules_and_formulas') or []:
            key = (_norm_table(f.get('table', '')), _norm_col(f.get('column', '')))
            self.formulas.setdefault(key, []).append(str(f.get('formula', '')))
        self.deps: dict = {}
        for d in self.raw.get('dependencies') or []:
            key = (_norm_table(d.get('child_table', '')), _norm_col(d.get('child_column', '')))
            self.deps.setdefault(key, []).append(d)

    def patterns(self, table: str, column: str) -> list:
        """Exception dicts for (table, column)."""
        return self.exceptions.get((_norm_table(table), _norm_col(column)), [])

    def has_pattern(self, table: str, column: str, pattern: str) -> bool:
        return any(p.get('pattern') == pattern for p in self.patterns(table, column))

    def pattern_targets(self, table: str, column: str, pattern: str) -> dict:
        for p in self.patterns(table, column):
            if p.get('pattern') == pattern:
                return p.get('targets') or {}
        return {}

    def column_formulas(self, table: str, column: str) -> list:
        return self.formulas.get((_norm_table(table), _norm_col(column)), [])

    def table_size(self, table: str, default: int) -> int:
        return self.sizes.get(_norm_table(table), default)

    def is_null_target(self, table: str, column: str) -> bool:
        return (_norm_table(table), _norm_col(column)) in self.null_targets


def load_specification(path: str) -> Specification:
    """Load specification.json; missing file -> empty specification (generic rules only)."""
    raw = dict(_DEFAULT)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                raw.update(loaded)
        except (OSError, ValueError):
            pass
    return Specification(raw)
