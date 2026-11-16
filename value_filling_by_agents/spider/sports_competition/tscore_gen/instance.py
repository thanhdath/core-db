"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .specification import load_specification
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_fk_cols=()) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = []
        for _ in range(n):
            if cm.name in null_fk_cols and rng.random() < 0.08:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes per instance with small jitter (0-230 rows per table)."""
    base = spec.get('table_sizes_per_instance', {})
    jitter = int(spec.get('size_jitter', 3))
    sizes = {}
    for t in schema.tables:
        b = int(base.get(t, 0))
        if b <= 0:
            sizes[t] = 0
            continue
        sizes[t] = min(230, b + rng.randint(0, jitter))
    return sizes


def _apply_formulas(inst: dict, spec: dict) -> None:
    """Compute derived columns in Python from in-memory sampled values (never SQL)."""
    for key, f in spec.get('formulas', {}).items():
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        parts = [p.split('.', 1)[1] for p in f.get('of', [])]
        if f.get('op') != 'sum' or not parts:
            continue
        n = len(inst[t][col])
        out = []
        for i in range(n):
            vals = [inst[t][p][i] for p in parts if p in inst[t]]
            if any(v is None for v in vals):
                out.append(None)
            else:
                out.append(sum(vals))
        inst[t][col] = out


def _apply_non_negative(inst: dict, spec: dict) -> None:
    """Clamp non-NULL operands to >= 0 (rule holds when expression is not FALSE)."""
    for key in spec.get('non_negative', []):
        t, col = key.split('.', 1)
        if t in inst and col in inst[t]:
            inst[t][col] = [None if v is None else max(0, v) for v in inst[t][col]]


def _plant_nulls(inst: dict, schema, spec: dict, rng) -> None:
    """NULL rule: every nullable column gets >=1 NULL row per instance (share ~0-10%)."""
    targets = set(spec.get('null_targets', []))
    for t, tm in schema.tables.items():
        if t not in inst:
            continue
        n = len(next(iter(inst[t].values()))) if inst[t] else 0
        if n == 0:
            continue
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            key = '%s.%s' % (t, cm.name)
            if key not in targets:
                continue
            col = inst[t].get(cm.name)
            if col is None:
                continue
            if any(v is None for v in col):
                continue
            k = max(1, int(round(n * rng.uniform(0.0, 0.10))))
            k = min(k, n)
            idx = rng.sample(range(n), k)
            for i in idx:
                col[i] = None


def _ensure_duplicate_share(inst: dict, spec: dict, rng) -> None:
    """DISTINCT-targeted columns: 20-50% duplicate share (by construction)."""
    for key in spec.get('duplicate_share_columns', []):
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        n = len(vals)
        if n < 3:
            continue
        non_null = [v for v in vals if v is not None]
        if not non_null:
            continue
        target_dup = int(round(n * rng.uniform(0.20, 0.50)))
        target_dup = max(1, min(target_dup, n - 1))
        distinct_keep = n - target_dup
        seen, keep_idx = set(), []
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in seen:
                seen.add(v)
                keep_idx.append(i)
            if len(keep_idx) >= distinct_keep:
                break
        if not keep_idx:
            continue
        pool = [vals[i] for i in keep_idx]
        for i in range(n):
            if vals[i] is None:
                continue
            if i not in keep_idx:
                vals[i] = rng.choice(pool)


def _ensure_group_sizes(inst: dict, spec: dict, rng) -> None:
    """Group-size targets: groups of size 1, 2 and >= 3 for the listed columns."""
    for key in spec.get('group_size_columns', []):
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        n = len(vals)
        if n < 6:
            continue
        labels = ['g1', 'g2', 'g3']
        sizes = [1, 2, max(3, n - 3)]
        assign = []
        for lab, sz in zip(labels, sizes):
            assign.extend([lab] * sz)
        assign = assign[:n]
        while len(assign) < n:
            assign.append(rng.choice(labels))
        rng.shuffle(assign)
        for i in range(n):
            if vals[i] is not None:
                vals[i] = assign[i]


def _ensure_unmatched_join(inst: dict, schema, spec: dict, rng) -> None:
    """Parent rows without children: leave some parent PKs unreferenced by generated children."""
    uj = spec.get('unmatched_join', {})
    parents = uj.get('parents', [])
    for pkey in parents:
        pt, pc = pkey.split('.', 1)
        if pt not in inst or pc not in inst[pt]:
            continue
        pvals = [v for v in inst[pt][pc] if v is not None]
        if len(pvals) < 2:
            continue
        for (ct, cc), (pp, ppc) in schema.fks.items():
            if pp != pt or ppc != pc:
                continue
            if ct not in inst or cc not in inst[ct]:
                continue
            child = inst[ct][cc]
            orphan = rng.choice(pvals)
            for i, v in enumerate(child):
                if v == orphan:
                    others = [x for x in pvals if x != orphan]
                    if others:
                        child[i] = rng.choice(others)


def _ensure_rows_with_different_values(inst: dict, spec: dict, rng) -> None:
    """>= 2 rows per group with different values for the listed columns."""
    for key in spec.get('rows_with_different_values', []):
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        non_null = [i for i, v in enumerate(vals) if v is not None]
        if len(non_null) < 2:
            continue
        a, b = rng.sample(non_null, 2)
        if vals[a] == vals[b]:
            vals[b] = vals[a] + 1 if isinstance(vals[a], (int, float)) else vals[a]


def _ensure_ties_for_order_limit(inst: dict, spec: dict, rng) -> None:
    """Tied sort values for ORDER BY ..."""
    for key, cfg in spec.get('ties_for_order_limit', {}).items():
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        non_null = [i for i, v in enumerate(vals) if v is not None]
        if len(non_null) < 2:
            continue
        a, b = rng.sample(non_null, 2)
        vals[b] = vals[a]


def _ensure_aggregate_boundary(inst: dict, spec: dict, rng) -> None:
    """Aggregate boundary: ensure group counts straddle the listed COUNT(*) thresholds."""
    for key, thresholds in spec.get('aggregate_boundary', {}).items():
        t, col = key.split('.', 1)
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        n = len(vals)
        if n < 6:
            continue
        labels = []
        for th in thresholds:
            labels.extend(['c%d' % th] * max(1, th))
        labels = labels[:n]
        while len(labels) < n:
            labels.append(rng.choice(labels))
        rng.shuffle(labels)
        for i in range(n):
            if vals[i] is not None:
                vals[i] = labels[i]


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    spec = spec or load_specification()
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                key = '%s.%s' % (t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), spec=spec, key=key)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    null_fk = set(spec.get('unmatched_join', {}).get('child_null_fk', []))
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, null_fk))
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
    _apply_formulas(inst, spec)
    _apply_non_negative(inst, spec)
    _ensure_duplicate_share(inst, spec, rng)
    _ensure_group_sizes(inst, spec, rng)
    _ensure_aggregate_boundary(inst, spec, rng)
    _ensure_rows_with_different_values(inst, spec, rng)
    _ensure_ties_for_order_limit(inst, spec, rng)
    _ensure_unmatched_join(inst, schema, spec, rng)
    _plant_nulls(inst, schema, spec, rng)
    _apply_formulas(inst, spec)
    return {t: inst[t] for t in schema.tables}
