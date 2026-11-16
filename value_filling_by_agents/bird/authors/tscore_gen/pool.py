"""Literal pool: route pool-SQL literals to columns (reuses literals.py extraction)."""
from .literals import extract_typed_values, seed_literal_pool_from_queries


def build_pool(sqls, schema):
    """Return (pool dict {(table,column): [str,...]}, n_skipped)."""
    good, skipped = [], 0
    for s in sqls:
        try:
            extract_typed_values(s)
            good.append(s)
        except Exception:
            skipped += 1
    pool = seed_literal_pool_from_queries(good, schema)
    return pool, skipped
