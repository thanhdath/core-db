"""Spec-driven per-column samplers (built on the generic fuzzer classes)."""
import random

from . import spec
from .values import make_column_sampler


class ColumnPlan:
    def __init__(self, schema, table: str, column: str, literal_pool: list, rng, spec_obj: dict):
        self.table = table
        self.column = column
        self.rng = rng
        self.spec = spec_obj
        cm = self._column_meta(schema, table, column)
        self.column_meta = cm
        self.nullable = bool(cm is not None and not cm.notnull and cm.pk_pos == 0)
        self.pk = cm is not None and cm.pk_pos > 0
        self.observed = list(schema.original_values.get((table, column), []) or [])
        compact_n = max(1, len(self.observed))
        n_null_obs = sum(1 for v in self.observed if v is None)
        self.compact_null_share = n_null_obs / float(compact_n)
        self.enum = spec.enum_pool(table, column)
        self.bstr = spec.boundary_strings(table, column, spec_obj)
        self.bint = spec.boundary_ints(table, column, spec_obj)
        self.measure = spec.measure_range(table, column)
        self.literals = list(literal_pool or [])
        self.duplicate_col = self._is_duplicate_col()
        self.sampler = None
        if not self.pk and not self.bint and not self.bstr:
            self.sampler = make_column_sampler(cm, self._elements(), 0.2, float('inf'), rng) if cm else None

    @staticmethod
    def _column_meta(schema, table: str, column: str):
        tm = schema.tables.get(table)
        if tm is None:
            return None
        for cm in tm.columns:
            if cm.name == column:
                return cm
        return None

    def _elements(self) -> list:
        els = list(self.enum) + list(self.bstr) + list(self.literals)
        els += [v for v in self.observed if v is not None]
        return els

    def _is_duplicate_col(self) -> bool:
        ex = spec.column_exception(self.spec, self.table, self.column)
        return ex.get('pattern') == 'duplicates_for_distinct'

    def value(self, used_dup: list) -> object:
        r = self.rng
        if self.duplicate_col and used_dup and r.random() < spec.duplicate_share():
            return r.choice(used_dup)
        if self.bstr:
            if r.random() < 0.35:
                return r.choice(self.bstr)
            return spec.perturb_string(r.choice(self.bstr), r)
        if self.bint:
            if r.random() < 0.4:
                return r.choice(self.bint)
            return spec.fresh_key_int(r.choice(self.bint), set(), r)
        if self.measure:
            lo, hi = self.measure
            if r.random() < 0.15:
                return r.choice([lo, hi])
            return r.randint(lo, hi)
        if self.enum:
            if r.random() < 0.8:
                return r.choice(self.enum)
            base = r.choice(self.enum)
            if isinstance(base, int):
                return spec.fresh_key_int(base, set(), r)
            return spec.perturb_string(base, r)
        if self.sampler is not None:
            try:
                return self.sampler.sample()
            except Exception:
                pass
        return r.choice(self.observed) if self.observed else 0

    def null_plan(self, n: int) -> list:
        """n booleans: True where the value must be NULL; compact share with >=1 NULL row."""
        if not self.nullable:
            return [False] * n
        share = spec.null_share(self.table, self.column, self.compact_null_share, self.nullable)
        k = int(round(share * n))
        k = max(1, min(k, n))
        flags = [True] * k + [False] * (n - k)
        self.rng.shuffle(flags)
        return flags


def draw_column(schema, table: str, column: str, n: int, literal_pool: list, rng, spec_obj: dict,
                excluded: set = None) -> list:
    excluded = excluded if excluded is not None else set()
    plan = ColumnPlan(schema, table, column, literal_pool, rng, spec_obj)
    nulls = plan.null_plan(n)
    out: list = []
    used_dup: list = []
    for i in range(n):
        if nulls[i]:
            out.append(None)
            continue
        v = plan.value(used_dup)
        if plan.pk:
            tries = 0
            while v in excluded and tries < 10:
                v = spec.fresh_key_int(int(v) if isinstance(v, int) else 0, excluded, rng)
                tries += 1
            excluded.add(v)
        elif v is not None:
            used_dup.append(v)
        out.append(v)
    return out
