"""Specification loading and per-column sampling plans (implemented by construction in the samplers)."""
import re

DEFAULT_NULL_SHARE = 0.0
DEFAULT_TABLE_SIZES = {'Investors': 20, 'Lots': 15, 'Ref_Transaction_Types': 2, 'Transactions': 15,
                       'Sales': 15, 'Purchases': 15, 'Transactions_Lots': 15}
AMOUNT_BOUNDARIES = [99.9999, 100.0, 100.0001, 2998.9999, 2999.0, 2999.0001, 2999.9999, 3000.0, 3000.0001]
SHARE_BOUNDARIES = ['-12', '-11', '-10', '9', '10', '11', '99', '100', '101', '102']
ENUM_TYPES = ['PUR', 'SALE']
ENUM_DESCRIPTIONS = ['Sale', 'Purchase']


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _col_plan(declared_type: str) -> dict:
    t = (declared_type or '').lower()
    if 'int' in t:
        return {'kind': 'int'}
    if any(k in t for k in ('decimal', 'numeric', 'real', 'float', 'double')):
        return {'kind': 'decimal'}
    if 'date' in t or 'time' in t:
        return {'kind': 'datetime'}
    return {'kind': 'string'}


def _apply_exception(plan: dict, exc: dict) -> None:
    """Fold one per_column_exceptions entry into a column plan."""
    pat = exc.get('pattern', '')
    targets = exc.get('targets') or []
    if pat == 'enum':
        plan['enum'] = [str(x) for x in targets]
        plan['kind'] = 'string'
    elif pat == 'enum_and_comparison_boundary':
        plan['enum'] = [str(x) for x in targets]
        plan['boundaries'] = [str(x) for x in targets]
        plan['kind'] = 'string'
    elif pat == 'comparison_boundary':
        plan['boundaries'] = list(targets)
    elif pat == 'duplicates_for_distinct':
        plan['duplicate_share'] = (0.2, 0.5)
    elif pat in ('group_sizes_and_ties', 'group_sizes', 'group_sizes_and_unmatched'):
        plan['group_sizes'] = True
    elif pat == 'unmatched_join_rows':
        plan['parent_rows_without_children'] = True


def load_spec(raw: dict) -> dict:
    """Translate a specification dict into {table: {column: plan}} plus table sizes and null targets."""
    out = {'columns': {}, 'sizes': dict(DEFAULT_TABLE_SIZES), 'null_targets': set()}
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            out['sizes'][t] = int(n)
        except (TypeError, ValueError):
            pass
    for nt in raw.get('null_targets') or []:
        if '.' in nt:
            out['null_targets'].add(tuple(nt.split('.', 1)))
    for exc in raw.get('per_column_exceptions') or []:
        t, c = exc.get('table'), exc.get('column')
        if not t or not c:
            continue
        plan = out['columns'].setdefault(t, {}).setdefault(c, {})
        _apply_exception(plan, exc)
    for t in ('Transactions', 'Ref_Transaction_Types'):
        p = out['columns'].setdefault(t, {}).setdefault('transaction_type_code', {})
        p['enum'] = list(ENUM_TYPES)
        p['kind'] = 'string'
        p.pop('boundaries', None)
    return out


def spec_from_schema(schema) -> dict:
    """Fallback specification derived from the schema when no specification.json is present."""
    out = {'columns': {}, 'sizes': {}, 'null_targets': set()}
    for t, tm in schema.tables.items():
        out['sizes'][t] = max(1, min(20, schema.original_sizes.get(t, 15) or 15))
        for cm in tm.columns:
            plan = _col_plan(cm.type_str)
            if not cm.notnull and cm.pk_pos == 0:
                out['null_targets'].add((t, cm.name))
            out['columns'].setdefault(t, {})[cm.name] = plan
    for t, c, vals in (('Ref_Transaction_Types', 'transaction_type_code', ENUM_TYPES),
                       ('Ref_Transaction_Types', 'transaction_type_description', ENUM_DESCRIPTIONS),
                       ('Transactions', 'transaction_type_code', ENUM_TYPES)):
        if t in out['columns'] and c in out['columns'][t]:
            out['columns'][t][c]['enum'] = list(vals)
    if 'Transactions' in out['columns']:
        tc = out['columns']['Transactions']
        if 'amount_of_transaction' in tc:
            tc['amount_of_transaction']['boundaries'] = list(AMOUNT_BOUNDARIES)
        if 'share_count' in tc:
            tc['share_count']['boundaries'] = list(SHARE_BOUNDARIES)
    return out


def column_plan(spec: dict, table: str, column: str, declared_type: str) -> dict:
    """Merged plan for one column: declared-type kind + specification exceptions."""
    plan = _col_plan(declared_type)
    plan.update((spec.get('columns') or {}).get(table, {}).get(column, {}))
    return plan


def table_size(spec: dict, table: str, rng) -> int:
    """Per-instance table size: specification size with a small random jitter (0-230 rows)."""
    base = int((spec.get('sizes') or {}).get(table, DEFAULT_TABLE_SIZES.get(table, 15)))
    if base <= 0:
        return 0
    jitter = rng.randint(-2, 2)
    return max(0, min(230, base + jitter))


def null_share(spec: dict, table: str, column: str, observed: float, n_rows: int = 1) -> float:
    """NULL share for a nullable column: compact share, at least one NULL row per instance."""
    if (table, column) not in (spec.get('null_targets') or set()):
        return 0.0
    if observed and observed > 0:
        return max(0.0, min(0.5, observed))
    return max(1.0 / max(1, n_rows), DEFAULT_NULL_SHARE)


def _is_num(x) -> bool:
    return _num(x) is not None


def coerce_boundary(value, kind: str):
    """Type a boundary literal for the column kind (numbers stay numbers, strings stay strings)."""
    if kind == 'decimal':
        n = _num(value)
        return n if n is not None else value
    if kind == 'int':
        n = _num(value)
        return int(n) if n is not None else value
    return str(value)


def boundary_values(plan: dict, kind: str) -> list:
    """Typed boundary values for a column plan."""
    out = []
    for v in plan.get('boundaries') or []:
        out.append(coerce_boundary(v, kind))
    return out


def enum_values(plan: dict) -> list:
    return [str(v) for v in plan.get('enum') or []]


def like_patterns(values: list) -> list:
    """LIKE patterns without '%' plus prefix/suffix variants (used for string pools)."""
    out = []
    for v in values:
        s = str(v)
        if not s:
            continue
        out.append(s)
        if len(s) > 1:
            out.append(s[:-1])
            out.append(s[1:])
        out.append(s + 'x')
        out.append('x' + s)
    return out


def numeric_variants(values: list, kind: str) -> list:
    """Numbers +-1 / +-2 around each pool value (perturbations)."""
    out = []
    for v in values:
        n = _num(v)
        if n is None:
            continue
        for d in (-2, -1, 1, 2):
            x = n + d
            if kind == 'int':
                out.append(int(round(x)))
            else:
                out.append(round(x, 4))
    return out


def string_variants(values: list) -> list:
    """Prefix / suffix / dropped-character variants and case flips for string pools."""
    out = []
    for v in values:
        s = str(v)
        if not s:
            continue
        out.append(s)
        out.append(s.upper())
        out.append(s.lower())
        out.append(s + 'a')
        out.append('a' + s)
        if len(s) > 1:
            out.append(s[:-1])
            out.append(s[1:])
    return out


def _unused(_x):
    return re.sub(r'\s+', ' ', str(_x))
