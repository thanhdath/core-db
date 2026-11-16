"""Typed literal extraction from pool SQL (never executed) and pool seeding."""
import re

import sqlparse

_NUM = re.compile(r'^-?\d+(\.\d+)?$')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}:\d{2})?$')


def _typed(tok: str):
    """Return (kind, value) for a literal token."""
    t = tok.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        inner = t[1:-1]
        if _DATE.match(inner):
            return ('datetime', inner)
        if _NUM.match(inner):
            return ('number', inner)
        return ('string', inner)
    if _NUM.match(t):
        return ('number', t)
    return ('string', t)


def extract_typed_values(sql: str):
    """Extract comparison / IN / BETWEEN / LIKE literals as typed values."""
    out = []
    try:
        stmts = sqlparse.parse(sql)
    except Exception:
        return out
    for st in stmts:
        for tok in st.flatten():
            if tok.ttype is not None and 'Literal' in str(tok.ttype):
                kind, val = _typed(tok.value)
                out.append((kind, val))
    return out


def seed_literal_pool_from_queries(sqls, schema):
    """Route typed literals to columns by name heuristics; return {table: {col: [values]}}."""
    pool = {}
    for s in sqls:
        for kind, val in extract_typed_values(s):
            for tn, t in schema.tables.items():
                for c in t.columns:
                    if re.search(r'\b%s\b' % re.escape(c.name), s, re.I):
                        pool.setdefault(tn, {}).setdefault(c.name, [])
                        if val not in pool[tn][c.name]:
                            pool[tn][c.name].append(val)
    return pool
