"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, apply_null_rule, cap_distinct, _near_dup_str, _near_dup_num


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        if cm.notnull:
            out[cm.name] = vals
        else:
            out[cm.name] = apply_null_rule(vals, True, max(null_share, 0.05), rng)
    return out


def choose_table_sizes(schema, rng, spec_sizes=None) -> dict:
    """Specification sizes when given; else uniform rand_lin sizes w.p."""
    sizes = {}
    if spec_sizes:
        for t in schema.tables:
            base = int(spec_sizes.get(t, 0))
            if rng.random() < 0.5:
                sizes[t] = max(0, int(base * rng.uniform(0.5, 1.5)))
            else:
                sizes[t] = max(0, min(2500, int(base * rng.choice([1, 2, 4]))))
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


def _spec_key(t: str, c: str) -> str:
    return '%s.%s' % (t, c)


def _group_size_plan(n: int, rng) -> list:
    """Group sizes 1, 2 and >=3 (specification group_sizes / aggregate_boundary)."""
    plan = [1, 2, 3]
    while sum(plan) < n:
        plan.append(rng.choice([1, 1, 2, 3, 3, 4]))
    return plan


def _fresh_pk_values(tm, n: int, rng, existing: set) -> list:
    """Sequential integers starting at 1001, step 1, unique against compact rows."""
    if not tm.primary_key or len(tm.primary_key) != 1:
        return None
    start = 1001
    while start in existing:
        start += 1
    return [start + i for i in range(n)]


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) on top of the compact rows."""
    spec = spec or {}
    ranges = spec.get('ranges') or {}
    enums = spec.get('enums') or {}
    null_shares = spec.get('null_shares') or {}
    comp_lits = spec.get('comparison_literals') or {}
    dup_share = float(spec.get('duplicate_share') or 0.3)
    tie_targets = set(spec.get('tie_targets') or [])
    group_targets = spec.get('group_size_targets') or {}

    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                key = _spec_key(t, cm.name)
                lits = list(literal_pool.get((t, cm.name), []))
                for v in comp_lits.get(key, []):
                    if v not in lits:
                        lits.append(v)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, lits, schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), domain=ranges.get(key), enum=enums.get(key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec.get('table_sizes'))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        compact = {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}
        n_compact = len(next(iter(compact.values()))) if compact else 0
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                vals = [samplers[(t, cm.name)].sample() for _ in range(n)]
                key = _spec_key(t, cm.name)
                if key in tie_targets or cm.unique:
                    cap = max(1, int(round((1.0 - dup_share) * max(1, n))))
                    vals = cap_distinct(vals, cap, rng)
                for i in range(len(vals)):
                    if vals[i] is not None and rng.random() < 0.10:
                        if isinstance(vals[i], str):
                            vals[i] = _near_dup_str(vals[i], rng)
                        elif isinstance(vals[i], (int, float)) and not isinstance(vals[i], bool):
                            vals[i] = _near_dup_num(vals[i], rng)
                share = null_shares.get(key, 0.05 if not cm.notnull else 0.0)
                vals = apply_null_rule(vals, not cm.notnull, share, rng)
                cols[cm.name] = compact[cm.name] + vals
            else:
                cols[cm.name] = compact[cm.name] + [None] * n
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                 null_share=null_shares.get(_spec_key(t, tm.columns[0].name), 0.05))
        for c, vals in fk_cols.items():
            cols[c] = compact[c] + vals
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            existing = set(v for v in compact.get(pk, []) if v is not None)
            fresh = _fresh_pk_values(tm, n, rng, existing)
            if fresh is not None:
                cols[pk] = compact[pk] + fresh
        for key in group_targets:
            gt, gc = key.split('.', 1)
            if gt == t and gc in cols:
                plan = _group_size_plan(n, rng)
                vals = []
                for g, k in enumerate(plan):
                    vals.extend([g] * k)
                vals = vals[:n]
                if len(vals) < n:
                    vals.extend([plan[-1]] * (n - len(vals)))
                cols[gc] = compact[gc] + vals
        keep = list(range(n_compact))
        seen_pk = set()
        if tm.primary_key:
            for i in range(n_compact):
                seen_pk.add(tuple(cols[c][i] for c in tm.primary_key))
        for i in range(n_compact, n_compact + n):
            k = tuple(cols[c][i] for c in tm.primary_key) if tm.primary_key else None
            if k is not None and k in seen_pk:
                continue
            if k is not None:
                seen_pk.add(k)
            keep.append(i)
        for cm in tm.columns:
            if cm.unique and cm.name in cols:
                seen, keep2 = set(), []
                for i in keep:
                    v = cols[cm.name][i]
                    if v in seen:
                        continue
                    seen.add(v)
                    keep2.append(i)
                keep = keep2
        inst[t] = {c: [cols[c][i] for i in keep] for c in cols}
    return {t: inst[t] for t in schema.tables}
