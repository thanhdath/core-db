"""In-memory parent-row store and aggregate helpers used by the construction rules."""
import random


class ParentStore:
    """Map table -> {column -> list(values)} for compact + generated rows."""

    def __init__(self, schema):
        self.schema = schema
        self.rows = {t: {cm.name: list(schema.original_values.get((t, cm.name), []) or [])
                         for cm in tm.columns}
                     for t, tm in schema.tables.items()}
        self.n_compact = {t: int(schema.original_sizes.get(t, 0) or 0) for t in schema.tables}
        self._compact_pk = {}
        for t, tm in schema.tables.items():
            if tm.primary_key:
                lists = [self.rows[t].get(c, []) for c in tm.primary_key]
                n = min((len(l) for l in lists), default=0)
                self._compact_pk[t] = [tuple(l[i] for l in lists) for i in range(n)]

    def compact_pk_tuples(self, table: str) -> list:
        """PK tuples present in the compact database for this table (never reconstructed)."""
        return list(self._compact_pk.get(table, []))

    def keys(self, table: str, column: str) -> list:
        return self.rows.get(table, {}).get(column, [])

    def add_row(self, table: str, row: dict) -> None:
        cols = self.rows.setdefault(table, {})
        for c, v in row.items():
            cols.setdefault(c, []).append(v)

    def n_generated(self, table: str) -> int:
        any_col = next(iter(self.rows.get(table, {}).values()), [])
        return max(0, len(any_col) - self.n_compact.get(table, 0))

    def row_tuples(self, table: str, cols: list) -> list:
        """Actual row tuples over `cols` (compact + generated), skipping rows with any NULL."""
        data = self.rows.get(table, {})
        lists = [data.get(c, []) for c in cols]
        if not lists or not lists[0]:
            return []
        n = min(len(l) for l in lists)
        out = []
        for i in range(n):
            tup = tuple(l[i] for l in lists)
            if any(x is None for x in tup):
                continue
            out.append(tup)
        return out

    def pairs_by_key(self, table: str, key_col: str, other_cols: list) -> dict:
        """Map key_col value -> list of tuples over other_cols, from real rows."""
        data = self.rows.get(table, {})
        klist = data.get(key_col, [])
        olists = [data.get(c, []) for c in other_cols]
        if not klist or not olists:
            return {}
        n = min([len(klist)] + [len(l) for l in olists])
        out: dict = {}
        for i in range(n):
            k = klist[i]
            if k is None:
                continue
            tup = tuple(l[i] for l in olists)
            if any(x is None for x in tup):
                continue
            out.setdefault(k, []).append(tup)
        return out

    def distinct_columns(self, table: str, column: str) -> list:
        seen, out = set(), []
        for v in self.keys(table, column):
            if v is None:
                continue
            k = (type(v).__name__, v)
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
        return out

    def pk_pool(self, table: str) -> list:
        """Distinct non-NULL PK tuples present in compact + generated rows."""
        tm = self.schema.tables.get(table)
        if tm is None or not tm.primary_key:
            return []
        lists = [self.rows[table].get(c, []) for c in tm.primary_key]
        n = min((len(l) for l in lists), default=0)
        seen, out = set(), []
        for i in range(n):
            tup = tuple(l[i] for l in lists)
            if any(x is None for x in tup):
                continue
            if tup in seen:
                continue
            seen.add(tup)
            out.append(tup)
        return out


def fk_values(rng, parent_keys: list, n: int, allow_null: bool, null_share: float,
              compact_parent_keys: list = None, force_values: list = None) -> list:
    """Draw n FK values from parent keys (compact or generated), with NULLs per rule."""
    compact_parent_keys = compact_parent_keys or []
    pool = list(parent_keys)
    if not pool:
        return [None] * n
    out = []
    force_values = list(force_values or [])
    for _ in range(n):
        if allow_null and rng.random() < null_share:
            out.append(None)
        elif force_values:
            out.append(force_values.pop(0))
        else:
            out.append(rng.choice(pool))
    return out


def group_size_plan(n: int, rng) -> list:
    from .spec import group_size_plan as _gsp  # noqa: F401
    if n <= 0:
        return []
    return _gsp(n, rng)


def grow_group_targets(n: int, rng) -> list:
    """Return a per-row group id plan whose group sizes include 1, 2 and >=3."""
    if n <= 0:
        return []
    sizes = group_size_plan(n, rng)
    out, gid = [], 0
    for s in sizes:
        out.extend([gid] * s)
        gid += 1
    return out[:n]


def one_tie_plan(base_keys: list, n: int, rng) -> list:
    """Return n values drawn from base_keys s.t."""
    if not base_keys or n <= 0:
        return [None] * n
    plan = []
    if n >= 2:
        top = rng.choice(base_keys)
        plan.extend([top, top])
    while len(plan) < n:
        plan.append(rng.choice(base_keys))
    return plan[:n]
