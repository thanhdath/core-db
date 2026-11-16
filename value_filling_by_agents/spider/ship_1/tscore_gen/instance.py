"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import column_domain, is_null_target
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
    """Parent key values: compact originals plus generated values (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []) or [])
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's key pool with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _plant_nulls(columns: dict, table_meta, schema, table: str, n: int, rng, spec: dict) -> None:
    """NULL rule: only spec null_targets get NULLs; >= 1 NULL; share follows the compact share (5-30 %)."""
    if n <= 0:
        return
    for cm in table_meta.columns:
        if cm.pk_pos > 0 or cm.notnull:
            continue
        if cm.name not in columns:
            continue
        if not is_null_target(spec, table, cm.name):
            continue
        dom = column_domain(spec, table, cm.name)
        share = dom.get('null_share')
        if share is None:
            orig = schema.original_values.get((table, cm.name), []) or []
            if orig:
                share = sum(1 for v in orig if v is None) / max(1, len(orig))
            else:
                share = 0.0
        if isinstance(share, (tuple, list)):
            share = rng.uniform(share[0], share[1])
        k = max(1, int(round(float(share) * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            columns[cm.name][i] = None


def _apply_group_sizes(columns: dict, table_meta, table: str, n: int, rng, spec: dict) -> None:
    """Realise group-size targets (1, 2 and >= 3) by repeating values in a column."""
    if n < 6:
        return
    for cm in table_meta.columns:
        if cm.pk_pos > 0 or cm.name not in columns:
            continue
        dom = column_domain(spec, table, cm.name)
        if not dom.get('group_sizes'):
            continue
        vals = columns[cm.name]
        nonnull = [v for v in vals if v is not None]
        if not nonnull:
            continue
        bases = list(dict.fromkeys(nonnull))[:3]
        if not bases:
            continue
        plan = []
        for gi, b in enumerate(bases):
            plan += [b] * (gi + 1)
        while len(plan) < n:
            plan.append(rng.choice(bases))
        rng.shuffle(plan)
        for i in range(n):
            if vals[i] is not None:
                vals[i] = plan[i]


def _apply_duplicate_share(columns: dict, table_meta, table: str, n: int, rng, spec: dict) -> None:
    """Realise a 20-50 % duplicate share on DISTINCT columns by copying values."""
    if n < 4:
        return
    for cm in table_meta.columns:
        if cm.pk_pos > 0 or cm.name not in columns:
            continue
        dom = column_domain(spec, table, cm.name)
        share = dom.get('dup_share')
        if not share:
            continue
        lo, hi = share if isinstance(share, (tuple, list)) else (0.2, 0.5)
        k = int(round(rng.uniform(lo, hi) * n))
        vals = columns[cm.name]
        idx = [i for i in range(n) if vals[i] is not None]
        if len(idx) < 2:
            continue
        for i in rng.sample(idx, min(k, len(idx))):
            j = rng.choice([x for x in idx if x != i])
            vals[i] = vals[j]


def _distinct_per_group(columns: dict, table_meta, table: str, n: int, rng, spec: dict) -> None:
    """Ensure >= 2 distinct values per non-NULL FK group for columns flagged distinct_per_group."""
    for cm in table_meta.columns:
        if cm.name not in columns:
            continue
        dom = column_domain(spec, table, cm.name)
        if not dom.get('distinct_per_group'):
            continue
        fk = None
        for c2 in table_meta.columns:
            if (table, c2.name) in _SCHEMA_FKS:
                fk = c2.name
                break
        if fk is None or fk not in columns:
            continue
        vals = columns[cm.name]
        groups: dict = {}
        for i, g in enumerate(columns[fk]):
            if g is None:
                continue
            groups.setdefault(g, []).append(i)
        for g, idxs in groups.items():
            if len(idxs) < 2:
                continue
            seen = {vals[i] for i in idxs}
            if len(seen) < 2:
                base = vals[idxs[0]]
                if base is not None and str(base).isdigit():
                    vals[idxs[-1]] = str(int(base) + 1)
                elif base is not None:
                    vals[idxs[-1]] = str(base) + 'x'


def _apply_tie_at_rank(columns: dict, table_meta, table: str, n: int, rng, spec: dict) -> None:
    """Realise a tie at rank 1 on COUNT(*) DESC for columns flagged tie_at_rank [1]."""
    if n < 4:
        return
    for cm in table_meta.columns:
        if cm.pk_pos > 0 or cm.name not in columns:
            continue
        dom = column_domain(spec, table, cm.name)
        if not dom.get('tie_at_rank'):
            continue
        vals = columns[cm.name]
        idx = [i for i in range(n) if vals[i] is not None]
        if len(idx) < 4:
            continue
        a, b = vals[idx[0]], vals[idx[1]]
        if a == b:
            continue
        vals[idx[0]] = a
        vals[idx[1]] = a
        vals[idx[2]] = b
        vals[idx[3]] = b


_SCHEMA_FKS: dict = {}


def choose_table_sizes(schema, rng, spec: dict = None) -> dict:
    """Specification sizes when given, else the upstream rand_lin / level sizes (fuzz.py:83-110)."""
    spec = spec or {}
    fixed = spec.get('table_sizes') or {}
    if fixed:
        return {t: int(fixed.get(t, 0)) for t in schema.tables}
    sizes = {}
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


def _pk_offsets(schema) -> dict:
    """Per-table, per-PK-column offset so generated keys start above the compact max."""
    off = {}
    for t, tm in schema.tables.items():
        for c in tm.primary_key:
            vals = [v for v in schema.original_values.get((t, c), []) if isinstance(v, (int, float))]
            off[(t, c)] = int(max(vals)) if vals else 0
    return off


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance of *appended* rows (fuzz.py:111-196, spec-aware)."""
    spec = spec or {}
    _SCHEMA_FKS.clear()
    _SCHEMA_FKS.update(schema.fks)
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                dom = column_domain(spec, t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), domain=dom)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    offsets = _pk_offsets(schema)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for c in tm.primary_key:
            if c in cols:
                base = offsets.get((t, c), 0)
                cols[c] = [base + i + 1 for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        _apply_group_sizes(cols, tm, t, n, rng, spec)
        _apply_duplicate_share(cols, tm, t, n, rng, spec)
        _apply_tie_at_rank(cols, tm, t, n, rng, spec)
        _distinct_per_group(cols, tm, t, n, rng, spec)
        _plant_nulls(cols, tm, schema, t, n, rng, spec)
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
    return {t: inst[t] for t in schema.tables}
