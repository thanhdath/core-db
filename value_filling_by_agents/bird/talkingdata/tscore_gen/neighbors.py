"""Neighbour queries (fuzz/neighbor.py:1-177)."""
import re
import sqlite3

import sqlparse
from sqlparse import tokens as T

FAMILIES = [['count', 'min', 'max', 'avg', 'sum'], ['>', '<', '>=', '<=', '=', '!='], ['desc', 'asc'],
            ['/', '+', '-', '*'], ['and', 'or'], ['like', 'not like'], ['in', 'not in']]
_ALL = {x for f in FAMILIES for x in f}


def _join(toks: list) -> str:
    return ''.join(toks).strip().replace('  ', ' ')


def _droppable(span: list) -> bool:
    """neighbor.py:110-129."""
    s = ''.join(span).strip().lower()
    if not s or s in ('asc', '*', 'as', ';', 'as result'):
        return False
    return not re.fullmatch(r'\w+\s*\.', s)


def _str_variants(v: str) -> list:
    qc, body = v[0], v[1:-1]
    out = {''}
    n = len(body)
    for a in range(n + 1):
        for b in range(a + 1, n + 1):
            out.add(body[a:b])
            out.add(body[:a] + body[b:])
    out |= {'%' + body, body + '%', '%' + body + '%', body}
    return [qc + x.replace(qc, qc * 2) + qc for x in sorted(out)]


def _family(low: str, v: str) -> list:
    out = []
    for fam in FAMILIES:
        if low in fam:
            out += [x.upper() if v.isupper() else x for x in fam if x != low]
    return out


def _replacements(tok, cols: list, collow: set, rng) -> list:
    v, low = tok.value, tok.value.lower()
    out = _family(low, v)
    if tok.ttype in T.Name or low in collow:
        out += cols
    if tok.ttype in T.Number.Integer:
        i = int(v)
        out += [str(rng.randint(-abs(i) - 1, abs(i))) for _ in range(10)] + [str(i + 1), str(i - 1)]
    elif tok.ttype in T.Number.Float:
        f = float(v)
        out += [str(rng.uniform(-f, f)) for _ in range(10)] + [str(f + 0.1), str(f - 0.1)]
    elif (tok.ttype in T.String.Single or tok.ttype in T.String.Symbol) and len(v) >= 2 and v[0] == v[-1]:
        out += _str_variants(v)
    return out


def _norm(s: str) -> str:
    return re.sub(r'count\s*\([^)]*\)', 'count()', s, flags=re.I).strip().rstrip(';').strip()


def neighbor_queries(sql: str, schema, rng, max_neighbors: int = 5000) -> list:
    """Span drops + token replacements kept if executable on an empty schema clone (neighbor.py:1-177).
    Neighbours that lose the FROM clause of a query that has one are excluded (new, recorded)."""
    try:
        toks = [t for st in sqlparse.parse(sql) for t in st.flatten()]
    except Exception:
        return []
    vals = [t.value for t in toks]
    cand = set()
    for i in range(len(toks)):
        for j in range(i + 1, len(toks) + 1):
            if _droppable(vals[i:j]):
                cand.add(_join(vals[:i] + vals[j:]))
    cols = sorted({c.name for tm in schema.tables.values() for c in tm.columns})
    collow = {c.lower() for c in cols}
    nonws = [i for i, t in enumerate(toks) if not t.is_whitespace]
    for k, i in enumerate(nonws):
        t = toks[i]
        for r in _replacements(t, cols, collow, rng):
            cand.add(_join(vals[:i] + [r] + vals[i + 1:]))
        if k + 1 < len(nonws) and t.value.lower() == 'not':
            j = nonws[k + 1]
            nxt = toks[j].value.lower()
            if nxt in ('like', 'in'):
                for r in _family('not ' + nxt, toks[j].value):
                    cand.add(_join(vals[:i] + [r] + vals[j + 1:]))
    base = _norm(_join(vals))
    need_from = re.search(r'\bfrom\b', sql, re.I) is not None
    con = sqlite3.connect(':memory:')
    for s in schema.ddl:
        try:
            con.execute(s)
        except sqlite3.Error:
            pass
    keep = []
    for c in sorted(cand):
        if not c or c == sql.strip() or _norm(c) == base:
            continue
        if need_from and not re.search(r'\bfrom\b', c, re.I):
            continue
        try:
            con.execute(c).fetchall()
            keep.append(c)
        except Exception:
            pass
    con.close()
    if max_neighbors is not None and len(keep) > max_neighbors:
        keep = sorted(rng.sample(keep, max_neighbors))
    return keep
