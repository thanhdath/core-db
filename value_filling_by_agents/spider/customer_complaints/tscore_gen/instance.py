"""Random instance construction (fuzz/fuzz.py:83-196) with specification-driven samplers."""
from .values import (apply_duplicate_share, apply_group_sizes, apply_null_rule,
                     apply_tie, make_spec_sampler, DISTINCT_COLUMNS, TIE_COLUMNS,
                     GROUP_SIZE_COLUMNS, UNMATCHED_PARENT, DIFFERENT_VALUE_COLUMNS)


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_numeric_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(existing.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_parent: dict) -> dict:
    """FK child columns draw from the parent's *final* parent set (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(compact_parent.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
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


def _enforce_semantic_rules(table: str, cols: dict, rng) -> None:
    """Enforce the specification's semantic rules by construction (in Python)."""
    if table == 'Products':
        if 'product_price' in cols:
            fixed = []
            for v in cols['product_price']:
                if v is None:
                    fixed.append(None)
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    f = round(rng.uniform(0.01, 200.00), 4)
                fixed.append(round(max(0.01, min(200.0, f)), 4))
            cols['product_price'] = fixed
    if table == 'Complaints':
        ra, cl = cols.get('date_complaint_raised'), cols.get('date_complaint_closed')
        if ra is not None and cl is not None:
            for i in range(len(cl)):
                if ra[i] is not None and cl[i] is not None and str(cl[i]) < str(ra[i]):
                    cl[i] = ra[i]


def _revalidate_fks(rows: dict, schema, fks: dict) -> None:
    """Drop child rows whose FK is a non-NULL value that no longer exists in the parent."""
    for (ct, cc), (pt, pc) in fks.items():
        if ct not in rows or pt not in rows:
            continue
        child = rows[ct].get(cc)
        parent = rows[pt].get(pc)
        if child is None or parent is None:
            continue
        pset = set(v for v in parent if v is not None)
        if not pset:
            continue
        keep = [i for i, v in enumerate(child) if v is None or v in pset]
        if len(keep) != len(child):
            for i, v in enumerate(child):
                if v is not None and v not in pset:
                    child[i] = sorted(pset)[0]
            rows[ct] = _filter(rows[ct], keep)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of *appended* rows (fuzz.py:111-196 + specification)."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    compact_parent = {k: list(v) for k, v in schema.original_values.items()}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            ov = schema.original_values.get(key, [])
            pool = literal_pool.get(key, [])
            sampler = make_spec_sampler(t, cm, pool, ov, rng,
                                        schema.null_share.get(key, 0.0),
                                        schema.distinct_count.get(key, 0))
            vals = [sampler.sample() for _ in range(n)]
            if key in DISTINCT_COLUMNS:
                vals = apply_duplicate_share(vals, rng)
            if key in GROUP_SIZE_COLUMNS:
                vals = apply_group_sizes(vals, rng, numeric=_is_numeric_col(cm))
            if key in TIE_COLUMNS:
                vals = apply_tie(vals, rng, TIE_COLUMNS[key])
            if key in DIFFERENT_VALUE_COLUMNS and n >= 2:
                if len({v for v in vals if v is not None}) < 2:
                    vals[0] = 0.01
                    vals[1] = 200.0
            cols[cm.name] = vals
        existing_pk = set()
        if tm.primary_key:
            pk_vals = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            for i in range(min((len(v) for v in pk_vals), default=0)):
                existing_pk.add(tuple(v[i] for v in pk_vals))
        cols = sample_fresh_primary_keys(tm, cols, existing_pk)
        existing_uq = {c.name: set(v for v in schema.original_values.get((t, c.name), []) if v is not None)
                       for c in tm.columns if c.unique}
        cols = drop_unique_duplicates(tm, cols, existing_uq)
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_parent)
        for name, vals in fk_cols.items():
            cols[name] = vals
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _enforce_semantic_rules(t, cols, rng)
        inst[t] = cols
    for (pt, pc), (ct, cc) in UNMATCHED_PARENT.items():
        if pt in inst and ct in inst and pc in inst[pt] and cc in inst[ct]:
            used = set(v for v in inst[ct][cc] if v is not None)
            parents = [v for v in inst[pt][pc] if v is not None]
            if parents and all(p in used for p in parents):
                drop = parents[-1]
                keep = [i for i, v in enumerate(inst[ct][cc]) if v != drop]
                inst[ct] = _filter(inst[ct], keep)
    _revalidate_fks(inst, schema, schema.fks)
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in inst[t]:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            if not nullable:
                continue
            inst[t][cm.name] = apply_null_rule(inst[t][cm.name], rng,
                                               schema.null_share.get(key, 0.0), True)
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in inst[t]:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            if not nullable:
                continue
            vals = inst[t][cm.name]
            if vals and not any(v is None for v in vals):
                vals[rng.randrange(len(vals))] = None
    return {t: inst[t] for t in schema.tables}
