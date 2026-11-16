"""Random instance construction (fuzz/fuzz.py:83-196)."""
import re

from .values import _init_sampler, _str_variants, FRESH_SHARE


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set = None) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows), first kept."""
    if not table_meta.primary_key or not columns:
        return columns
    taken = set(taken or ())
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict = None) -> dict:
    """Drop rows repeating any single unique column value (compact rows included)."""
    taken = taken or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v is None or v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact: dict = None) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    compact = compact or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec_sizes: dict = None) -> dict:
    """Specification table sizes with a small per-instance variation (+/-2 rows per table)."""
    sizes = {}
    spec_sizes = spec_sizes or {}
    for lvl in schema.table_order:
        for t in lvl:
            base = int(spec_sizes.get(t, 4))
            sizes[t] = max(0, base + rng.randint(-2, 2))
    return sizes


def _compact_taken(schema, table: str) -> tuple:
    """(set of PK tuples, {unique column: set of values}) of the compact rows."""
    tm = schema.tables[table]
    n = schema.original_sizes.get(table, 0)
    pk = set()
    if tm.primary_key:
        cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
        for i in range(min([len(c) for c in cols] or [0])):
            pk.add(tuple(c[i] for c in cols))
    uniq = {}
    for cm in tm.columns:
        if cm.unique:
            uniq[cm.name] = {v for v in schema.original_values.get((table, cm.name), []) if v is not None}
    return pk, uniq


def _enforce_rules(table: str, column: str, values: list, rng) -> list:
    """Semantic rules of the specification, enforced in Python (never with SQL)."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if table == 'Person' and column == 'age':
            try:
                v = max(0, int(v))
            except (TypeError, ValueError):
                v = rng.randint(0, 100)
        elif table == 'Person' and column == 'gender':
            if str(v).lower() not in ('female', 'male'):
                v = rng.choice(['female', 'male'])
        elif table == 'Person' and column == 'job':
            if str(v).lower() not in ('student', 'engineer', 'doctor'):
                v = rng.choice(['student', 'engineer', 'doctor'])
        elif table == 'PersonFriend' and column == 'year':
            try:
                v = max(0, int(v))
            except (TypeError, ValueError):
                v = rng.randint(0, 20)
        out.append(v)
    return out


def _plant_ties(values: list, rng) -> list:
    """Ensure at least one tie at the LIMIT rank (rank 1) for ORDER BY columns."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return values
    try:
        lo, hi = min(vals), max(vals)
    except TypeError:
        return values
    for target in (lo, hi):
        if sum(1 for v in values if v == target) < 2:
            for i in range(len(values)):
                if values[i] is None or values[i] == target:
                    continue
                other = hi if target == lo else lo
                if values[i] == other and sum(1 for v in values if v == other) <= 1:
                    continue
                values[i] = target
                break
    distinct = {v for v in values if v is not None}
    if len(distinct) < 2:
        for i in range(len(values)):
            if values[i] is not None:
                try:
                    values[i] = int(values[i]) + 1
                except (TypeError, ValueError):
                    values[i] = str(values[i]) + 'x'
                break
    return values


def _plant_duplicates(values: list, rng) -> list:
    """Ensure at least one duplicate value (20-50% share) for DISTINCT columns."""
    n = len(values)
    if n < 2:
        return values
    lo = max(1, int(round(0.2 * n)))
    hi = max(lo, int(round(0.5 * n)))
    cand = [v for v in values if v is not None]
    if not cand:
        return values
    target = rng.choice(cand)
    have = sum(1 for v in values if v == target)
    want = rng.randint(lo, hi)
    if have >= want:
        return values
    for i in range(n):
        if have >= want:
            break
        if values[i] is not None and values[i] != target:
            values[i] = target
            have += 1
    return values


def _plant_nulls(values: list, null_rate: float, rng) -> list:
    """NULL rule: at least one NULL row per nullable column, share ~ compact null_rate."""
    if not values:
        return values
    k = max(1, int(round(null_rate * len(values))))
    k = min(k, len(values))
    idx = rng.sample(range(len(values)), k)
    for i in idx:
        values[i] = None
    if all(v is None for v in values):
        values[rng.randrange(len(values))] = 'x'
    return values


def _null_rate(schema, table: str, column: str) -> float:
    ov = schema.original_values.get((table, column), [])
    if not ov:
        return 0.0
    return sum(1 for v in ov if v is None) / len(ov)


def _ensure_unmatched_join(inst: dict, schema, rng) -> None:
    """unmatched_join_rows: at least one parent row has no child and at least one child FK is NULL."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        child_vals = inst[ct].get(cc)
        parent_vals = inst[pt].get(pc)
        if not child_vals or not parent_vals:
            continue
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        if cm is not None and not cm.notnull and cm.pk_pos == 0:
            child_vals[rng.randrange(len(child_vals))] = None
        referenced = {v for v in child_vals if v is not None}
        unreferenced = [v for v in parent_vals if v is not None and v not in referenced]
        if not unreferenced and len(parent_vals) > 1:
            for i in range(len(child_vals)):
                if child_vals[i] is not None:
                    child_vals[i] = None
                    break


def build_random_instance(schema, literal_pool: dict, size, rng, spec_sizes: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196), appended to the compact rows."""
    p = FRESH_SHARE
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
        size = choose_table_sizes(schema, rng, spec_sizes)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, schema.original_values))
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _enforce_rules(t, cm.name, cols[cm.name], rng)
        pk_taken, uniq_taken = _compact_taken(schema, t)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, pk_taken)
        cols = drop_unique_duplicates(tm, cols, uniq_taken)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.name in cols:
                if (t, cm.name) in (('Person', 'age'), ('PersonFriend', 'year')):
                    cols[cm.name] = _plant_ties(cols[cm.name], rng)
                if (t, cm.name) in (('PersonFriend', 'name'), ('PersonFriend', 'friend')):
                    cols[cm.name] = _plant_duplicates(cols[cm.name], rng)
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                cols[cm.name] = _plant_nulls(cols[cm.name], _null_rate(schema, t, cm.name), rng)
        inst[t] = cols
    _ensure_unmatched_join(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
