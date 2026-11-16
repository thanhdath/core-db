"""Random instance construction adapted for the specification."""
from .spec import (CHAR_PK_POOLS, DUP_DISTINCT_SHARE, DUP_DISTINCT_TARGETS, GROUP_SIZE, GUARANTEED_LITERALS,
                   PARENT_GROUP_SIZE, NULL_TARGETS, table_size)
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        if not all(c in columns for c in table_meta.primary_key):
            keep.append(i)
            continue
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, unique_sets: dict) -> dict:
    """Drop rows repeating any single unique column value or composite unique tuple."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for cols_tuple in unique_sets.get(table_meta.name, []):
        if all(c in columns for c in cols_tuple):
            seen, keep = set(), []
            n = len(columns[cols_tuple[0]])
            for i in range(n):
                k = tuple(columns[c][i] for c in cols_tuple)
                if k not in seen:
                    seen.add(k)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_max(schema, table: str, column: str) -> int:
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _parent_keys(schema, instance: dict, pt: str, pc: str) -> list:
    """Final parent key set = compact values + generated values (non-NULL)."""
    out = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    out += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return out


def _parent_tuples(schema, instance: dict, pt: str, pcs: list) -> list:
    """Existing parent tuples (compact + generated, non-NULL in all components)."""
    n_compact = len(schema.original_values.get((pt, pcs[0]), [])) if pcs else 0
    out = []
    for i in range(n_compact):
        t = tuple(schema.original_values.get((pt, c), [None] * n_compact)[i] for c in pcs)
        if all(v is not None for v in t):
            out.append(t)
    gen = instance.get(pt, {})
    if gen and all(c in gen for c in pcs):
        n_gen = len(gen[pcs[0]])
        for i in range(n_gen):
            t = tuple(gen[c][i] for c in pcs)
            if all(v is not None for v in t):
                out.append(t)
    return out


def _child_counts_for_group_sizes(n_children: int, n_parents: int, rng) -> list:
    """Assign each child to a parent index so that group sizes 1, 2 and >=3 all occur."""
    if n_parents < 3 or n_children < 6:
        return [rng.randrange(n_parents) for _ in range(n_children)]
    order = list(range(n_parents))
    rng.shuffle(order)
    p1, p2, p3 = order[0], order[1], order[2]
    rest = order[3:]
    assign = [p1, p2, p2, p3, p3, p3]
    while len(assign) < n_children:
        assign.append(rng.choice(rest) if rest else rng.choice(order))
    rng.shuffle(assign)
    return assign


def _parent_keys_with_group_sizes(schema, instance: dict, pt: str, pc: str, n: int, rng) -> list:
    """Draw n parent key values, reserving at least one parent with no children."""
    vals = _parent_keys(schema, instance, pt, pc)
    seen, uniq = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    if not uniq:
        return []
    pool = list(uniq)
    if len(pool) > 1:
        reserve = 1
        usable = pool[:max(1, len(pool) - reserve)]
    else:
        usable = pool
    if len(usable) >= 3 and n >= 6:
        idxs = _child_counts_for_group_sizes(n, len(usable), rng)
        return [usable[i] for i in idxs]
    return [rng.choice(usable) for _ in range(n)]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance following the specification, all values in memory."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            nullable = (t, cm.name) in NULL_TARGETS and not cm.notnull
            share = _null_share_for(ov, max(len(ov), 1)) if nullable else 0.0
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), ov, p, rng, len(tm.primary_key), nullable=nullable,
                null_share=share,
            )
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}

        pk_cols = [c for c in tm.columns if c.pk_pos > 0]
        pk_cols.sort(key=lambda c: c.pk_pos)
        if len(pk_cols) == 1 and pk_cols[0].name not in schema.fks:
            pk = pk_cols[0]
            tlow = (pk.type_str or '').lower()
            if 'int' in tlow:
                cols[pk.name] = _sequential_pk(schema, t, pk.name, n)
            elif (t, pk.name) in CHAR_PK_POOLS:
                pools = CHAR_PK_POOLS[(t, pk.name)]
                vals = [pools[i % len(pools)] for i in range(min(n, len(pools)))]
                while len(vals) < n:
                    vals.append(rng.choice(pools))
                cols[pk.name] = vals
        elif len(pk_cols) >= 2:
            _generate_composite_pk(schema, inst, t, pk_cols, n, rng, cols, samplers)

        for cm in tm.columns:
            if cm.name in cols:
                continue
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                continue
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
            elif cm.default is not None:
                cols[cm.name] = [cm.default] * n
            else:
                cols[cm.name] = [None] * n

        n_available = len(cols.get(pk_cols[0].name, [])) if pk_cols else n
        if pk_cols and pk_cols[0].name in cols:
            n_available = len(cols[pk_cols[0].name])
        else:
            n_available = n
        _fill_foreign_keys(schema, inst, t, n_available, rng, cols)

        inst[t] = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = inst[t].get(pc, [])
                fs = set(final)
                if fs:
                    inst[t][cm.name] = [v if v is None or v in fs else rng.choice(list(fs)) for v in inst[t][cm.name]]

    _apply_guaranteed_literals(inst, rng)
    _apply_group_size_hints(inst, schema, rng)
    _apply_dup_distinct_hints(inst, rng)
    _reserve_parent_without_children(inst, schema, rng)
    _force_nulls_and_nonnulls(inst, schema, rng)
    return {t: inst.get(t, {}) for t in schema.tables}


def _null_share_for(original_values, n: int) -> float:
    """Compact share when observed; otherwise a small fixed share honouring at least one NULL."""
    if n <= 0:
        return 0.0
    observed = sum(1 for v in original_values if v is None) / max(1, len(original_values))
    base = observed if observed > 0 else 1.0 / max(n, 1)
    return max(base, 1.0 / max(n, 1))


def _sequential_pk(schema, table: str, column: str, n: int) -> list:
    start = _compact_max(schema, table, column) + 1
    return list(range(start, start + n))


def _generate_composite_pk(schema, inst, t, pk_cols, n, rng, cols, samplers):
    """Composite PK: first component sequential; remaining components sequential per first component."""
    first = pk_cols[0]
    tlow = (first.type_str or '').lower()
    if 'int' in tlow:
        if (t, first.name) in schema.fks:
            parent = inst.get(schema.fks[(t, first.name)][0], {})
            pcol = schema.fks[(t, first.name)][1]
            seq = [v for v in parent.get(pcol, []) if v is not None]
            if not seq:
                seq = []
        else:
            seq = _sequential_pk(schema, t, first.name, n)
    else:
        seq = [rng.choice(CHAR_PK_POOLS.get((t, first.name), ['x'])) for _ in range(n)]
    if len(seq) < n:
        seq = (seq + [rng.choice(seq) if seq else 1 for _ in range(n)])[:n]
    cols[first.name] = seq
    sub_counters = {}
    for c in pk_cols[1:]:
        name = c.name
        start = 0 if 'draft' in name.lower() else 1
        vals = []
        for v in seq:
            k = sub_counters.get((name, v), start)
            vals.append(k)
            sub_counters[(name, v)] = k + 1
        cols[name] = vals


def _fill_foreign_keys(schema, inst, table, n, rng, cols):
    """Fill FK columns."""
    by_parent: dict = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        by_parent.setdefault((pt, (pc,)), []).append(cm.name)

    parent_composites: dict = {}
    for (pt, pcs), children in list(by_parent.items()):
        pmeta = schema.tables[pt]
        if len(pmeta.primary_key) > 1 and all(c in pmeta.primary_key for c in pcs):
            parent_composites.setdefault(pt, []).append((tuple(pcs), children))

    handled = set()
    for pt, groups in parent_composites.items():
        pmeta = schema.tables[pt]
        pk_tuple = tuple(pmeta.primary_key)
        child_cols = []
        for cm in schema.tables[table].columns:
            pt2, pc2 = schema.fks.get((table, cm.name), (None, None))
            if pt2 == pt and pc2 in pk_tuple:
                child_cols.append((pc2, cm.name))
        if len(child_cols) >= 2:
            tuples = _parent_tuples(schema, inst, pt, list(pk_tuple))
            if tuples:
                usable = tuples[:max(1, len(tuples) - 1)] if len(tuples) > 1 else tuples
                if len(usable) >= 3 and n >= 6:
                    idxs = _child_counts_for_group_sizes(n, len(usable), rng)
                    chosen = [usable[i] for i in idxs]
                else:
                    chosen = [rng.choice(usable) for _ in range(n)]
                for pcol, ccol in child_cols:
                    idx = list(pk_tuple).index(pcol)
                    cols[ccol] = [tup[idx] if tup else None for tup in chosen]
                handled.update(ccol for _, ccol in child_cols)
                handled.add(pt)

    for cm in schema.tables[table].columns:
        if cm.name in handled:
            continue
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        vals = _parent_keys(schema, inst, pt, pc)
        if not vals:
            cols[cm.name] = [None] * n
            continue
        if (table, cm.name) in GROUP_SIZE and len(set(vals)) >= 3 and n >= 6:
            chosen = _parent_keys_with_group_sizes(schema, inst, pt, pc, n, rng)
        else:
            uniq = list(dict.fromkeys(vals))
            usable = uniq[:max(1, len(uniq) - 1)] if len(uniq) > 1 else uniq
            chosen = [rng.choice(usable) for _ in range(n)]
        cols[cm.name] = chosen


def choose_table_sizes(schema, rng) -> dict:
    return {t: table_size(t, rng) for t in schema.tables}


def _apply_guaranteed_literals(inst, rng) -> None:
    """Guarantee at least one occurrence of listed exact literals for non-key columns."""
    for (tbl, col), literals in GUARANTEED_LITERALS.items():
        colv = inst.get(tbl, {}).get(col)
        if not colv:
            continue
        for lit in literals:
            if lit not in colv:
                j = rng.randrange(len(colv))
                colv[j] = lit


def _apply_group_size_hints(inst, schema, rng) -> None:
    """For non-key grouping columns, force at least one group of size 1, 2, and >=3."""
    targets = {('Employees', 'role_code'), ('Roles', 'role_description'), ('Roles', 'role_code')}
    for (tbl, col) in targets:
        colv = inst.get(tbl, {}).get(col)
        if not colv:
            continue
        pool = list({v for v in colv if v is not None})
        if len(pool) < 3:
            continue
        assignments = [(pool[0], 1), (pool[1], 2), (pool[2], 3)]
        i = 0
        for val, c in assignments:
            for _ in range(c):
                if i < len(colv):
                    colv[i] = val
                    i += 1


def _apply_dup_distinct_hints(inst, rng) -> None:
    """Introduce a 20-50% duplicate share for non-key columns whose DISTINCT patterns matter."""
    for (tbl, col) in DUP_DISTINCT_TARGETS:
        colv = inst.get(tbl, {}).get(col)
        if not colv:
            continue
        non_null = [v for v in colv if v is not None]
        if len(non_null) < 2:
            continue
        dup_count = max(1, int(round(len(colv) * DUP_DISTINCT_SHARE)))
        base = non_null[0]
        slots = [i for i, v in enumerate(colv) if v is not None]
        rng.shuffle(slots)
        for i in slots[:dup_count]:
            colv[i] = base


def _reserve_parent_without_children(inst, schema, rng) -> None:
    """Ensure at least one Documents row has no children in any child table."""
    if 'Documents' not in inst:
        return
    doc_ids = [v for v in inst['Documents'].get('document_id', []) if v is not None]
    if not doc_ids:
        return
    child_tables = ['Document_Drafts', 'Draft_Copies', 'Circulation_History', 'Documents_Mailed']
    referenced = set()
    for t in child_tables:
        referenced.update(v for v in inst.get(t, {}).get('document_id', []) if v is not None)
    unreferenced = [d for d in doc_ids if d not in referenced]
    if unreferenced:
        return
    reserve = rng.choice(doc_ids)
    alternatives = [d for d in doc_ids if d != reserve]
    if not alternatives:
        return
    for t in child_tables:
        col = inst.get(t, {}).get('document_id')
        if not col:
            continue
        for i, v in enumerate(col):
            if v == reserve:
                col[i] = rng.choice(alternatives)


def _force_nulls_and_nonnulls(inst, schema, rng) -> None:
    """Guarantee at least one NULL and one non-NULL per nullable column (after all hint application)."""
    for (tbl, col) in NULL_TARGETS:
        cm = next((c for c in schema.tables[tbl].columns if c.name == col), None)
        if cm is None or cm.notnull or cm.pk_pos > 0:
            continue
        colv = inst.get(tbl, {}).get(col)
        if not colv:
            continue
        nn = [i for i, v in enumerate(colv) if v is not None]
        nul = [i for i, v in enumerate(colv) if v is None]
        if not nul:
            j = rng.randrange(len(colv))
            colv[j] = None
            nul = [j]
        if not nn:
            val = None
            if (tbl, col) in schema.fks:
                pts = _parent_keys(schema, inst, *schema.fks[(tbl, col)])
                val = rng.choice(pts) if pts else 'x'
            elif (tbl, col) in {k for k in GUARANTEED_LITERALS}:
                val = GUARANTEED_LITERALS[(tbl, col)][0]
            else:
                val = 'a'
            j = rng.randrange(len(colv))
            colv[j] = val
        inst[tbl][col] = colv
