"""Typed literal extraction from construction SQL and routing to columns."""
import re

try:
    import sqlparse
except Exception:  # pragma: no cover
    sqlparse = None

_STR_RE = re.compile(r"'((?:[^']|'')*)'")
_NUM_RE = re.compile(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])')
_IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _unquote(s: str) -> str:
    return s.replace("''", "'")


def extract_typed_values(sql: str):
    """Return a list of (kind, value) literals found in the SQL text."""
    if not isinstance(sql, str):
        raise ValueError('not a string')
    out = []
    masked = sql
    for m in _STR_RE.finditer(sql):
        out.append(('str', _unquote(m.group(1))))
    masked = _STR_RE.sub("''", masked)
    for m in _NUM_RE.finditer(masked):
        tok = m.group(0)
        if '.' in tok:
            try:
                out.append(('float', float(tok)))
            except ValueError:
                pass
        else:
            try:
                out.append(('int', int(tok)))
            except ValueError:
                pass
    return out


def _column_kind(cm) -> str:
    t = (cm.type_str or '').lower()
    if any(k in t for k in ('int', 'number', 'real', 'float', 'double', 'decimal', 'numeric')):
        return 'num'
    return 'text'


def _coerce(kind: str, value, cm):
    """Coerce a literal to the column's declared type; None if incompatible."""
    ck = _column_kind(cm)
    if ck == 'num':
        if kind in ('int', 'float'):
            return int(value) if float(value).is_integer() else float(value)
        try:
            f = float(str(value))
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return None
    if kind == 'str':
        return value
    return str(value)


def seed_literal_pool_from_queries(sqls, schema) -> dict:
    """Route literals of the pool SQLs to (table, column) pools."""
    pool: dict = {}
    all_cols = []
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            all_cols.append((t, cm))
    for sql in sqls:
        try:
            lits = extract_typed_values(sql)
        except Exception:
            continue
        if not lits:
            continue
        idents = {m.group(0).lower() for m in _IDENT_RE.finditer(sql)}
        matched = [(t, cm) for (t, cm) in all_cols if cm.name.lower() in idents]
        targets = matched if matched else all_cols
        for kind, value in lits:
            for (t, cm) in targets:
                v = _coerce(kind, value, cm)
                if v is None:
                    continue
                key = (t, cm.name)
                lst = pool.setdefault(key, [])
                if v not in lst:
                    lst.append(v)
    return pool
