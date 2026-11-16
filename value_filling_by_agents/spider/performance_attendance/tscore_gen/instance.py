"""Random instance construction (fuzz/fuzz.py:83-196) + spec-driven construction."""
import random

from .spec import (get_pattern, has_pattern, is_not_null_rule, is_null_target, load_spec)
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Pick table sizes from the spec (with a small variation)."""
    sizes = {}
    if spec is not None:
        ts = spec.get('table_sizes', {})
        for t in schema.tables:
            if t in ts:
                sizes[t] = max(1, int(ts[t] * rng.uniform(0.8, 1.2)))
    if not sizes:
        if rng.random() < 0.5:
            for lvl in schema.table_order:
                for t in lvl:
                    min_c = 30 * rng.random()
                    sizes[t] = int(min_c + int(rng.random() * 200))
        else:
            s = 1 + 30 * rng.random()
            for lvl in schema.table_order:
                for t in lvl:
                    sizes[t] = int(min(s, 2500))
                s *= 4
    return sizes


def _share(spec, pattern, t, c, default=(0.2, 0.5)):
    """Duplicate share (lo, hi) for a column from the spec."""
    p = get_pattern(spec, pattern, t, c)
    if isinstance(p, dict) and 'duplicate_share' in p:
        v = p['duplicate_share']
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return float(v[0]), float(v[1])
    return default


def _planted_duplicates(values: list, rng, share_lo: float, share_hi: float) -> list:
    """Duplicate values: 20-50% of rows share a value with another row."""
    if not values:
        return values
    n = len(values)
    share = rng.uniform(share_lo, share_hi)
    k = max(1, int(n * share))
    pool = list(values)
    for _ in range(k):
        idx = rng.randrange(n)
        values[idx] = rng.choice(pool)
    return values


def _planted_ties(values: list, rng, tie, direction: str) -> list:
    """Plant at least two rows tied at the requested rank after sorting (DESC/ASC)."""
    if not values:
        return values
    n = len(values)
    if isinstance(tie, (list, tuple)):
        rank = int(tie[0]) if tie else 1
    elif isinstance(tie, int):
        rank = tie
    else:
        rank = 1
    if rank > n:
        rank = 1
    try:
        order = sorted(range(n), key=lambda i: (values[i] is None, values[i]),
                       reverse=(direction.upper() == 'DESC'))
    except TypeError:
        order = list(range(n))
    if len(order) < 2:
        return values
    pos = min(max(rank - 1, 0), len(order) - 2)
    a, b = order[pos], order[pos + 1]
    values[b] = values[a]
    return values


def _planted_aggregate(values: list, rng, counts: list) -> list:
    """Plant group sizes 1, 2, 3 around the requested count (0 only via LEFT JOIN)."""
    if not values:
        return values
    n = len(values)
    out = []
    for c in counts:
        if c in (1, 2, 3):
            out.extend([c] * c)
    while len(out) < n:
        out.append(values[-1] if values else 0)
    return out[:n]


def _spec_plan(schema, spec: dict, rng) -> dict:
    """Per-table plan: which columns get the spec's patterns."""
    plan = {}
    for t in schema.tables:
        plan[t] = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            plan[t][cm.name] = {
                'duplicates': has_pattern(spec, 'duplicates_for_distinct', t, cm.name),
                'group_sizes': has_pattern(spec, 'group_sizes', t, cm.name),
                'ties': has_pattern(spec, 'ties_for_order_limit', t, cm.name),
                'aggregate': has_pattern(spec, 'aggregate_boundary', t, cm.name),
                'null': is_null_target(spec, t, cm.name) and not is_not_null_rule(spec, t, cm.name),
            }
    return plan


def build_spec(schema: dict) -> dict:
    """Load the spec (specification.json or defaults) and return it."""
    return load_spec()


def _is_key_column(tm, name: str) -> bool:
    return name in tm.primary_key or any(c.name == name and c.unique for c in tm.columns)


def build_instance(schema, literal_pool: dict, spec, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + spec-driven construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                    p, rng, len(tm.primary_key), spec=spec, table=t, col=cm.name)
    size = choose_table_sizes(schema, rng, spec)
    plan = _spec_plan(schema, spec, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = _nrows(cols)
        for cm in tm.columns:
            c = cm.name
            if c not in cols or _is_key_column(tm, c):
                continue
            pl = plan[t].get(c, {})
            if pl.get('duplicates') and n > 0:
                lo, hi = _share(spec, 'duplicates_for_distinct', t, c)
                cols[c] = _planted_duplicates(cols[c], rng, lo, hi)
            if pl.get('ties') and n > 0:
                tp = get_pattern(spec, 'ties_for_order_limit', t, c) or {}
                cols[c] = _planted_ties(cols[c], rng, tp.get('tie_at_rank', 1),
                                        tp.get('direction', 'DESC'))
            if pl.get('group_sizes') and n > 0:
                gp = get_pattern(spec, 'group_sizes', t, c) or {}
                cols[c] = _planted_aggregate(cols[c], rng, gp.get('group_sizes', [1, 2, 3]))
            if pl.get('aggregate') and n > 0:
                ap = get_pattern(spec, 'aggregate_boundary', t, c) or {}
                cols[c] = _planted_aggregate(cols[c], rng, ap.get('count', [1, 2, 3]))
    for (ct, cc), (pt, pc) in schema.fks.items():
        if not has_pattern(spec, 'unmatched_join_rows', ct, cc):
            continue
        parent = inst.get(pt, {})
        child = inst.get(ct, {})
        if not parent or not child:
            continue
        pvals = parent.get(pc, [])
        cvals = child.get(cc, [])
        if not pvals or not cvals:
            continue
        used = set(cvals)
        orphan = next((v for v in pvals if v not in used), None)
        if orphan is None:
            orphan = pvals[0]
            others = [v for v in pvals if v != orphan]
            if others:
                repl = rng.choice(others)
                child[cc] = [repl if v == orphan else v for v in cvals]
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = _nrows(cols)
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if cm.notnull or cm.pk_pos > 0:
                continue
            if is_not_null_rule(spec, t, cm.name):
                continue
            if n == 0:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            obs = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.0
            share = max(obs, 1.0 / n)
            k = max(1, int(round(n * share)))
            idxs = rng.sample(range(n), min(k, n))
            for idx in idxs:
                cols[cm.name][idx] = None
    for t in order:
        tm = schema.tables[t]
        inst[t] = sample_fresh_primary_keys(tm, inst[t])
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = _nrows(cols)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = inst.get(pt, {}).get(pc) or []
            if not pv:
                continue
            fs = set(pv)
            cols[cm.name] = [v if v in fs else rng.choice(pv) for v in cols[cm.name]]
    return {t: inst[t] for t in schema.tables}
