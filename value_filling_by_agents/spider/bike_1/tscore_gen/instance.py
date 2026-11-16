"""Random instance construction: compact rows + appended generated rows."""
import datetime as dt

from .spec import (copied_for, domain_for, is_nullable_column, like_patterns, null_share,
                   rules_for)
from .values import _init_sampler, _parse_date


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
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
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, parent: str, parent_col: str) -> list:
    """Parent key values (compact + generated) held in memory."""
    return instance.get(parent, {}).get(parent_col) or []


def _parent_lookup(instance: dict, schema, parent: str, parent_col: str) -> list:
    """Existing parent key values: generated rows first, then compact rows from the schema."""
    vals = []
    for v in _parent_pool(instance, parent, parent_col):
        if v is not None and v not in vals:
            vals.append(v)
    for v in schema.original_values.get((parent, parent_col), []):
        if v is not None and v not in vals:
            vals.append(v)
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   spec: dict) -> dict:
    """FK child columns draw only from existing parent rows, or are NULL by the NULL rule."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_lookup(instance, schema, pt, pc)
        share = null_share(schema, table, cm.name) if is_nullable_column(schema, table, cm.name) else 0.0
        vals = []
        for _ in range(n):
            if share > 0 and rng.random() < share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes with per-instance variation (0-230 rows, or level x 4 up to 2500)."""
    sizes = {}
    base = spec.get('sizes') or {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(30 * rng.random() + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    for t, n in base.items():
        if t in sizes and sizes[t] < 1:
            sizes[t] = 1
    return sizes


def _date_ge(a, b) -> bool:
    """True when datetime/date a >= b; unparsable values are treated as non-violations."""
    if a is None or b is None:
        return True
    _, da = _parse_date(str(a))
    _, db = _parse_date(str(b))
    if da is None or db is None:
        return str(a) >= str(b)
    return da >= db


def _apply_rules(table: str, cols: dict, spec: dict, rng, date_samplers: dict = None) -> dict:
    """Enforce semantic rules in Python; NULL operands are left untouched (three-valued logic)."""
    n = len(next(iter(cols.values()))) if cols else 0
    for (t, c, kind, arg) in rules_for(spec, table):
        if c not in cols:
            continue
        vals = cols[c]
        if kind == 'gt':
            cols[c] = [v if v is None or v > arg else arg + 1 + rng.randint(0, 2) for v in vals]
        elif kind == 'ge':
            cols[c] = [v if v is None or v >= arg else arg for v in vals]
        elif kind == 'between':
            lo, hi = arg
            cols[c] = [v if v is None or lo <= v <= hi else rng.randint(int(lo), int(hi)) for v in vals]
        elif kind == 'in':
            pool = list(arg)
            cols[c] = [v if v is None or v in pool else rng.choice(pool) for v in vals]
        elif kind == 'ge_col':
            other = cols.get(arg)
            if other is None:
                continue
            sampler = (date_samplers or {}).get(c)
            is_date = sampler is not None and hasattr(sampler, 'draw_ge')
            fixed = []
            for i in range(n):
                a, b = vals[i], other[i]
                if a is None or b is None:
                    fixed.append(a)
                elif is_date:
                    fixed.append(a if _date_ge(a, b) else sampler.draw_ge(b))
                elif a >= b:
                    fixed.append(a)
                else:
                    fixed.append(b)
            cols[c] = fixed
    return cols


def _apply_copied(table: str, cols: dict, instance: dict, spec: dict, schema=None) -> dict:
    """Copied name columns take the parent row's name for the sampled parent key."""
    for (child_col, pt, pc, copy_col) in copied_for(spec, table):
        if child_col not in cols or copy_col not in cols:
            continue
        parent = instance.get(pt, {})
        keys = list(parent.get(pc) or [])
        names = list(parent.get(copy_col) or [])
        if schema is not None:
            keys += list(schema.original_values.get((pt, pc), []))
            names += list(schema.original_values.get((pt, copy_col), []))
        lookup = {}
        for k, v in zip(keys, names):
            if k is not None and k not in lookup:
                lookup[k] = v
        vals = list(cols[copy_col])
        for i, k in enumerate(cols[child_col]):
            if k is None:
                vals[i] = None
            elif k in lookup:
                vals[i] = lookup[k]
        cols[copy_col] = vals
    return cols


def _ensure_null_rows(table: str, cols: dict, spec: dict, schema, rng) -> dict:
    """At least one NULL row per nullable column (planted NULLs are never replaced)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for c, vals in cols.items():
        is_pk = any(cm.name == c and cm.pk_pos > 0 for cm in schema.tables[table].columns)
        if is_pk or not is_nullable_column(schema, table, c):
            continue
        if any(v is None for v in vals):
            continue
        vals[rng.randrange(n)] = None
    return cols


def _init_pk_samplers(schema, spec, literal_pool, p, rng, samplers):
    """Primary-key samplers start at the compact max PK + 1 (disjoint from compact keys)."""
    for t, tm in schema.tables.items():
        for pk in tm.primary_key:
            key = (t, pk)
            cm = next((c for c in tm.columns if c.name == pk), None)
            if cm is None or key in samplers:
                continue
            dom = domain_for(spec, t, pk)
            if dom[0] != 'int_seq':
                continue
            mx = schema.pk_max.get(key)
            start = None
            if isinstance(mx, (int, float)):
                start = (mx + 1) if float(mx).is_integer() else (mx + 0.000001)
            samplers[key] = _init_sampler(cm, dom, literal_pool.get(key, []),
                                          schema.original_values.get(key, []), p, rng,
                                          1, float('inf'), 0.0, start)


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance: compact rows + generated rows (fuzz.py:111-196 adapted)."""
    if spec is None:
        from .spec import spec_from_columns
        spec = spec_from_columns(schema)
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    pk_keys = {(t, pk) for t, tm in schema.tables.items() for pk in tm.primary_key}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks or key in pk_keys:
                continue
            dom = domain_for(spec, t, cm.name)
            share = null_share(schema, t, cm.name) if is_nullable_column(schema, t, cm.name) else 0.0
            els = literal_pool.get(key, [])
            for (lt, lc, pat) in like_patterns(spec):
                if lt == t and lc == cm.name and dom and dom[0] == 'date':
                    els = list(els) + [p.replace('%', '') for p in [pat]]
            samplers[key] = _init_sampler(cm, dom, els,
                                          schema.original_values.get(key, []), p, rng,
                                          len(tm.primary_key), null_share=share)
    _init_pk_samplers(schema, spec, literal_pool, p, rng, samplers)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in samplers and key not in schema.fks:
                cols[cm.name] = [samplers[key].sample() for _ in range(n)]
        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = _parent_lookup(inst, schema, pt, pc)
            share = null_share(schema, t, cm.name) if is_nullable_column(schema, t, cm.name) else 0.0
            vals = []
            for _ in range(n):
                if share > 0 and rng.random() < share:
                    vals.append(None)
                elif pv:
                    vals.append(rng.choice(pv))
                else:
                    vals.append(None)
            cols[cm.name] = vals
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = [v for v in final if v is not None]
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(fs) if fs else None)
                                 for v in cols[cm.name]]
        cols = _apply_copied(t, cols, inst, spec, schema)
        cols = _apply_rules(t, cols, spec, rng, {c: samplers.get((t, c)) for c in cols})
        cols = _ensure_null_rows(t, cols, spec, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
