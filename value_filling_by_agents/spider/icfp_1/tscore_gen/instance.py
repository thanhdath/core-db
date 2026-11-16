"""Random instance construction: compact rows are kept, generated rows are appended."""
from .spec import check_rule, like_variants, near_variants
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _compact_columns(schema, table: str) -> dict:
    """Compact rows of a table, column order preserved."""
    tm = schema.tables[table]
    return {c.name: list(schema.original_values.get((table, c.name), [])) for c in tm.columns}


def _max_int(values) -> int:
    xs = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return max(xs) if xs else 0


def _fresh_int_pool(schema, table: str, column: str, n: int, rng) -> list:
    """Sequential integers above the compact maximum (and above any pool literal)."""
    base = _max_int(schema.original_values.get((table, column), []))
    return [base + 1 + i for i in range(n)]


def _is_text(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('char', 'text', 'clob')) or t == ''


def _is_int(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'int' in t


def _plant_boundary(vals: list, boundary: list, rng) -> None:
    """Force each boundary value into the generated values (in place)."""
    if not boundary or not vals:
        return
    for j, b in enumerate(boundary):
        if j < len(vals):
            vals[j] = b
        else:
            vals[rng.randrange(len(vals))] = b


def _plant_duplicates_merged(compact: list, vals: list, share, rng) -> None:
    """Repeat earlier values so 20-50% of the *merged* column duplicates another row's value."""
    if not share or not vals:
        return
    lo, hi = share
    target = rng.uniform(lo, hi)
    merged = list(compact) + list(vals)
    n = len(merged)
    if n < 2:
        return
    seen, dup = set(), 0
    for v in merged:
        if v in seen:
            dup += 1
        else:
            seen.add(v)
    need = int(round(target * n)) - dup
    if need <= 0:
        return
    pool = [v for v in merged if v is not None]
    if not pool:
        return
    idxs = list(range(len(vals)))
    rng.shuffle(idxs)
    for i in idxs[:need]:
        vals[i] = rng.choice(pool)


def _plant_group_sizes_merged(compact: list, vals: list, rng) -> None:
    """Force group sizes 1, 2 and >= 3 over the merged column (non-unique columns only)."""
    if not vals:
        return
    merged = list(compact) + list(vals)
    if len(merged) < 6:
        return
    base = next((v for v in merged if v is not None), None)
    if base is None:
        return
    if len(vals) >= 3:
        vals[0] = vals[1] = vals[2] = base
    if len(vals) >= 5:
        other = next((v for v in merged if v is not None and v != base), base)
        vals[3] = vals[4] = other


def _plant_tie(vals: list, rng) -> None:
    """Force two rows to share the top value (tie at rank 1 for ORDER/LIMIT)."""
    n = len(vals)
    if n < 2:
        return
    vals[1] = vals[0]


def _sample_independent(schema, spec, table: str, column: str, n: int, rng) -> list:
    """Draw n values for a non-FK column from the specification pools and samplers."""
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == column)
    key = (table, column)
    ex = spec['exceptions'].get(key, {})
    pool = list(spec['pools'].get(key, []))
    if cm.pk_pos > 0:
        return _fresh_int_pool(schema, table, column, n, rng)
    if 'boundary' in ex:
        pool = pool + [v for v in ex['boundary'] if v not in pool]
    if 'like_literals' in ex:
        pool = pool + like_variants(ex['like_literals'], rng)
    if 'variants' in ex:
        pool = pool + [v for v in ex['variants'] if v not in pool]
    p = 0.8 if _is_text(cm) else 0.2
    sampler = _init_sampler(cm, [str(v) for v in pool], schema.original_values.get(key, []),
                            p, rng, len(tm.primary_key))
    vals = []
    for _ in range(n):
        v = sampler.sample()
        if isinstance(v, str) and rng.random() < 0.1:
            nv = near_variants(v, rng, 1)
            if nv:
                v = nv[0]
        vals.append(v)
    if 'like_literals' in ex:
        lv = like_variants(ex['like_literals'], rng)
        _plant_boundary(vals, lv, rng)
    if 'variants' in ex:
        _plant_boundary(vals, ex['variants'], rng)
    if ex.get('duplicate_share'):
        _plant_duplicates_merged(schema.original_values.get(key, []), vals, ex['duplicate_share'], rng)
    if ex.get('group_sizes') and cm.pk_pos == 0:
        _plant_group_sizes_merged(schema.original_values.get(key, []), vals, rng)
    if ex.get('tie'):
        _plant_tie(vals, rng)
    return vals


def _sample_fk(schema, spec, table: str, column: str, n: int, rng, parent_pool: list) -> list:
    """FK child column draws from the parent's compact+generated key pool; NULL by the NULL rule."""
    key = (table, column)
    share = spec['null_share'].get(key, 0.0)
    out = []
    for _ in range(n):
        if parent_pool and rng.random() >= share:
            out.append(rng.choice(parent_pool))
        else:
            out.append(None)
    return out


def _apply_rules(spec, table: str, columns: dict, rng) -> dict:
    """Replace values that violate a semantic rule with a valid pool value (NULL is never replaced)."""
    for column, vals in columns.items():
        for i, v in enumerate(vals):
            if v is None or check_rule(spec, table, column, v):
                continue
            r = spec['rules'].get((table, column))
            if not r:
                continue
            if r[0] == 'between':
                vals[i] = rng.randint(r[1], r[2])
            elif r[0] == 'in':
                vals[i] = rng.choice(r[1])
            elif r[0] == 'in_ci':
                vals[i] = rng.choice(r[1])
            elif r[0] == 'gt':
                vals[i] = r[1] + 1 + rng.randrange(10)
    return columns


def _inject_nulls(spec, table: str, columns: dict, rng, exempt: dict) -> dict:
    """Inject NULLs into nullable non-PK columns at the spec null_share (>= 1 per column)."""
    for column, vals in columns.items():
        key = (table, column)
        share = spec['null_share'].get(key, 0.0)
        if share <= 0.0 or not vals:
            continue
        ex_idx = exempt.get(column, set())
        candidates = [i for i in range(len(vals)) if i not in ex_idx]
        if not candidates:
            continue
        k = max(1, int(len(vals) * share))
        for i in rng.sample(candidates, min(k, len(candidates))):
            vals[i] = None
    return columns


def _dedupe_keys(tm, columns: dict) -> dict:
    """Drop rows repeating the PK tuple or a single-column UNIQUE value (first occurrence kept)."""
    n = _n_rows(columns)
    keep = list(range(n))
    if tm.primary_key and all(c in columns for c in tm.primary_key):
        seen, k2 = set(), []
        for i in keep:
            k = tuple(columns[c][i] for c in tm.primary_key)
            if k not in seen:
                seen.add(k)
                k2.append(i)
        keep = k2
    for cm in tm.columns:
        if cm.unique and cm.name in columns:
            seen, k2 = set(), []
            for i in keep:
                v = columns[cm.name][i]
                if v not in seen:
                    seen.add(v)
                    k2.append(i)
            keep = k2
    return _filter(columns, keep)


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Compact sizes plus a small random number of appended rows per table."""
    sizes = {}
    for t in schema.tables:
        base = (spec or {}).get('sizes', {}).get(t, 0)
        sizes[t] = base + rng.randint(0, 6)
    return sizes


def _reserve_unmatched_parents(schema, spec, inst: dict, rng) -> None:
    """Ensure at least one parent key per parent table is not referenced by any child row."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        ex = spec['exceptions'].get((ct, cc), {})
        if not ex.get('unmatched_parent'):
            continue
        parent_vals = inst.get(pt, {}).get(pc)
        if not parent_vals:
            continue
        base = _max_int(schema.original_values.get((pt, pc), []))
        gen_max = _max_int(parent_vals)
        fresh = max(base, gen_max) + 1
        ptm = schema.tables[pt]
        for cm in ptm.columns:
            col = inst[pt].setdefault(cm.name, [])
            if cm.name == pc:
                col.append(fresh)
            elif cm.pk_pos > 0:
                col.append(fresh)
            else:
                col.append(None)
        child_vals = inst.get(ct, {}).get(cc)
        if child_vals:
            for i, v in enumerate(child_vals):
                if v == fresh:
                    others = [x for x in parent_vals if x != fresh]
                    child_vals[i] = rng.choice(others) if others else None


def _plant_count_ties(schema, spec, inst: dict, rng) -> None:
    """Ensure two parent rows have equal child counts (tie at rank 1 for COUNT(*)-based ORDER/LIMIT)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        ex = spec['exceptions'].get((pt, pc), {})
        if not ex.get('tie'):
            continue
        parent_vals = inst.get(pt, {}).get(pc) or []
        child_vals = inst.get(ct, {}).get(cc) or []
        if len(parent_vals) < 2 or not child_vals:
            continue
        counts = {}
        for v in child_vals:
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        sorted_parents = sorted(parent_vals, key=lambda p: counts.get(p, 0))
        p1, p2 = sorted_parents[0], sorted_parents[1]
        c1, c2 = counts.get(p1, 0), counts.get(p2, 0)
        if c1 == c2:
            continue
        hi_p, lo_p = (p1, p2) if c1 > c2 else (p2, p1)
        need = abs(c1 - c2)
        moved = 0
        for i, v in enumerate(child_vals):
            if moved >= need:
                break
            if v == hi_p:
                child_vals[i] = lo_p
                moved += 1
        inst[ct][cc] = child_vals


def _plant_authorder_diversity(schema, spec, inst: dict, rng) -> None:
    """For each paper group with >= 2 rows, ensure at least two rows have different authOrder values."""
    if 'Authorship' not in inst:
        return
    paper_ids = inst['Authorship'].get('paperID') or []
    orders = inst['Authorship'].get('authOrder') or []
    if not paper_ids or not orders:
        return
    n = min(len(paper_ids), len(orders))
    groups = {}
    for i in range(n):
        p = paper_ids[i]
        if p is not None:
            groups.setdefault(p, []).append(i)
    for p, idxs in groups.items():
        if len(idxs) < 2:
            continue
        vals = {orders[i] for i in idxs if orders[i] is not None}
        if len(vals) < 2:
            a = orders[idxs[0]]
            orders[idxs[1]] = 2 if a == 1 else 1
    inst['Authorship']['authOrder'] = orders


def _plant_boundary_after_rules(spec, table: str, columns: dict, rng) -> dict:
    """Plant boundary values after rule application; return exempt index sets per column."""
    exempt: dict = {}
    for column, vals in columns.items():
        key = (table, column)
        ex = spec['exceptions'].get(key, {})
        boundary = ex.get('boundary')
        if not boundary or not vals:
            continue
        idxs = set()
        for j, b in enumerate(boundary):
            if j < len(vals):
                vals[j] = b
                idxs.add(j)
            else:
                i = rng.randrange(len(vals))
                vals[i] = b
                idxs.add(i)
        exempt[column] = idxs
    return exempt


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one instance: compact rows + generated rows, in foreign-key order."""
    if spec is None:
        from .spec import spec_from_columns
        spec = spec_from_columns(schema)
    for (t, c), vals in literal_pool.items():
        k = (t, c)
        if k in spec['pools']:
            spec['pools'][k] = list(dict.fromkeys(list(spec['pools'][k]) + [str(v) for v in vals]))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    order = [t for lvl in schema.table_order for t in lvl]
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        compact = _compact_columns(schema, t)
        n_gen = max(0, int(size.get(t, 0)) - _n_rows(compact))
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                pt, pc = schema.fks[key]
                parent = inst.get(pt, {}).get(pc) or list(schema.original_values.get((pt, pc), []))
                cols[cm.name] = _sample_fk(schema, spec, t, cm.name, n_gen, rng, parent)
            else:
                cols[cm.name] = _sample_independent(schema, spec, t, cm.name, n_gen, rng)
        cols = _apply_rules(spec, t, cols, rng)
        exempt = _plant_boundary_after_rules(spec, t, cols, rng)
        for cm in tm.columns:
            if cm.pk_pos == 0 and not cm.notnull and cm.name in cols:
                key = (t, cm.name)
                share = spec['null_share'].get(key, 0.0)
                if share > 0.0 and cols[cm.name]:
                    ex_idx = exempt.get(cm.name, set())
                    candidates = [i for i in range(len(cols[cm.name])) if i not in ex_idx]
                    if candidates:
                        k = max(1, int(len(cols[cm.name]) * share))
                        for i in rng.sample(candidates, min(k, len(candidates))):
                            cols[cm.name][i] = None
        cols = _dedupe_keys(tm, cols)
        merged = {}
        for cm in tm.columns:
            merged[cm.name] = list(compact.get(cm.name, [])) + list(cols.get(cm.name, []))
        inst[t] = merged
    _reserve_unmatched_parents(schema, spec, inst, rng)
    _plant_count_ties(schema, spec, inst, rng)
    _plant_authorder_diversity(schema, spec, inst, rng)
    return {t: inst[t] for t in schema.tables}
