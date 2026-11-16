"""Specification model: value domains, ranges, NULL targets, dependencies, semantic rules."""
import re


DEFAULT_SIZES = {'college': 5, 'member': 10, 'round': 6}


def _norm_col(c: str) -> str:
    return str(c).strip().strip('"`').lower()


def _split_col(c: str):
    """'member.Country' -> ('member', 'Country'); 'Country' -> (None, 'Country')."""
    parts = str(c).split('.')
    if len(parts) >= 2:
        return _norm_col(parts[-2]), parts[-1]
    return None, parts[-1]


def _isnum(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


class Spec:
    """Container for the generation specification (all lookups case-insensitive)."""

    def __init__(self):
        self.sizes = dict(DEFAULT_SIZES)
        self.enums = {}
        self.ranges = {}
        self.literals = {}
        self.null_targets = set()
        self.dup_share = {}
        self.ties = {}
        self.agg_boundary = {}
        self.fresh_share = 0.2
        self.unique_tuples = []
        self.fks = []
        self.rules = []

    def enum(self, t, c):
        return self.enums.get((_norm_col(t), _norm_col(c)))

    def rng(self, t, c):
        return self.ranges.get((_norm_col(t), _norm_col(c)))

    def lits(self, t, c):
        return self.literals.get((_norm_col(t), _norm_col(c)), [])

    def is_null_target(self, t, c):
        return (_norm_col(t), _norm_col(c)) in self.null_targets

    def dup(self, t, c):
        return self.dup_share.get((_norm_col(t), _norm_col(c)))

    def tie_dir(self, t, c):
        return self.ties.get((_norm_col(t), _norm_col(c)))

    def agg(self, t, c):
        return self.agg_boundary.get((_norm_col(t), _norm_col(c)))

    def size(self, t):
        return int(self.sizes.get(t, DEFAULT_SIZES.get(t, 0)))


def _parse_formula(spec: Spec, table: str, col: str, formula: str) -> None:
    """Recognise the small formula language used by the specification."""
    f = formula.strip()
    m = re.fullmatch(r'(\w+)\s*>\s*(-?\d+)', f)
    if m:
        spec.ranges[(table, col)] = (int(m.group(2)) + 1, 10 ** 6)
        return
    m = re.fullmatch(r"(\w+)\s+IN\s*\((.*)\)", f, re.I)
    if m:
        vals = [v.strip().strip("'\"") for v in m.group(2).split(',') if v.strip()]
        spec.enums[(table, col)] = vals
        return
    m = re.fullmatch(r'(\w+)\s+BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', f, re.I)
    if m:
        spec.ranges[(table, col)] = (int(m.group(2)), int(m.group(3)))
        return


def load_specification(raw: dict) -> Spec:
    """Build a Spec from the pipeline's specification.json dict."""
    s = Spec()
    if not isinstance(raw, dict):
        return s
    s.sizes = {str(k): int(v) for k, v in (raw.get('table_sizes_per_instance') or {}).items()} or dict(DEFAULT_SIZES)
    s.fresh_share = float((raw.get('generic_sampling_rules') or {}).get('fresh_values_share', 0.2)
                          if isinstance((raw.get('generic_sampling_rules') or {}).get('fresh_values_share', 0.2),
                                       (int, float)) else 0.2)
    for nt in raw.get('null_targets') or []:
        t, c = _split_col(nt)
        if t:
            s.null_targets.add((t, _norm_col(c)))
    for dep in raw.get('dependencies') or []:
        if 'child_table' in dep:
            s.fks.append((_norm_col(dep['child_table']), _norm_col(dep['child_column']),
                          _norm_col(dep['parent_table']), _norm_col(dep['parent_column'])))
        if 'unique_tuples' in dep:
            for tup in dep['unique_tuples']:
                s.unique_tuples.append((_norm_col(dep['table']), [_norm_col(x) for x in tup]))
    for r in raw.get('semantic_rules_and_formulas') or []:
        _parse_formula(s, _norm_col(r.get('table')), _norm_col(r.get('column')), str(r.get('formula', '')))
    for ex in raw.get('per_column_exceptions') or []:
        t, c = _split_col(ex.get('column', ''))
        if not t:
            continue
        t, c = _norm_col(t), _norm_col(c)
        pat = ex.get('pattern')
        tg = ex.get('targets') or {}
        if pat == 'aggregate_boundary':
            s.agg_boundary[(t, c)] = [int(x) for x in (tg.get('values') or [1, 2, 3])]
        elif pat == 'duplicates_for_distinct':
            share = str(tg.get('duplicate_share', '20-50 %'))
            m = re.findall(r'\d+', share)
            if len(m) >= 2:
                s.dup_share[(t, c)] = (float(m[0]) / 100.0, float(m[1]) / 100.0)
            else:
                s.dup_share[(t, c)] = (0.2, 0.5)
        elif pat == 'ties_for_order_limit':
            s.ties[(t, c)] = str(tg.get('direction', 'ASC')).upper()
        elif pat == 'literal_boundary':
            s.literals[(t, c)] = [int(x) for x in (tg.get('literals') or [])]
        elif pat == 'null_rows':
            if 'none' not in str(tg.get('null_share', '')).lower():
                s.null_targets.add((t, c))
    return s


def spec_from_compact(schema) -> Spec:
    """Fallback spec: sizes from the compact DB, enums/ranges from observed values."""
    s = Spec()
    s.sizes = {t: max(1, int(schema.original_sizes.get(t, 0))) for t in schema.tables}
    for (t, c), vals in schema.original_values.items():
        nn = [v for v in vals if v is not None]
        if not nn:
            continue
        if all(_isnum(v) for v in nn) and len(set(nn)) <= 12:
            lo, hi = int(min(nn)), int(max(nn))
            s.ranges[(t, c)] = (lo, hi)
        elif len(set(nn)) <= 8:
            s.enums[(t, c)] = sorted({str(v) for v in nn})
    for (ct, cc), (pt, pc) in schema.fks.items():
        s.fks.append((_norm_col(ct), _norm_col(cc), _norm_col(pt), _norm_col(pc)))
    for t, tm in schema.tables.items():
        if tm.primary_key:
            s.unique_tuples.append((_norm_col(t), [_norm_col(x) for x in tm.primary_key]))
    return s
