"""Literal pool construction from queries and original values."""
import re

from .literals import extract_typed_values, _isnum


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


def build_literal_pool(sqls: list, schema, loose: bool = True) -> dict:
    """Route literals to FK-root columns; also seed from original values so every column has a pool."""
    pool: dict = {}
    cache: dict = {}

    def vals(k):
        if k not in cache:
            cache[k] = {str(x) for x in schema.original_values.get(k, []) if x is not None}
        return cache[k]

    for k, vs in schema.original_values.items():
        pool.setdefault(k, [])
        for v in vs:
            if v is not None:
                pool[k].append(str(v))

    for sql in sqls:
        for (t, c), v in _routing_items(extract_typed_values(sql)):
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
