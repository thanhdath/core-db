"""Random instance construction (fuzz/fuzz.py:83-196), adapted for round 1."""
import random

from . import specification as S
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows); first kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _null_share(schema, table: str, column: str) -> float:
    """NULL share of the compact database for this column (0.5-30 %), at least one row."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.05
    share = sum(1 for v in vals if v is None) / len(vals)
    return min(0.30, max(0.005, share))


def _plant_nulls(table: str, column: str, values: list, share: float, rng) -> list:
    """NULL rule: at least one NULL row, share following the compact DB."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _plant_duplicates(values: list, rng, share=(0.2, 0.5)) -> list:
    """DISTINCT target: 20-50 % of the values repeat an earlier value."""
    n = len(values)
    if n < 2:
        return values
    k = max(1, int(round(rng.uniform(*share) * n)))
    out = list(values)
    for i in rng.sample(range(1, n), min(k, n - 1)):
        out[i] = out[rng.randrange(0, i)]
    return out


def _plant_ties(values: list, rng) -> list:
    """ORDER/LIMIT target: plant ties at ranks 1, 3, 4 (both directions)."""
    n = len(values)
    if n < 5:
        return values
    out = list(values)
    for a, b in ((0, 1), (2, 3), (3, 4)):
        if a < n and b < n:
            out[b] = out[a]
    return out


def _plant_group_sizes(values: list, rng) -> list:
    """GROUP/HAVING target: group sizes 1,2,3,4,5,6 straddle HAVING thresholds."""
    n = len(values)
    if n < 21:
        return values
    out = list(values)
    pos = 0
    for size in (1, 2, 3, 4, 5, 6):
        base = out[pos]
        for j in range(1, size):
            out[pos + j] = base
        pos += size
    return out


def _parent_key_tuples(schema, inst: dict, pt: str, pcols: tuple) -> list:
    """All (compact + generated) parent key tuples for the given parent columns."""
    compact = schema.original_values
    n_compact = len(compact.get((pt, pcols[0]), []))
    tuples = []
    for i in range(n_compact):
        try:
            t = tuple(compact[(pt, c)][i] for c in pcols)
        except (KeyError, IndexError):
            continue
        if all(v is not None for v in t):
            tuples.append(t)
    gen = inst.get(pt, {})
    if gen and all(c in gen for c in pcols):
        m = len(gen[pcols[0]])
        for i in range(m):
            t = tuple(gen[c][i] for c in pcols)
            if all(v is not None for v in t):
                tuples.append(t)
    return tuples


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_parent: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    handled = set()
    for (ct, child_cols), (pt, pcols) in schema.composite_fks.items():
        if ct != table:
            continue
        tuples = _parent_key_tuples(schema, instance, pt, pcols)
        if tuples:
            picks = [rng.choice(tuples) for _ in range(n)]
            for j, c in enumerate(child_cols):
                out[c] = [p[j] for p in picks]
        else:
            for c in child_cols:
                out[c] = [None] * n
        handled.update(child_cols)
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name in handled:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_parent.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification TABLE_SIZES with per-instance jitter (0-230 rows, or level x4 capped at 2500)."""
    sizes = {}
    for t in schema.tables:
        base = S.TABLE_SIZES.get(t, 20)
        if rng.random() < 0.5:
            sizes[t] = max(0, int(base * rng.uniform(0.5, 1.5)))
        else:
            sizes[t] = max(0, min(2500, int(base * rng.uniform(0.8, 1.2))))
    return sizes


def _is_nullable(cm) -> bool:
    return (not cm.notnull) and cm.pk_pos == 0


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), adapted for round 1."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    compact_parent = {k: list(v) for k, v in schema.original_values.items()}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_parent))
        for cm in tm.columns:
            key = '%s.%s' % (t, cm.name)
            if cm.name not in cols:
                continue
            if _is_nullable(cm):
                cols[cm.name] = _plant_nulls(t, cm.name, cols[cm.name], _null_share(schema, t, cm.name), rng)
            if key in S.DUP_TARGETS and not cm.unique and cm.pk_pos == 0:
                cols[cm.name] = _plant_duplicates(cols[cm.name], rng)
            if key in S.TIE_TARGETS:
                cols[cm.name] = _plant_ties(cols[cm.name], rng)
            if key in S.GROUP_TARGETS:
                cols[cm.name] = _plant_group_sizes(cols[cm.name], rng)
        taken = set()
        if tm.primary_key:
            for i in range(len(schema.original_values.get((t, tm.primary_key[0]), []))):
                try:
                    taken.add(tuple(schema.original_values[(t, c)][i] for c in tm.primary_key))
                except (KeyError, IndexError):
                    pass
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}, taken)
        taken_u = {}
        for cm in tm.columns:
            if cm.unique:
                taken_u[cm.name] = set(v for v in schema.original_values.get((t, cm.name), []) if v is not None)
        cols = drop_unique_duplicates(tm, cols, taken_u)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and cm.name in cols and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
