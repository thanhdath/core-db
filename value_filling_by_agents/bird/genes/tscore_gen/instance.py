"""Random instance construction (fuzz/fuzz.py:83-196)."""
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
    for u in table_meta.uniques:
        if all(c in columns for c in u):
            seen, keep = set(), []
            for i in range(len(next(iter(columns.values())))):
                k = tuple(columns[c][i] for c in u)
                if k not in seen:
                    seen.add(k)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
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


def _fresh_key(rng, used: set, prefix: str = 'G', digits: int = 6) -> str:
    """Fresh 'G' + 6 digits token not in used."""
    for _ in range(10000):
        v = prefix + ('%0*d' % (digits, rng.randint(0, 10 ** digits - 1)))
        if v not in used:
            used.add(v)
            return v
    v = prefix + ('%0*d' % (digits, len(used) + 1))
    used.add(v)
    return v


def _compact_rows(schema, table: str) -> dict:
    """Compact rows of a table as a column->list dict (read from original_values)."""
    tm = schema.tables[table]
    return {cm.name: list(schema.original_values.get((table, cm.name), [])) for cm in tm.columns}


def _compact_null_share(schema, table: str, col: str) -> float:
    """Observed NULL share of a nullable column in the compact database."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _plant_nulls(columns: dict, table: str, col: str, share: float, rng) -> None:
    """Set NULL on a share of generated rows (at least one) for a nullable column."""
    vals = columns.get(col)
    if not vals:
        return
    n = len(vals)
    k = max(1, int(round(n * share)))
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs[:k]:
        vals[i] = None


def _apply_copy_rules(instance: dict, schema, table: str, columns: dict) -> None:
    """Compute copied columns from the parent row via FK; parent must exist (asserted)."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        for pcm in schema.tables[pt].columns:
            if pcm.name == cm.name and pcm.name != pc:
                parent_vals = instance.get(pt, {}).get(pcm.name) or []
                parent_keys = instance.get(pt, {}).get(pc) or []
                lookup = {}
                for k, v in zip(parent_keys, parent_vals):
                    lookup.setdefault(k, v)
                child_keys = columns.get(pc) or []
                copied = []
                for ck in child_keys:
                    if ck in lookup:
                        copied.append(lookup[ck])
                    else:
                        copied.append(None)
                columns[cm.name] = copied


def _assert_copy_invariant(instance: dict, schema, table: str) -> None:
    """Assert copied columns equal the parent's value for every row with a parent."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        for pcm in schema.tables[pt].columns:
            if pcm.name == cm.name and pcm.name != pc:
                parent_vals = instance.get(pt, {}).get(pcm.name) or []
                parent_keys = instance.get(pt, {}).get(pc) or []
                lookup = {}
                for k, v in zip(parent_keys, parent_vals):
                    lookup.setdefault(k, v)
                child_keys = instance.get(table, {}).get(pc) or []
                child_vals = instance.get(table, {}).get(cm.name) or []
                for ck, cv in zip(child_keys, child_vals):
                    if ck in lookup and cv != lookup[ck]:
                        raise AssertionError('copy invariant violated on %s.%s' % (table, cm.name))


def _plant_group_sizes(columns: dict, col: str, rng) -> bool:
    """Plant group sizes 1, 2, >=3 on a non-unique column (after copy rule)."""
    vals = columns.get(col)
    if not vals or len(vals) < 6:
        return False
    pool = list(dict.fromkeys([v for v in vals if v is not None]))
    if len(pool) < 3:
        return False
    chosen = rng.sample(pool, 3)
    g1, g2, g3 = chosen
    n = len(vals)
    idxs = list(range(n))
    rng.shuffle(idxs)
    vals[idxs[0]] = g1
    vals[idxs[1]] = g2
    vals[idxs[2]] = g2
    vals[idxs[3]] = g3
    vals[idxs[4]] = g3
    vals[idxs[5]] = g3
    return True


def _assert_group_sizes(columns: dict, col: str) -> None:
    """Assert group sizes 1, 2, >=3 exist on the final row set."""
    vals = [v for v in columns.get(col) or [] if v is not None]
    if len(vals) < 6:
        return
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    sizes = set(counts.values())
    if not (1 in sizes and 2 in sizes and any(s >= 3 for s in sizes)):
        raise AssertionError('group sizes lost on %s' % col)


def _plant_tie(columns: dict, col: str, compact_vals: list, rng) -> bool:
    """Plant at least two rows at the global max of the combined (compact + generated) set."""
    vals = columns.get(col)
    if not vals:
        return False
    combined = [v for v in list(compact_vals) + list(vals) if v is not None]
    if not combined:
        return False
    try:
        top = max(combined)
    except TypeError:
        return False
    n = len(vals)
    idxs = list(range(n))
    rng.shuffle(idxs)
    planted = 0
    for i in idxs:
        if vals[i] != top:
            vals[i] = top
            planted += 1
        if planted >= 2:
            break
    return planted >= 2


def _assert_tie(columns: dict, col: str, compact_vals: list) -> None:
    """Assert at least two generated rows at the global max."""
    vals = [v for v in columns.get(col) or [] if v is not None]
    combined = [v for v in list(compact_vals) + vals if v is not None]
    if not combined:
        return
    try:
        top = max(combined)
    except TypeError:
        return
    if sum(1 for v in vals if v == top) < 2:
        raise AssertionError('tie lost on %s' % col)


def _plant_different_values(columns: dict, group_col: str, val_col: str, rng) -> bool:
    """For each group in group_col, ensure >= 2 distinct val_col values."""
    groups = columns.get(group_col) or []
    vals = columns.get(val_col) or []
    if not groups or len(groups) != len(vals):
        return False
    by_group = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    planted_any = False
    for g, idxs in by_group.items():
        if len(idxs) < 2:
            continue
        distinct = {vals[i] for i in idxs}
        if len(distinct) >= 2:
            continue
        base = vals[idxs[0]]
        try:
            bf = float(base)
        except (TypeError, ValueError):
            continue
        newv = None
        for delta in (0.01, 0.05, 0.1, 0.25, 0.5):
            for cand in (bf + delta, bf - delta):
                cand = min(1.0, max(0.0, cand))
                if cand != bf:
                    newv = cand
                    break
            if newv is not None:
                break
        if newv is None:
            newv = rng.uniform(0.0, 1.0)
            if newv == bf:
                newv = 0.0 if bf != 0.0 else 1.0
        vals[idxs[1]] = newv
        if vals[idxs[1]] != vals[idxs[0]]:
            planted_any = True
    return planted_any


def _assert_different_values(columns: dict, group_col: str, val_col: str) -> None:
    groups = columns.get(group_col) or []
    vals = columns.get(val_col) or []
    by_group = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    for g, idxs in by_group.items():
        if len(idxs) >= 2 and len({vals[i] for i in idxs}) < 2:
            raise AssertionError('different values lost on %s by %s' % (val_col, group_col))


def _sample_table(schema, table: str, n: int, rng, spec: dict, instance: dict) -> dict:
    """Sample n rows for one table; FK columns draw from parent rows in instance."""
    tm = schema.tables[table]
    columns = {}
    for cm in tm.columns:
        key = (table, cm.name)
        observed = list(schema.original_values.get(key, []))
        enum_pool = spec.get('enum_pools', {}).get(key)
        boundary = spec.get('boundary', {}).get(key, [])
        rng_range = spec.get('ranges', {}).get(key)
        dup_share = spec.get('dup_share', {}).get(key, 0.0)
        if key in schema.fks:
            pt, pc = schema.fks[key]
            pv = instance.get(pt, {}).get(pc) or []
            if pv:
                columns[cm.name] = [rng.choice(pv) for _ in range(n)]
            else:
                columns[cm.name] = [None] * n
            continue
        s = _init_sampler(cm, [], observed, 0.2, rng, 1 if cm.pk_pos else 0,
                          enum_pool=enum_pool, rng_range=rng_range, boundary=boundary, dup_share=dup_share)
        columns[cm.name] = [s.sample() for _ in range(n)]
    return columns


def _compact_columns(schema, table: str) -> dict:
    """Compact rows as column->list."""
    return _compact_rows(schema, table)


def _append(instance: dict, table: str, gen: dict) -> None:
    """Append generated columns to the instance's compact columns (fixed column order)."""
    for c in gen:
        instance[table].setdefault(c, [])
        instance[table][c].extend(gen[c])


def _plant_unmatched_parent(instance: dict, schema, rng) -> None:
    """Ensure at least one Classification key has no Genes child and no Interactions child."""
    cls = instance.get('Classification')
    if not cls or 'GeneID' not in cls:
        return
    cls_keys = list(cls['GeneID'])
    genes_keys = set(instance.get('Genes', {}).get('GeneID') or [])
    inter_keys = set(instance.get('Interactions', {}).get('GeneID1') or [])
    inter_keys |= set(instance.get('Interactions', {}).get('GeneID2') or [])
    unmatched = [k for k in cls_keys if k not in genes_keys and k not in inter_keys]
    if unmatched:
        return
    used = set(cls_keys)
    new_key = _fresh_key(rng, used, 'G', 6)
    loc_pool = list(dict.fromkeys([v for v in (cls.get('Localization') or []) if v is not None]))
    new_loc = rng.choice(loc_pool) if loc_pool else 'cytoplasm'
    for c in cls:
        if c == 'GeneID':
            cls[c].append(new_key)
        elif c == 'Localization':
            cls[c].append(new_loc)
        else:
            cls[c].append(None)
    genes_keys = set(instance.get('Genes', {}).get('GeneID') or [])
    inter_keys = set(instance.get('Interactions', {}).get('GeneID1') or [])
    inter_keys |= set(instance.get('Interactions', {}).get('GeneID2') or [])
    if not any(k not in genes_keys and k not in inter_keys for k in cls['GeneID']):
        raise AssertionError('unmatched-parent target lost')


def build_random_instance(schema, pool: dict, _unused, rng, spec=None) -> dict:
    """Build one instance: compact rows kept verbatim + appended generated rows."""
    spec = spec or {}
    sizes = choose_table_sizes(schema, rng)
    instance = {}
    for t in schema.tables:
        instance[t] = _compact_columns(schema, t)
    cls_tm = schema.tables.get('Classification')
    cls_keys = list(instance.get('Classification', {}).get('GeneID') or [])
    used_keys = set(cls_keys)
    if cls_tm is not None:
        n = sizes.get('Classification', 0)
        gen = _sample_table(schema, 'Classification', n, rng, spec, instance)
        gen['GeneID'] = [_fresh_key(rng, used_keys, spec.get('id_format', {}).get('prefix', 'G'),
                                    spec.get('id_format', {}).get('digits', 6)) for _ in range(n)]
        for cm in cls_tm.columns:
            if not cm.notnull and cm.pk_pos == 0:
                share = _compact_null_share(schema, 'Classification', cm.name)
                _plant_nulls(gen, 'Classification', cm.name, share, rng)
        gen = sample_fresh_primary_keys(cls_tm, gen)
        gen = drop_unique_duplicates(cls_tm, gen)
        _append(instance, 'Classification', gen)
        cls_keys = list(instance['Classification'].get('GeneID') or [])
        used_keys = set(cls_keys)
    genes_tm = schema.tables.get('Genes')
    if genes_tm is not None:
        n = sizes.get('Genes', 0)
        gen = _sample_table(schema, 'Genes', n, rng, spec, instance)
        gen['GeneID'] = [rng.choice(cls_keys) for _ in range(n)] if cls_keys else []
        for cm in genes_tm.columns:
            if not cm.notnull and cm.pk_pos == 0 and (('Genes', cm.name) not in schema.fks):
                share = _compact_null_share(schema, 'Genes', cm.name)
                _plant_nulls(gen, 'Genes', cm.name, share, rng)
        gen = sample_fresh_primary_keys(genes_tm, gen)
        gen = drop_unique_duplicates(genes_tm, gen)
        _apply_copy_rules(instance, schema, 'Genes', gen)
        planted_gs = {}
        for (t, c) in spec.get('group_size_targets', []):
            if t == 'Genes' and c in gen:
                planted_gs[c] = _plant_group_sizes(gen, c, rng)
        planted_tie = {}
        for (t, c) in spec.get('tie_targets', []):
            if t == 'Genes' and c in gen:
                planted_tie[c] = _plant_tie(gen, c, list(schema.original_values.get((t, c), [])), rng)
        _append(instance, 'Genes', gen)
        _assert_copy_invariant(instance, schema, 'Genes')
        for (t, c) in spec.get('group_size_targets', []):
            if t == 'Genes' and planted_gs.get(c) and c in instance['Genes']:
                _assert_group_sizes(instance['Genes'], c)
        for (t, c) in spec.get('tie_targets', []):
            if t == 'Genes' and planted_tie.get(c) and c in instance['Genes']:
                _assert_tie(instance['Genes'], c, list(schema.original_values.get((t, c), [])))
    inter_tm = schema.tables.get('Interactions')
    if inter_tm is not None:
        n = sizes.get('Interactions', 0)
        gen = _sample_table(schema, 'Interactions', n, rng, spec, instance)
        gen['GeneID1'] = [rng.choice(cls_keys) for _ in range(n)] if cls_keys else []
        gen['GeneID2'] = [rng.choice(cls_keys) for _ in range(n)] if cls_keys else []
        for cm in inter_tm.columns:
            if not cm.notnull and cm.pk_pos == 0 and (('Interactions', cm.name) not in schema.fks):
                share = _compact_null_share(schema, 'Interactions', cm.name)
                _plant_nulls(gen, 'Interactions', cm.name, share, rng)
        gen = sample_fresh_primary_keys(inter_tm, gen)
        gen = drop_unique_duplicates(inter_tm, gen)
        planted_dv = {}
        for (t, c) in spec.get('different_value_targets', []):
            if t == 'Interactions' and c in gen:
                planted_dv[c] = _plant_different_values(gen, 'GeneID1', c, rng)
        planted_tie = {}
        for (t, c) in spec.get('tie_targets', []):
            if t == 'Interactions' and c in gen:
                planted_tie[c] = _plant_tie(gen, c, list(schema.original_values.get((t, c), [])), rng)
        _append(instance, 'Interactions', gen)
        for (t, c) in spec.get('different_value_targets', []):
            if t == 'Interactions' and planted_dv.get(c) and c in instance['Interactions']:
                _assert_different_values(instance['Interactions'], 'GeneID1', c)
        for (t, c) in spec.get('tie_targets', []):
            if t == 'Interactions' and planted_tie.get(c) and c in instance['Interactions']:
                _assert_tie(instance['Interactions'], c, list(schema.original_values.get((t, c), [])))
    _plant_unmatched_parent(instance, schema, rng)
    return instance
