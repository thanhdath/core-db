"""Specification model: value pools, ranges, enums, NULL targets, dependencies, formulas."""
import datetime as dt
import re
from dataclasses import dataclass, field

_DT_FMT = '%Y-%m-%d %H:%M:%S'


def parse_dt(s):
    """Parse a specification timestamp (tolerant of the ':18' shorthand)."""
    if s is None:
        return None
    if isinstance(s, dt.datetime):
        return s
    s = str(s).strip()
    for f in (_DT_FMT, '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$', s)
    if m:
        return dt.datetime(*[int(x) for x in m.groups()])
    return None


def fmt_dt(d):
    """Format a datetime the way the compact database does."""
    return d.strftime(_DT_FMT)


@dataclass
class ColumnSpec:
    table: str
    column: str
    pattern: str = ''
    targets: list = field(default_factory=list)


@dataclass
class Formula:
    table: str
    column: str
    text: str
    kind: str = ''
    left: str = ''
    right: str = ''
    values: list = field(default_factory=list)


@dataclass
class Specification:
    sizes: dict = field(default_factory=dict)
    exceptions: dict = field(default_factory=dict)
    null_targets: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    formulas: list = field(default_factory=list)
    generic: dict = field(default_factory=dict)

    def exc(self, table, column):
        return self.exceptions.get((table, column))

    def is_null_target(self, table, column):
        return (table, column) in set(self.null_targets)

    def formulas_for(self, table, column):
        return [f for f in self.formulas if f.table == table and f.column == column]


def _split_col(s):
    s = str(s).strip()
    if '.' in s:
        t, c = s.split('.', 1)
        return t.strip(), c.strip()
    return '', s


def _parse_formula(table, column, text):
    """Classify a formula text into a small Python-checkable kind."""
    t = str(text).strip()
    m = re.match(r'^(\w+)\s*>=\s*(\w+)$', t)
    if m:
        return Formula(table, column, t, 'ge', m.group(1), m.group(2))
    m = re.match(r"^(\w+)\s+IN\s*\((.*)\)$", t, re.I)
    if m:
        vals = [x.strip().strip("'\"") for x in m.group(2).split(',') if x.strip()]
        return Formula(table, column, t, 'in', m.group(1), '', vals)
    return Formula(table, column, t, 'other')


def spec_from_dict(d: dict) -> Specification:
    """Build a Specification from the pipeline's specification.json dict."""
    sp = Specification()
    if not d:
        return sp
    sp.generic = d.get('generic_sampling_rules') or {}
    sp.sizes = {k: int(v) for k, v in (d.get('table_sizes_per_instance') or {}).items()}
    for e in d.get('per_column_exceptions') or []:
        t, c = e.get('table'), e.get('column')
        if not t or not c:
            continue
        sp.exceptions[(t, c)] = ColumnSpec(t, c, e.get('pattern', ''), list(e.get('targets') or []))
    for n in d.get('null_targets') or []:
        t, c = _split_col(n)
        if t:
            sp.null_targets.append((t, c))
    for dep in d.get('dependencies') or []:
        ch, pa = dep.get('child'), dep.get('parent')
        if ch and pa:
            ct, cc = _split_col(ch)
            pt, pc = _split_col(pa)
            sp.dependencies.append(((ct, cc), (pt, pc)))
    for f in d.get('semantic_rules_and_formulas') or []:
        t, c = f.get('table'), f.get('column')
        if t and c:
            sp.formulas.append(_parse_formula(t, c, f.get('formula', '')))
    return sp


def load_specification(path: str) -> Specification:
    """Load specification.json from disk (empty spec if missing)."""
    import json
    import os
    if not path or not os.path.exists(path):
        return Specification()
    with open(path) as f:
        return spec_from_dict(json.load(f))


def formula_holds(f: Formula, row: dict):
    """SQL three-valued logic: a rule holds when its expression is not FALSE."""
    if f.kind == 'ge':
        a, b = row.get(f.left), row.get(f.right)
        if a is None or b is None:
            return True
        try:
            return a >= b
        except TypeError:
            return True
    if f.kind == 'in':
        v = row.get(f.left)
        if v is None:
            return True
        return v in f.values
    return True
