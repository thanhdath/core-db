"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler, _spec_hooks


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, reserved: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with compact rows), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(reserved), []
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
    """Parent values = compact values + generated values (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's FINAL values (compact + generated); empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec appended-row sizes per instance; fall back to upstream rand_lin/level sizes."""
    sizes = {}
    for t in schema.tables:
        if t in spec.TABLE_SIZES:
            sizes[t] = spec.TABLE_SIZES[t]
    if len(sizes) == len(schema.tables):
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                if t not in sizes:
                    min_c = 30 * rng.random()
                    sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                if t not in sizes:
                    sizes[t] = int(min(s, 2500))
                s *= 4
    return sizes


def _plant_nulls(table: str, columns: dict, schema, rng) -> dict:
    """NULL rule: for every nullable column, ~10% NULL rows and at least one NULL row."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.name not in columns or cm.pk_pos > 0 or cm.notnull:
            continue
        key = '%s.%s' % (table, cm.name)
        if key not in spec.NULL_TARGETS and (table, cm.name) not in schema.fks:
            continue
        k = max(1, int(round(n * spec.NULL_SHARE)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            columns[cm.name][i] = None
    return columns


def _apply_semantic_rules(table: str, columns: dict, schema, rng) -> dict:
    """Semantic formulas by construction (non-NULL operands only; NULLs never replaced)."""
    tm = schema.tables[table]
    names = {c.name.lower(): c.name for c in tm.columns}
    if table.lower() == 'people':
        h, w = names.get('height'), names.get('weight')
        if h in columns:
            columns[h] = [None if v is None else max(spec.HEIGHT_RANGE[0], min(spec.HEIGHT_RANGE[1], float(v)))
                          for v in columns[h]]
        if w in columns:
            columns[w] = [None if v is None else max(spec.WEIGHT_RANGE[0], min(spec.WEIGHT_RANGE[1], float(v)))
                          for v in columns[w]]
    if table.lower() == 'entrepreneur':
        m = names.get('money_requested')
        if m in columns:
            columns[m] = [None if v is None else max(spec.MONEY_MIN, float(v)) for v in columns[m]]
        inv = names.get('investor')
        if inv in columns:
            columns[inv] = [None if v is None else (v if v in spec.INVESTOR_ENUM or v == spec.INVESTOR_NEAR_VARIANT
                                                   else rng.choice(spec.INVESTOR_ENUM))
                            for v in columns[inv]]
    return columns


def _plant_boundaries(table: str, columns: dict, schema) -> dict:
    """Guarantee each Money_Requested boundary literal appears at least once (non-NULL slots)."""
    if table.lower() != 'entrepreneur':
        return columns
    names = {c.name.lower(): c.name for c in schema.tables[table].columns}
    m = names.get('money_requested')
    if m not in columns:
        return columns
    col = columns[m]
    slots = [i for i, v in enumerate(col) if v is not None]
    if not slots:
        return columns
    for j, b in enumerate(spec.MONEY_BOUNDARIES):
        col[slots[j % len(slots)]] = float(b)
    return columns


def _plant_ties(table: str, columns: dict, schema, rng) -> dict:
    """Plant >= 2 rows at the value occupying the listed LIMIT rank (tie_for_order_limit)."""
    names = {c.name.lower(): c.name for c in schema.tables[table].columns}
    if table.lower() == 'entrepreneur':
        m = names.get('money_requested')
        if m in columns:
            col = columns[m]
            slots = [i for i, v in enumerate(col) if v is not None]
            if len(slots) >= 2:
                vals = sorted((col[i] for i in slots), reverse=True)
                rank = min(spec.MONEY_TIE_RANK, len(vals)) - 1
                tie = vals[rank]
                for i in slots[:2]:
                    col[i] = tie
    if table.lower() == 'people':
        w = names.get('weight')
        if w in columns:
            col = columns[w]
            slots = [i for i, v in enumerate(col) if v is not None]
            if len(slots) >= 2:
                vals = sorted(col[i] for i in slots)
                rank = min(spec.WEIGHT_TIE_RANK, len(vals)) - 1
                tie = vals[rank]
                for i in slots[:2]:
                    col[i] = tie
    return columns


def _plant_group_sizes(table: str, columns: dict, schema, rng) -> dict:
    """Plant groups of size 1, 2 and >= 3 for GROUP-target columns (people_id, investor)."""
    names = {c.name.lower(): c.name for c in schema.tables[table].columns}
    if table.lower() != 'entrepreneur':
        return columns
    for cname in ('people_id', 'investor'):
        c = names.get(cname)
        if c not in columns:
            continue
        col = columns[c]
        slots = [i for i, v in enumerate(col) if v is not None]
        if len(slots) < 6:
            continue
        col[slots[0]] = col[slots[0]]
        col[slots[1]] = col[slots[2]]
        col[slots[3]] = col[slots[4]] = col[slots[5]]
    return columns


def _plant_duplicates(table: str, columns: dict, schema, rng) -> dict:
    """Plant duplicates so DISTINCT-target columns reach a 20-50% duplicate share."""
    names = {c.name.lower(): c.name for c in schema.tables[table].columns}
    if table.lower() != 'entrepreneur':
        return columns
    for cname in ('company', 'investor'):
        c = names.get(cname)
        if c not in columns:
            continue
        col = columns[c]
        slots = [i for i, v in enumerate(col) if v is not None]
        if len(slots) < 4:
            continue
        k = max(1, int(round(len(slots) * 0.30)))
        for i in slots[1:1 + k]:
            col[i] = col[slots[0]]
    return columns


def _remap_fks(instance: dict, schema, table: str, rng) -> dict:
    """Re-validate every non-NULL child FK value against the FINAL parent PK pool."""
    cols = instance.get(table, {})
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        pset = set(pv)
        if cm.name not in cols:
            continue
        out = []
        for v in cols[cm.name]:
            if v is None:
                out.append(None)
            elif v in pset:
                out.append(v)
            else:
                out.append(rng.choice(pv) if pv else None)
        cols[cm.name] = out
    instance[table] = cols
    return instance


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                hooks = _spec_hooks(t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), hooks=hooks)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        cols = _plant_nulls(t, cols, schema, rng)
        cols = _apply_semantic_rules(t, cols, schema, rng)
        cols = _plant_boundaries(t, cols, schema)
        cols = _plant_ties(t, cols, schema, rng)
        cols = _plant_group_sizes(t, cols, schema, rng)
        cols = _plant_duplicates(t, cols, schema, rng)
        reserved = set()
        if tm.primary_key:
            ov = schema.original_values
            m = len(ov.get((t, tm.primary_key[0]), []))
            for i in range(m):
                reserved.add(tuple(ov.get((t, c), [None] * m)[i] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols},
                                         reserved)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, len(next(iter(cols.values()))) if cols else 0, rng)
        for cname, vals in fk_cols.items():
            inst[t][cname] = vals
        inst = _remap_fks(inst, schema, t, rng)
    return {t: inst[t] for t in schema.tables}
