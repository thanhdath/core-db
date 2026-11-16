"""Specification loading and literal routing (generation specification -> value pools)."""
import json
import re


_NUM = re.compile(r'-?\d+(?:\.\d+)?')
_TS = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _split_col(name: str) -> tuple:
    parts = name.split('.')
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[-1]


def _as_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str) and _NUM.fullmatch(v.strip()):
        return float(v) if '.' in v else int(v)
    return None


def _variants_of(literal: str) -> list:
    """Near-variants named by the specification."""
    out = []
    if not literal:
        return out
    last = literal[-1]
    out.append(literal[:-1] + ('t' if last != 't' else 's'))
    out.append(literal + 'x')
    out.append(literal + ' x')
    out.append(literal.lower())
    if _TS.match(literal):
        import datetime as _dt
        try:
            d = _dt.datetime.strptime(literal, '%Y-%m-%d %H:%M:%S')
            out.append((d + _dt.timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'))
            out.append((d - _dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass
    return out


def _parse_targets(text: str) -> list:
    """Pull quoted literals and bare numbers out of a target description."""
    vals = []
    for m in re.finditer(r"'((?:[^']|'')*)'", text):
        vals.append(m.group(1).replace("''", "'"))
    for m in re.finditer(r'(?<![\w.\'-])-?\d+(?:\.\d+)?(?![\w.\'])', text):
        vals.append(m.group(0))
    return vals


def _is_int_column(column: str) -> bool:
    low = (column or '').lower()
    return any(k in low for k in ('int', 'num', 'score', 'year', 'id'))


def _parse_targets_for(text: str, column: str) -> list:
    """Target parsing aware of the column type."""
    quoted = [m.group(1).replace("''", "'") for m in re.finditer(r"'((?:[^']|'')*)'", text)]
    bare = [m.group(0) for m in re.finditer(r'(?<![\w.\'-])-?\d+(?:\.\d+)?(?![\w.\'])', text)]
    low = (column or '').lower()
    if 'date' in low or 'timestamp' in low or 'time' in low:
        return [q for q in quoted if _DATE.match(q) or _TS.match(q)]
    if _is_int_column(column):
        out = [q for q in quoted if _NUM.fullmatch(q.strip())]
        out += bare
        return out
    return quoted + bare


def load_specification(path: str) -> dict:
    """Read the specification and pre-compute per-column pools/policies."""
    with open(path) as f:
        raw = json.load(f)
    pools: dict = {}
    policies: dict = {}
    boundary: dict = {}
    for exc in raw.get('per_column_exceptions', []) or []:
        col = exc.get('column')
        if not col:
            continue
        t, c = _split_col(col)
        key = (t, c)
        pat = exc.get('pattern')
        targets = exc.get('targets') or ''
        vals = _parse_targets_for(targets, c)
        if pat in ('comparison_boundary', 'like_near_variant'):
            pools.setdefault(key, [])
            for v in vals:
                if v not in pools[key]:
                    pools[key].append(v)
            if pat == 'like_near_variant' and not _is_int_column(c):
                for v in list(vals):
                    for w in _variants_of(v):
                        if w not in pools[key]:
                            pools[key].append(w)
            if pat == 'comparison_boundary':
                boundary.setdefault(key, [])
                for v in vals:
                    if v not in boundary[key]:
                        boundary[key].append(v)
            policies.setdefault(key, {})[pat] = vals
        elif pat in ('null_rows', 'null_in_count_column'):
            policies.setdefault(key, {})[pat] = targets
        elif pat in ('duplicates_for_distinct', 'ties_for_order_limit', 'rows_with_different_values'):
            policies.setdefault(key, {})[pat] = targets
    rules = []
    for r in raw.get('semantic_rules_and_formulas', []) or []:
        rules.append(r)
    sizes = raw.get('table_sizes_per_instance', {}) or {}
    null_targets = raw.get('null_targets', []) or []
    return {'pools': pools, 'policies': policies, 'rules': rules, 'sizes': sizes,
            'null_targets': null_targets, 'boundary': boundary, 'raw': raw}


def spec_pool_literals(spec: dict, schema) -> dict:
    """Route specification literals to concrete (table, column) keys of the schema."""
    out: dict = {}
    if not spec:
        return out
    for (t, c), vals in (spec.get('pools') or {}).items():
        keys = []
        if t is not None:
            for tn, tm in schema.tables.items():
                if tn.lower() == t.lower():
                    for cm in tm.columns:
                        if cm.name.lower() == c.lower():
                            keys.append((tn, cm.name))
        if not keys:
            for tn, tm in schema.tables.items():
                for cm in tm.columns:
                    if cm.name.lower() == c.lower():
                        keys.append((tn, cm.name))
        for k in keys:
            out.setdefault(k, [])
            for v in vals:
                if v not in out[k]:
                    out[k].append(v)
    return out


def boundary_literals(spec: dict, table: str, column: str) -> list:
    """Exact comparison-boundary literals for a column (for seeding and feedback)."""
    if not spec:
        return []
    for (t, c), vals in (spec.get('boundary') or {}).items():
        if c.lower() != column.lower():
            continue
        if t is None or t.lower() == table.lower():
            return list(vals)
    return []


def seed_parent_keys(spec: dict, schema) -> dict:
    """Boundary literals that must be planted in parent tables so FK boundaries are realizable."""
    out: dict = {}
    if not spec:
        return out
    for (t, c), vals in (spec.get('boundary') or {}).items():
        if t is None:
            continue
        child = None
        for tn, tm in schema.tables.items():
            if tn.lower() != t.lower():
                continue
            for cm in tm.columns:
                if cm.name.lower() == c.lower():
                    child = (tn, cm.name)
        if child is None:
            continue
        parent = schema.fks.get(child)
        if parent is None:
            continue
        out.setdefault(parent, [])
        for v in vals:
            if v not in out[parent]:
                out[parent].append(v)
    return out


def policy_for(spec: dict, table: str, column: str) -> dict:
    """Policies for a column, tolerant to table-name case."""
    if not spec:
        return {}
    pol = spec.get('policies') or {}
    for (t, c), p in pol.items():
        if c.lower() != column.lower():
            continue
        if t is None or t.lower() == table.lower():
            return p
    return {}


def null_share_for(spec: dict, table: str, column: str, default: float) -> float:
    """NULL share from the specification (5-30 % / 20-50 % ranges -> midpoint)."""
    p = policy_for(spec, table, column)
    txt = p.get('null_rows') or p.get('null_in_count_column') or ''
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*%', txt)
    if m:
        return (int(m.group(1)) + int(m.group(2))) / 200.0
    return default


def duplicate_share_for(spec: dict, table: str, column: str, default: float) -> float:
    p = policy_for(spec, table, column)
    txt = p.get('duplicates_for_distinct') or ''
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*%', txt)
    if m:
        return (int(m.group(1)) + int(m.group(2))) / 200.0
    return default


def tie_target_for(spec: dict, table: str, column: str) -> bool:
    p = policy_for(spec, table, column)
    return 'ties_for_order_limit' in p


def different_values_for(spec: dict, table: str, column: str) -> bool:
    p = policy_for(spec, table, column)
    return 'rows_with_different_values' in p
