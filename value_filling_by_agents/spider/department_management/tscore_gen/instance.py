"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the round-1 spec."""
import random

from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated parent values for a FK column (compact rows are never changed)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes per instance (spec.table_sizes_per_instance), with small jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        sizes[t] = max(0, base + rng.randint(-2, 2))
    return sizes


def _pk_start(schema, table: str, col: str) -> int:
    """First fresh PK value: above the compact max (keys fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, (int, float))]
    return int(max(vals)) + 1 if vals else 1


def _plant_nulls(cols: dict, table: str, tm, schema, n: int, rng) -> None:
    """NULL rule: every nullable column gets at least one NULL row per instance."""
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        if cm.name not in cols:
            continue
        share = spec.NULL_FLOOR_SHARE
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k) if n else []
        for i in idx:
            cols[cm.name][i] = None


def _apply_rules(cols: dict, table: str, tm, rng) -> None:
    """Semantic rules by construction: replace only non-NULL values that violate a rule."""
    for cm in tm.columns:
        rule = spec.RULES.get((table, cm.name))
        if rule is None or cm.name not in cols:
            continue
        vals = cols[cm.name]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if not rule(v):
                pool = [x for x in spec.OBSERVED.get(table, {}).get(cm.name, []) if rule(x)]
                pool += [x for x in spec.BOUNDARY.get((table, cm.name), []) if rule(x)]
                if pool:
                    vals[i] = rng.choice(pool)
                else:
                    if isinstance(v, (int, float)):
                        vals[i] = 1 if 'ID' in cm.name or 'Ranking' in cm.name else 0
                    else:
                        vals[i] = 'No'


def _shape_duplicates(cols: dict, table: str, tm, rng) -> None:
    """Shape duplicate shares for DISTINCT / group-size targets (department.Name, head.born_state, head.name)."""
    targets = {
        ('department', 'Name'): spec.NAME_DUP_SHARE,
        ('head', 'born_state'): spec.BORN_STATE_DUP_SHARE,
        ('head', 'name'): spec.HEAD_NAME_DUP_SHARE,
    }
    share = targets.get((table, None))
    for cm in tm.columns:
        s = targets.get((table, cm.name))
        if s is None or cm.name not in cols:
            continue
        vals = cols[cm.name]
        n = len(vals)
        if n < 2:
            continue
        k = max(1, int(round(s * n)))
        for j in range(n - k, n):
            src = rng.randrange(0, max(1, n - k))
            if vals[src] is not None:
                vals[j] = vals[src]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                boundary = spec.BOUNDARY.get((t, cm.name), [])
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), boundary=boundary)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                start = _pk_start(schema, t, cm.name)
                cols[cm.name] = [start + i for i in range(n)]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _shape_duplicates(cols, t, tm, rng)
        _plant_nulls(cols, t, tm, schema, len(next(iter(cols.values()))) if cols else 0, rng)
        _apply_rules(cols, t, tm, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
