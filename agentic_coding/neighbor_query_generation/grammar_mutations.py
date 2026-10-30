"""Grammar mutations of a gold query, following the Spider test-suite neighbor generator (Zhong et al., 2020).

A mutation either drops one contiguous token span (except whitespace, '*', AS, ASC, ';' and 'name .' spans) or
replaces one token by another of its family: aggregate, comparison, ORDER direction, arithmetic, AND/OR,
LIKE/NOT LIKE, IN/NOT IN, another column of the schema, nearby or random numbers, and sub-spans, cuts and
%-wrapped variants of a string literal.
"""
import random
import re

import sqlparse
from sqlparse import tokens as T

AGG_OP = {'count', 'min', 'max', 'avg', 'sum'}
CMP_OP = {'>', '<', '>=', '<=', '=', '!='}
LIKE_OP = {'LIKE', 'NOT LIKE'}
IN_OP = {'IN', 'NOT IN'}
LOGICAL_OP = {'AND', 'OR'}
NUM_OP = {'/', '+', '-', '*'}
ORDER = {'DESC', 'ASC'}
NUM_ALTERNATIVES = 10
FLOAT_EPS = 1e-1


def _tokens(sql):
    return [(t.ttype, t.value) for t in sqlparse.parse(sql)[0].flatten()]


def _join(tokens):
    return ''.join(v for _, v in tokens).strip().replace('  ', ' ')


def _same_family(token, family):
    ttype, value = token
    if value.lower() in family or value.upper() in family:
        return [(ttype, s) for s in sorted(family) if value.lower() != s and value.upper() != s]
    return []


def _number_replacements(token, rng):
    ttype, value = token
    if ttype == T.Literal.Number.Integer:
        x = int(value)
        drawn = {rng.randint(-abs(x) - 1, abs(x)) for _ in range(NUM_ALTERNATIVES)} - {x}
        return [(ttype, str(y)) for y in sorted(drawn | {x + 1, x - 1})]
    x = float(value)
    drawn = {rng.random() * 2 * x - x for _ in range(NUM_ALTERNATIVES)} - {x}
    return [(ttype, str(y)) for y in sorted(drawn | {x + FLOAT_EPS, x - FLOAT_EPS})]


def _string_replacements(token):
    ttype, value = token
    variants = {value[0] + value[-1]}
    for start in range(1, len(value) - 1):
        for end in range(start + 1, len(value) - 1):
            variants.add(value[0] + value[start:end] + value[-1])
            variants.add(value[:start] + value[end:])
    bare = value.replace('%', '')
    for last in ('%', ''):
        for first in ('%', ''):
            variants.add(bare[0] + first + bare[1:-1] + last + bare[-1])
    return [(ttype, x) for x in sorted(variants) if x != value]


def _replacements(token, columns, rng):
    out = []
    for family in (AGG_OP, CMP_OP, ORDER, NUM_OP, LOGICAL_OP, LIKE_OP, IN_OP, columns):
        out += _same_family(token, family)
    ttype, value = token
    if ttype in (T.Literal.Number.Integer, T.Literal.Number.Float):
        out += _number_replacements(token, rng)
    elif ttype in (T.Literal.String.Symbol, T.Literal.String.Single) and len(value) >= 2:
        out += _string_replacements(token)
    return out


def _droppable(span):
    kept = [x for x in span if x[0] != T.Whitespace]
    if not kept:
        return False
    if len(kept) == 1:
        ttype, value = kept[0]
        if (ttype == T.Keyword.Order and value.lower() == 'asc') or ttype == T.Wildcard \
                or (ttype == T.Keyword and value.lower() == 'as') or (ttype == T.Punctuation and value == ';'):
            return False
    if len(kept) == 2:
        if kept[0][0] == T.Name and kept[1][0] == T.Punctuation and kept[1][1] == '.':
            return False
        if kept[0][1].lower() == 'as' and kept[1][1].lower() == 'result':
            return False
    return True


def _count_free(sql):
    return re.sub(r'COUNT\s?\((.*?)\)', 'COUNT()', sql.strip(), flags=re.IGNORECASE)


def neighbor_queries(sql, columns, rng=None):
    """Sorted, distinct mutations of ``sql``; ``columns`` is the set of upper-case column names of the schema."""
    rng = rng or random.Random(42)
    tokens = _tokens(sql)
    out = set()
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens) + 1):
            if _droppable(tokens[i:j]):
                out.add(_join(tokens[:i] + tokens[j:]))
    for i, token in enumerate(tokens):
        if token[0] != T.Whitespace:
            for replacement in _replacements(token, columns, rng):
                out.add(_join(tokens[:i] + [replacement] + tokens[i + 1:]))
    return sorted(q for q in out if q and q != sql and _count_free(q) != _count_free(sql))
