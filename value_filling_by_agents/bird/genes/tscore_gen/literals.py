"""Typed literal extraction from construction SQL (never executed)."""
import re

import sqlparse

_NUM = re.compile(r'^-?\d+(?:\.\d+)?$')
_STR = re.compile(r"^'(.*)'$", re.S)
_IDENT = re.compile(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b')
_TABLE = re.compile(r'\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_]\w*)', re.I)


def _type_literal(tok: str):
    """Return (kind, value) for a literal token."""
    tok = tok.strip()
    m = _STR.match(tok)
    if m:
        return 'str', m.group(1).replace("''", "'")
    if _NUM.match(tok):
        if '.' in tok:
            return 'real', float(tok)
        return 'int', int(tok)
    return None, None


def extract_typed_values(sql: str) -> list:
    """Return a list of (table, column, kind, value) tuples from one SQL statement."""
    out = []
    try:
        stmt = sqlparse.parse(sql)[0]
    except Exception:
        return out
    text = str(stmt)
    for m in re.finditer(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(=|<>|!=|<=|>=|<|>)\s*(\'[^\']*\'|-?\d+(?:\.\d+)?)', text):
        table, col, _op, lit = m.groups()
        kind, val = _type_literal(lit)
        if kind:
            out.append((table, col, kind, val))
    for m in re.finditer(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s+IN\s*\(([^)]*)\)', text, re.I):
        table, col, body = m.groups()
        for lit in re.findall(r"'[^']*'|-?\d+(?:\.\d+)?", body):
            kind, val = _type_literal(lit)
            if kind:
                out.append((table, col, kind, val))
    for m in re.finditer(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s+BETWEEN\s+(\S+)\s+AND\s+(\S+)', text, re.I):
        table, col, lo, hi = m.groups()
        for lit in (lo, hi):
            kind, val = _type_literal(lit)
            if kind:
                out.append((table, col, kind, val))
    for m in re.finditer(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s+LIKE\s+(\'[^\']*\')', text, re.I):
        table, col, lit = m.groups()
        kind, val = _type_literal(lit)
        if kind == 'str':
            out.append((table, col, 'str', val.replace('%', '')))
    return out


def seed_literal_pool_from_queries(sqls: list, schema) -> dict:
    """Build a pool dict {(table, col): [values]} from construction SQL literals."""
    pool: dict = {}
    for sql in sqls:
        try:
            for table, col, _kind, val in extract_typed_values(sql):
                key = (table, col)
                if key in schema.original_values or any(
                        cm.name == col for tm in schema.tables.values() for cm in tm.columns):
                    pool.setdefault(key, [])
                    if val not in pool[key]:
                        pool[key].append(val)
        except Exception:
            continue
    return pool
