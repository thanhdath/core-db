"""Random instance construction (fuzz/fuzz.py:83-196), adapted to the specification."""
from . import spec
from .values import make_spec_sampler


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


def _parent_pool(instance: dict, schema, pt: str, pc: str, compact: dict) -> list:
    """Parent values: compact rows first, then generated rows (kept in memory)."""
    vals = list(compact.get((pt, pc), []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _generated_parent_pool(instance: dict, pt: str, pc: str) -> list:
    """Generated parent key values only (used by copy-rule child FKs)."""
    return [v for v in instance.get(pt, {}).get(pc, []) if v is not None]


def _generated_parent_rows(instance: dict, pt: str) -> list:
    """Generated parent rows (dicts) only, keyed by their generated key values."""
    gen = instance.get(pt, {})
    if not gen:
        return []
    n = len(next(iter(gen.values())))
    return [{c: gen.get(c, [None] * n)[i] for c in gen} for i in range(n)]


def _copy_rule_columns(table: str) -> set:
    """Child columns that are populated by a copy rule (excluded from the NULL rule)."""
    out = set()
    for (ct, cc), (pt, pc, copied) in spec.COPY_RULES.items():
        if ct == table:
            out.update(copied)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact: dict) -> dict:
    """FK child columns draw from the parent's values with replacement; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        if key in spec.COPY_RULES:
            pv = _generated_parent_pool(instance, pt, pc)
            if not pv:
                pv = _parent_pool(instance, schema, pt, pc, compact)
        else:
            pv = _parent_pool(instance, schema, pt, pc, compact)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def apply_copy_rules(instance: dict, schema, table: str, cols: dict, rng, compact: dict) -> None:
    """Copy child columns from the generated parent row selected by the FK (spec.COPY_RULES)."""
    for cm in schema.tables[table].columns:
        rule = spec.copy_rule_for(table, cm.name)
        if rule is None:
            continue
        pt, pc, copied = rule
        if cm.name not in cols:
            continue
        rows = _generated_parent_rows(instance, pt)
        if not rows:
            continue
        by_key = {}
        for r in rows:
            by_key.setdefault(r.get(pc), r)
        for child_col in copied:
            if child_col not in cols:
                continue
            new_vals = []
            for fk in cols[cm.name]:
                parent = by_key.get(fk)
                new_vals.append(parent.get(child_col) if parent is not None else None)
            cols[child_col] = new_vals


def _check_copy_rules(table: str, cols: dict, instance: dict) -> int:
    """Count violations: copied column NULL while the FK is non-NULL and the parent value is non-NULL."""
    bad = 0
    for (ct, cc), (pt, pc, copied) in spec.COPY_RULES.items():
        if ct != table:
            continue
        fk_vals = cols.get(cc)
        if fk_vals is None:
            continue
        parent = instance.get(pt, {})
        pkey = parent.get(pc, [])
        by_key = {}
        for i, k in enumerate(pkey):
            by_key.setdefault(k, i)
        for child_col in copied:
            cv = cols.get(child_col)
            if cv is None:
                continue
            pcol = parent.get(child_col, [])
            for fk, v in zip(fk_vals, cv):
                if fk is None or v is not None:
                    continue
                pi = by_key.get(fk)
                if pi is not None and pi < len(pcol) and pcol[pi] is not None:
                    bad += 1
    return bad


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (230 rows per table), with a small per-instance jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.table_size(t)
        jitter = rng.randint(-20, 20)
        sizes[t] = max(0, base + jitter)
    return sizes


def _apply_null_rule(table: str, column: str, values: list, rng) -> list:
    """Plant NULLs following the compact share; at least one NULL per nullable column."""
    share = spec.null_share(table, column)
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    n_null = int(round(share * n))
    if n_null == 0:
        n_null = 1
    n_null = min(n_null, n)
    idx = rng.sample(range(n), n_null)
    for i in idx:
        out[i] = None
    return out


def _enforce_rule(table: str, column: str, values: list, rng) -> list:
    """Enforce the semantic rule by construction (only non-NULL operands are constrained)."""
    rule = spec.rule_for(table, column)
    if rule is None:
        return values
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if rule[0] == 'range':
            lo, hi = rule[1], rule[2]
            try:
                f = float(v)
            except (TypeError, ValueError):
                out.append(v)
                continue
            if f < lo or f > hi:
                f = max(lo, min(hi, f))
            out.append(int(round(f)) if isinstance(lo, int) and isinstance(hi, int) else round(f, 1))
        elif rule[0] == 'min':
            lo = rule[1]
            try:
                f = float(v)
            except (TypeError, ValueError):
                out.append(v)
                continue
            if f < lo:
                f = lo
            out.append(int(round(f)) if isinstance(lo, int) else f)
        elif rule[0] == 'enum':
            if spec.enum_accepts(rule, v):
                out.append(v)
            else:
                out.append(rng.choice(rule[1]))
        elif rule[0] == 'flag':
            out.append(v if v in ('X', None) else 'X')
        else:
            out.append(v)
    return out


def _fresh_pk_values(table: str, table_meta, n: int, compact: dict, rng) -> dict:
    """Sequential unique integers for integer PK columns; non-integer PK columns are left to the enum samplers (they
    are part of a composite key, e.g. state_sector_details.level)."""
    out = {}
    for c in table_meta.primary_key:
        cm = next((x for x in table_meta.columns if x.name == c), None)
        if cm is None:
            continue
        t = (cm.type_str or '').lower()
        if 'int' not in t:
            continue
        existing = [v for v in compact.get((table, c), []) if isinstance(v, int)]
        start = (max(existing) + 1) if existing else 1
        out[c] = list(range(start, start + n))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    compact = schema.original_values
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and 'int' in (cm.type_str or '').lower():
                continue
            samplers[(t, cm.name)] = make_spec_sampler(
                t, cm.name, cm, literal_pool.get((t, cm.name), []),
                compact.get((t, cm.name), []), rng)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0 and 'int' in (cm.type_str or '').lower():
                continue
            s = samplers[(t, cm.name)]
            vals = [s.sample() for _ in range(n)]
            vals = _enforce_rule(t, cm.name, vals, rng)
            cols[cm.name] = vals
        pk_vals = _fresh_pk_values(t, tm, n, compact, rng)
        cols.update(pk_vals)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact))
        copied_cols = _copy_rule_columns(t)
        for cm in tm.columns:
            if cm.pk_pos > 0:
                continue
            if cm.name not in cols:
                continue
            if cm.notnull:
                continue
            if cm.name in copied_cols:
                continue
            cols[cm.name] = _apply_null_rule(t, cm.name, cols[cm.name], rng)
        apply_copy_rules(inst, schema, t, cols, rng, compact)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        bad = _check_copy_rules(t, cols, inst)
        if bad:
            raise AssertionError('copy-rule violation in %s: %d rows' % (t, bad))
    return {t: inst[t] for t in schema.tables}
