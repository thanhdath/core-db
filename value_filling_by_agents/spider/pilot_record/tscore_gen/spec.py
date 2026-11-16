"""Specification access: per-column domains, ranges, and pattern targets."""
import re


def _norm(spec: dict) -> dict:
    """Normalise the spec into {(table, column): {...}} plus a few helpers."""
    out = {'exceptions': {}, 'sizes': {}, 'generic': {}}
    if not spec:
        return out
    out['generic'] = spec.get('generic_sampling_rules') or {}
    out['sizes'] = spec.get('table_sizes_per_instance') or {}
    for ex in spec.get('per_column_exceptions') or []:
        t = (ex.get('table') or '').lower()
        c = (ex.get('column') or '').lower()
        if t and c:
            out['exceptions'][(t, c)] = ex
    return out


def _int_literal(v):
    """Extract an integer literal from a spec value (200, '2005', '2005 > 2005')."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r'-?\d+', str(v))
    return int(m.group(0)) if m else None


def column_spec(spec: dict, table: str, column: str) -> dict:
    """Return the exception dict for one column (or {})."""
    return _norm(spec)['exceptions'].get((table.lower(), column.lower()), {})


def table_sizes(spec: dict, schema) -> dict:
    """Per-table instance sizes from the spec (fallback to the compact size)."""
    n = _norm(spec)
    out = {}
    for t in schema.tables:
        s = n['sizes'].get(t)
        if isinstance(s, int) and s >= 0:
            out[t] = s
        else:
            out[t] = schema.original_sizes.get(t, 0)
    return out


def int_range(spec: dict, table: str, column: str):
    """(min, max) for an int_range column, or None."""
    ex = column_spec(spec, table, column)
    if ex.get('pattern') != 'int_range':
        return None
    tg = ex.get('targets') or {}
    lo, hi = _int_literal(tg.get('min')), _int_literal(tg.get('max'))
    if lo is None or hi is None:
        return None
    return (min(lo, hi), max(lo, hi))


def int_boundaries(spec: dict, table: str, column: str) -> list:
    """Literal values whose +/-1 must be present (int_range / int_boundary)."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    vals = []
    for b in tg.get('boundary') or []:
        v = _int_literal(b)
        if v is not None:
            vals.append(v)
    return vals


def enum_values(spec: dict, table: str, column: str) -> list:
    """Enum values for a text_enum column."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    vals = tg.get('values')
    if isinstance(vals, list):
        return [v for v in vals if isinstance(v, str)]
    return []


def near_variants(spec: dict, table: str, column: str) -> list:
    """Near-variant text values (case/whitespace)."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    nv = tg.get('near_variants')
    return [v for v in nv if isinstance(v, str)] if isinstance(nv, list) else []


def date_format(spec: dict, table: str, column: str) -> str:
    """Date format for a text_date column (default %Y/%m/%d)."""
    ex = column_spec(spec, table, column)
    if ex.get('pattern') == 'text_date':
        return ex.get('date_format') or '%Y/%m/%d'
    return '%Y/%m/%d'


def duplicate_share(spec: dict, table: str, column: str) -> float:
    """Target duplicate share midpoint (0.35) for distinct_duplicates columns."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    if tg.get('duplicate_share'):
        return 0.35
    return 0.0


def group_size_target(spec: dict, table: str, column: str) -> bool:
    """True if the column must have group sizes 1, 2 and >= 3."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    return 'group_sizes' in tg


def order_ties(spec: dict, table: str, column: str) -> bool:
    """True if the column must have tied values for ORDER BY."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    return 'order_ties' in tg


def unmatched_join(spec: dict, table: str, column: str) -> bool:
    """True if the parent must have at least one childless row."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    return bool(tg.get('unmatched_join_rows'))


def aggregate_boundary(spec: dict, table: str, column: str) -> list:
    """Values of the aggregate boundary (HAVING COUNT(*) ...)."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    vals = tg.get('aggregate_boundary')
    if isinstance(vals, list):
        return [int(v) for v in vals if isinstance(v, (int, float))]
    return []


def pool_size(spec: dict, table: str, column: str) -> int:
    """Distinct pool size for a distinct_duplicates column."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    ps = tg.get('pool_size')
    return int(ps) if isinstance(ps, (int, float)) else 3


def forced_not_null(spec: dict, table: str, column: str) -> bool:
    """True if the spec forces a column NOT NULL (e.g. int_primary_key)."""
    ex = column_spec(spec, table, column)
    tg = ex.get('targets') or {}
    if tg.get('not_null') is True:
        return True
    if ex.get('pattern') in ('primary_key', 'int_primary_key'):
        return True
    return False
