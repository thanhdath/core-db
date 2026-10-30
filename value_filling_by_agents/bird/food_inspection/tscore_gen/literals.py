"""Literal extraction and typing (sql_util/parse.py:146-253, sql_util/value_typing.py:1-75)."""
import re

import sqlparse
from sqlparse import tokens as T
from sqlparse.sql import Comparison, Identifier

_PH = 'placeholderrare'
_ITEM = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[^,\s]+")
_VAL = r"('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|-?\d+(?:\.\d+)?)"
_COL = r'((?:[`"]?[\w -]+?[`"]?\.)*[`"]?[\w-]+[`"]?)'
_IN = re.compile(_COL + r'\s*\)?\s+(?:not\s+)?in\s*\(([^()]*)\)', re.I)
_BETWEEN = re.compile(_COL + r'\s*\)?\s+(?:not\s+)?between\s+' + _VAL + r'\s+and\s+' + _VAL, re.I)
_CMP = re.compile(_COL + r'\s*\)?\s*(?:<>|!=|>=|<=|==|=|>|<|\s(?:not\s+)?like\s)\s*' + _VAL, re.I)
_QUAL = re.compile(r'^[`"]?[A-Za-z_][\w$]*[`"]?$')
_PLAIN_COL = re.compile(r'^[`"]?[A-Za-z_][\w$]*[`"]?(\.[`"]?[A-Za-z_][\w$]*[`"]?)?$')


def _unquote(v: str) -> str:
    """Strip surrounding quotes, collapse doubled quotes (parse.py:246-253)."""
    v = v.strip().rstrip(';')
    if len(v) >= 2 and v[0] in '\'"' and v[-1] == v[0]:
        v = v[1:-1].replace(v[0] * 2, v[0])
    return v.replace(_PH, '')


def _raw_unquote(v: str) -> str:
    """Strip surrounding quotes but KEEP doubled quotes (upstream parse.py:246-253 keeps them)."""
    v = v.strip().rstrip(';')
    if len(v) >= 2 and v[0] in '\'"' and v[-1] == v[0]:
        v = v[1:-1]
    return v.replace(_PH, '')


def _split_cols(name: str) -> list:
    """Column key plus tolerant table variants: (table, COL), (raw qualifier, COL), (None, COL)."""
    raw = name.strip().split('.')
    parts = [p.replace('"', '').replace('`', '').strip() for p in raw]
    col = parts[-1].upper().replace(_PH.upper(), '')
    if len(parts) == 1:
        return [(None, col)]
    tab = parts[-2].lower()
    out = []
    if not re.fullmatch(r't\d+', tab):
        out.append((tab, col))
        rq = raw[-2].strip().lower()
        if rq != tab:
            out.append((rq, col))
    out.append((None, col))
    return out


def _plain_column_name(tok):
    """Return the column reference text if tok is a plain (optionally qualified) column, else None.
    Upstream parse.py extract_typed_value_in_comparison_from_query only accepts a bare Identifier
    (optionally aliased/qualified); function calls and expressions are skipped."""
    if tok is None or not isinstance(tok, Identifier):
        return None
    v = tok.value.strip()
    if not _PLAIN_COL.match(v):
        return None
    return v


def _is_literal(tok) -> bool:
    """True only for a constant right operand: string/number literal, not a column reference."""
    if tok is None:
        return False
    if tok.ttype is not None and tok.ttype in T.Literal:
        return True
    if tok.ttype is not None and tok.ttype in T.Number:
        return True
    if isinstance(tok, Identifier):
        return False
    if tok.is_group:
        return False
    v = tok.value.strip()
    if not v or v.lower() in ('select', 'not', 'true', 'false'):
        return False
    if v.lower() == 'null':
        return True
    if v[0] in '\'"':
        return True
    return bool(re.fullmatch(r'-?\d+(?:\.\d+)?', v))


def _add(out: list, name: str, v: str) -> None:
    for k in _split_cols(name):
        out.append((k, _raw_unquote(v)))


def _walk(tok, out: list) -> None:
    if isinstance(tok, Comparison):
        parts = [x for x in tok.tokens if not x.is_whitespace]
        if len(parts) >= 3:
            name = _plain_column_name(parts[0])
            if name and _is_literal(parts[-1]):
                _add(out, name, parts[-1].value)
    if tok.is_group:
        for t in tok.tokens:
            _walk(t, out)


def _is_ident_operand(v: str) -> bool:
    """True if v looks like a bare (possibly qualified) column reference, not a constant."""
    if not v or v[0] in '\'"':
        return False
    if re.fullmatch(r'-?\d+(?:\.\d+)?', v):
        return False
    if v.lower() == 'null':
        return False
    return bool(re.fullmatch(r'[A-Za-z_][\w$]*(\.[A-Za-z_][\w$]*)*', v))


def _clean_qualifier(q: str) -> str:
    """Reduce a regex-captured qualifier to a bare table name (drop keywords, spaces, quotes)."""
    q = q.strip().replace('"', '').replace('`', '').lower()
    if not q:
        return ''
    tok = q.split()[-1] if q.split() else ''
    if not _QUAL.match(tok):
        return ''
    if tok in ('and', 'or', 'where', 'on', 'not', 'select', 'from', 'join', 'as', 'in', 'between', 'like'):
        return ''
    return tok


def _owners(schema, col: str) -> list:
    """Tables that own a column named col (case-insensitive), sorted for determinism."""
    if schema is None:
        return []
    cl = col.lower()
    return sorted({tn for tn, tm in schema.tables.items() for cm in tm.columns if cm.name.lower() == cl})


def _resolve(out: list, schema, qual: str, col: str, v: str) -> None:
    """Emit (table, COL) for the qualifier or, if unqualified, for every owning table; plus (None, COL)."""
    q = _clean_qualifier(qual)
    col = col.strip().replace('"', '').replace('`', '').replace(_PH, '')
    if not col:
        return
    val = _raw_unquote(v)
    if q:
        out.append(((q, col.upper()), val))
    else:
        for tn in _owners(schema, col):
            out.append(((tn, col.upper()), val))
    out.append(((None, col.upper()), val))


def extract_typed_values(sql: str, schema=None) -> list:
    """((table|None, COLUMN), value) pairs from comparisons, IN lists and [NOT] BETWEEN (parse.py:146-253).
    Only constant right operands are kept (column-vs-column join predicates are skipped). A comparison whose
    left side is a function call or expression is skipped (upstream parse.py only accepts a bare Identifier).
    When schema is given, unqualified columns also yield a (owner_table, COL) key for every owning table."""
    out: list = []
    try:
        s = re.sub(r'\b(year|number|length)\b', lambda m: m.group(1) + _PH, sql, flags=re.I)
        try:
            for st in sqlparse.parse(s):
                _walk(st, out)
        except Exception:
            pass
        for m in _CMP.finditer(s):
            v = m.group(2)
            if v.lower() in ('select', 'not'):
                continue
            if _is_ident_operand(v):
                continue
            _resolve(out, schema, m.group(1), m.group(1).split('.')[-1], v)
        for m in _IN.finditer(s):
            inner = m.group(2).strip()
            if not inner or inner.lower().startswith('select'):
                continue
            for it in _ITEM.findall(inner):
                if _is_ident_operand(it):
                    continue
                _resolve(out, schema, m.group(1), m.group(1).split('.')[-1], it)
        for m in _BETWEEN.finditer(s):
            _resolve(out, schema, m.group(1), m.group(1).split('.')[-1], m.group(2))
            _resolve(out, schema, m.group(1), m.group(1).split('.')[-1], m.group(3))
    except Exception:
        pass
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def _isnum(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _root(schema, key: tuple) -> tuple:
    seen = {key}
    while key in schema.fks and schema.fks[key] not in seen:
        key = schema.fks[key]
        seen.add(key)
    return key


def _routing_items(tv: list) -> list:
    """One routing key per literal: the first tabled variant, or (None, COL) if none exists."""
    best: dict = {}
    order = []
    for (t, c), v in tv:
        k = (c, v)
        if k not in best:
            best[k] = t
            order.append(k)
        elif best[k] is None and t is not None:
            best[k] = t
    return [((best[k], k[0]), k[1]) for k in order]


def seed_literal_pool_from_queries(sqls: list, schema, loose: bool = True) -> dict:
    """Route literals to FK-root columns = type_values_w_db(loose=True) (value_typing.py:31-75)."""
    pool: dict = {}
    cache: dict = {}

    def vals(k):
        if k not in cache:
            cache[k] = {str(x) for x in schema.original_values.get(k, []) if x is not None}
        return cache[k]

    for sql in sqls:
        for (t, c), v in _routing_items(extract_typed_values(sql, schema)):
            anchors = [(tn, cm.name) for tn, tm in schema.tables.items() for cm in tm.columns
                       if cm.name.lower() == c.lower() and (t is None or tn.lower() == t)]
            if not anchors and t is not None:
                anchors = [(tn, cm.name) for tn, tm in schema.tables.items() for cm in tm.columns
                           if cm.name.lower() == c.lower()]
            anc = sorted({_root(schema, a) for a in anchors})
            if len(anc) > 1:
                vn = _isnum(v)
                anc = [a for a in anc if vn in {_isnum(x) for x in vals(a)}]
            if len(anc) > 1 and not _isnum(v):
                contain = [a for a in anc if v in vals(a)]
                if contain:
                    keep = set(contain)
                    if loose:
                        for a in anc:
                            if any(vals(a) & vals(b) for b in contain):
                                keep.add(a)
                    anc = sorted(keep)
            for a in anc:
                pool.setdefault(a, []).append(str(v))
    return pool
