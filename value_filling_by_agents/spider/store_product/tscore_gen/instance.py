"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact database."""
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key if c in columns)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples=()) -> dict:
    """Drop rows repeating any single unique column value or composite UNIQUE tuple."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for t, cols in unique_tuples:
        if t != table_meta.name or not all(c in columns for c in cols):
            continue
        seen, keep = set(), []
        for i in range(_n_rows(columns)):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact parent values + generated parent values (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _child_keys(schema) -> set:
    """(table, col) pairs that are foreign-key columns."""
    return set(schema.fks)


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    out = {}
    null_targets = set(spec.get('null_targets') or [])
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        nullable = not cm.notnull and cm.pk_pos == 0
        vals = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        if nullable:
            share = spec.get('null_share', {}).get(table, 0.1)
            k = max(1, int(round(n * share)))
            idx = rng.sample(range(n), min(k, n))
            for i in idx:
                vals[i] = None
            if (table, cm.name) in null_targets and None not in vals and n:
                vals[rng.randrange(n)] = None
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes when given, else the upstream rand_lin / level x4 choice."""
    sizes = {}
    want = spec.get('sizes') or {}
    if want:
        for lvl in schema.table_order:
            for t in lvl:
                n = want.get(t.lower())
                if n is None:
                    n = int(30 * rng.random() + int(rng.random() * 200))
                sizes[t] = max(0, min(int(n), 2500))
        return sizes
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


def _spec_for(spec: dict, table: str, col: str, key: str):
    d = spec.get(key) or {}
    return (d.get(table.lower()) or {}).get(col.lower())


def _all_len(inst_cols: dict) -> int:
    return len(next(iter(inst_cols.values()))) if inst_cols else 0


def _shape_group_sizes(inst_cols: dict, col: str, rng) -> None:
    """Force group sizes 1, 2 and >=3 with an in-place replacement (length unchanged)."""
    vals = inst_cols.get(col)
    n = _all_len(inst_cols)
    if vals is None or n < 6:
        return
    idx = rng.sample(range(n), 3)
    vals[idx[1]] = vals[idx[0]]
    others = [i for i in range(n) if i != idx[2]][:2]
    for i in others:
        vals[i] = vals[idx[2]]


def _shape_duplicates(inst_cols: dict, col: str, rng, share: tuple) -> None:
    """Duplicate share in [lo, hi] for DISTINCT columns (in place)."""
    vals = inst_cols.get(col)
    n = _all_len(inst_cols)
    if vals is None or n < 4:
        return
    lo, hi = share
    target = int(round(n * rng.uniform(lo, hi)))
    for _ in range(target):
        i, j = rng.randrange(n), rng.randrange(n)
        vals[i] = vals[j]


def _order_index(vals: list):
    try:
        return sorted(range(len(vals)), key=lambda i: (vals[i] is None, vals[i]))
    except TypeError:
        return sorted(range(len(vals)), key=lambda i: (vals[i] is None, str(vals[i])))


def _shape_ties(inst_cols: dict, col: str, rng, info: dict) -> None:
    """Plant ties at the listed ranks by repeating the ordering value across rows."""
    vals = inst_cols.get(col)
    n = _all_len(inst_cols)
    if vals is None or n < 3:
        return
    ranks = [r for r in info.get('ranks', []) if 1 <= r <= n]
    if not ranks:
        return
    direction = str(info.get('direction', 'ASC')).upper()
    directions = ['ASC', 'DESC'] if 'AND' in direction else [direction]
    for d in directions:
        ordered = _order_index(vals)
        if d.startswith('DESC'):
            ordered = ordered[::-1]
        ordered = list(ordered)
        for r in ranks:
            a = ordered[r - 1]
            b = ordered[min(r, len(ordered) - 1)]
            if a != b:
                vals[b] = vals[a]


def _shape_different(inst_cols: dict, col: str, rng) -> None:
    """Ensure the largest repeated group contains >= 2 distinct values (in place)."""
    vals = inst_cols.get(col)
    n = _all_len(inst_cols)
    if vals is None or n < 2:
        return
    from collections import Counter
    cnt = Counter(vals)
    top, size = cnt.most_common(1)[0]
    if size < 2:
        return
    choices = [v for v in set(vals) if v != top]
    if not choices:
        return
    other = rng.choice(sorted(choices, key=str))
    for i in range(n):
        if vals[i] == top:
            vals[i] = other
            return


def _shape_unmatched(instance: dict, schema, table: str, inst_cols: dict, rng, spec: dict) -> None:
    """Guarantee at least one parent key that no child references."""
    for cm in schema.tables[table].columns:
        if not _spec_for(spec, table, cm.name, 'unmatched'):
            continue
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in inst_cols:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        if len(pv) < 2:
            continue
        vals = inst_cols[cm.name]
        used = {v for v in vals if v is not None}
        free = [v for v in pv if v not in used]
        if free:
            continue
        victim = rng.choice(sorted(used, key=str))
        repl = rng.choice([v for v in pv if v != victim])
        for i in range(len(vals)):
            if vals[i] == victim:
                vals[i] = repl


def _shape_existing_parents(instance: dict, schema, table: str, inst_cols: dict, rng) -> None:
    """Reserve at least one *existing parent* key that no child references."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in inst_cols:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        vals = inst_cols[cm.name]
        if len(pv) >= 2:
            used = {v for v in vals if v is not None}
            free = [v for v in pv if v not in used]
            if not free:
                victim = rng.choice(sorted(used, key=str))
                repl = rng.choice([v for v in pv if v != victim])
                for i in range(len(vals)):
                    if vals[i] == victim:
                        vals[i] = repl
        nullable = not cm.notnull and cm.pk_pos == 0
        if nullable and None not in vals and len(vals):
            vals[rng.randrange(len(vals))] = None


def _apply_null_rule(table: str, inst_cols: dict, schema, rng, spec: dict) -> None:
    """NULL is a value: every nullable column gets NULL rows with the compact share (>= 1)."""
    null_targets = set(spec.get('null_targets') or [])
    share = spec.get('null_share', {}).get(table, 0.1)
    for cm in schema.tables[table].columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in inst_cols:
            continue
        if (table, cm.name) not in null_targets and (table, cm.name) in schema.fks:
            continue
        vals = inst_cols[cm.name]
        n = len(vals)
        if not n:
            continue
        k = max(1, int(round(n * share)))
        for i in rng.sample(range(n), min(k, n)):
            vals[i] = None


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance of *generated* rows (fuzz.py:111-196 + specification)."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    fresh_share = float(spec.get('fresh_share', 0.3))
    pk_cols = {(t, c) for t, tm in schema.tables.items() for c in tm.primary_key}
    unique_cols = {(t, c.name) for t, tm in schema.tables.items() for c in tm.columns if c.unique}
    protected = pk_cols | unique_cols | _child_keys(schema)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            enum = _spec_for(spec, t, cm.name, 'enums')
            bnd = _spec_for(spec, t, cm.name, 'boundaries')
            rb = _spec_for(spec, t, cm.name, 'ranges')
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), enum=enum, boundaries=bnd, rng_bounds=rb,
                fresh_share=fresh_share)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if (t, cm.name) in protected:
                continue
            if _spec_for(spec, t, cm.name, 'group_sizes'):
                _shape_group_sizes(cols, cm.name, rng)
            ds = _spec_for(spec, t, cm.name, 'dup_share')
            if ds:
                _shape_duplicates(cols, cm.name, rng, ds)
            ti = _spec_for(spec, t, cm.name, 'ties')
            if ti:
                _shape_ties(cols, cm.name, rng, ti)
            if _spec_for(spec, t, cm.name, 'different'):
                _shape_different(cols, cm.name, rng)
        _shape_unmatched(inst, schema, t, cols, rng, spec)
        _shape_existing_parents(inst, schema, t, cols, rng)
        _apply_null_rule(t, cols, schema, rng, spec)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols, schema.unique_tuples)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
