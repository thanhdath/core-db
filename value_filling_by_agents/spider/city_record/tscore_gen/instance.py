"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import math

from .values import _init_sampler

_NULL_SHARE = 0.08


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_unique(columns: dict, table_meta, column: str) -> set:
    """Values already present in the compact table for a column."""
    return set(columns.get(column, []))


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pk: set) -> dict:
    """Drop rows whose PK tuple repeats the compact PK or a generated PK."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(compact_pk), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_unique: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(compact_unique.get(cm.name, ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v in seen:
                    continue
                seen.add(v)
                keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's final key pool (compact + generated) with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes exactly; every table receives at least one generated row."""
    sizes = {}
    base = spec.get('table_sizes') or {}
    for lvl in schema.table_order:
        for t in lvl:
            b = int(base.get(t, max(1, schema.original_sizes.get(t, 0))))
            sizes[t] = max(1, min(b, 2500))
    return sizes


def _is_numeric_column(cm) -> bool:
    t = (cm.type_str or '').lower()
    return any(k in t for k in ('int', 'real', 'float', 'double', 'decimal', 'numeric', 'number'))


def _boundary_for(spec: dict, table: str, column: str) -> list:
    return list(spec.get('literal_pool', {}).get((table, column), []))


def _compact_null_share(schema, table: str, column: str) -> float:
    """NULL share of the compact column (0.0 when unknown)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _plant_nulls(cols: dict, tm, n: int, rng, spec: dict, schema: dict) -> None:
    """NULL rule: at least one NULL per nullable column, share from the compact DB."""
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        if (tm.name, cm.name) not in spec.get('null_targets', set()):
            continue
        if cm.name not in cols or n == 0:
            continue
        share = _compact_null_share(schema, tm.name, cm.name)
        if share <= 0.0:
            share = _NULL_SHARE
        k = max(1, int(round(n * share)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None


def _plant_ties(cols: dict, tm, column: str, ranks: list, rng) -> None:
    """Tie at the requested ranks under ORDER BY column DESC (numeric columns only)."""
    if column not in cols:
        return
    cm = next((c for c in tm.columns if c.name == column), None)
    if cm is None or not _is_numeric_column(cm):
        return
    vals = cols[column]
    n = len(vals)
    if n < 2:
        return
    for r in ranks:
        if r < 1 or r >= n:
            continue
        order = sorted(range(n), key=lambda i: (vals[i] is None, -(vals[i] if isinstance(vals[i], (int, float)) else 0)))
        i = order[r - 1]
        j = order[r]
        if vals[i] is None:
            continue
        vals[j] = vals[i]
        order2 = sorted(range(n), key=lambda k: (vals[k] is None, -(vals[k] if isinstance(vals[k], (int, float)) else 0)))
        if order2[r - 1] != i or order2[r] != j:
            lo = vals[order2[r - 2]] if r >= 2 else None
            hi = vals[order2[r + 1]] if r + 1 < n else None
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                mid = (lo + hi) / 2.0
            elif isinstance(lo, (int, float)):
                mid = lo - 1
            elif isinstance(hi, (int, float)):
                mid = hi + 1
            else:
                mid = 0
            vals[i] = vals[j] = mid


def _plant_group_sizes(cols: dict, tm, column: str, rng) -> None:
    """Group sizes 1, 2 and >= 3 under GROUP BY column, using distinct base values."""
    if column not in cols:
        return
    vals = cols[column]
    n = len(vals)
    if n < 6:
        return
    existing = [v for v in vals if v is not None]
    if len(existing) < 3:
        return
    base1, base2, base3 = existing[0], existing[1], existing[2]
    if len({base1, base2, base3}) < 3:
        return
    vals[0] = base1
    vals[1] = vals[2] = base2
    for i in range(3, min(n, 6)):
        vals[i] = base3


def _plant_duplicates(cols: dict, tm, column: str, share: tuple, rng) -> None:
    """Duplicates share: copy some values into other rows so DISTINCT reduces the count."""
    if column not in cols:
        return
    vals = cols[column]
    n = len(vals)
    if n < 2:
        return
    lo, hi = share
    target = max(1, int(round(n * rng.uniform(lo, hi))))
    target = min(target, n - 1)
    existing = [v for v in vals if v is not None]
    if not existing:
        return
    for i in range(target):
        vals[i] = existing[i % len(existing)]


def _plant_comparison_boundaries(cols: dict, tm, spec: dict, rng) -> None:
    """For temperature columns, plant equal / one-step values against referenced columns."""
    if tm.name != 'temperature':
        return
    pairs = spec.get('boundary_pairs', {})
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for (t, c), others in pairs.items():
        if t != tm.name or c not in cols:
            continue
        for j, (other, step) in enumerate(others):
            if other not in cols:
                continue
            i = j % n
            if i >= n:
                break
            va = cols[other][i]
            if va is None:
                continue
            try:
                f = float(va)
            except (TypeError, ValueError):
                continue
            cols[c][i] = round(f, 1)


def _plant_compound_predicates(cols: dict, tm, spec: dict, rng) -> None:
    """Make (Mar < Jul OR Mar > Oct) and (Jun < Oct OR Mar < Jun) both true and false."""
    if tm.name != 'temperature':
        return
    n = len(next(iter(cols.values()))) if cols else 0
    if n < 4:
        return
    if 'Mar' in cols and 'Jul' in cols and 'Oct' in cols:
        cols['Mar'][0] = 1.0
        cols['Jul'][0] = 2.0
        cols['Oct'][0] = 3.0
        cols['Mar'][1] = 5.0
        cols['Jul'][1] = 4.0
        cols['Oct'][1] = 6.0
    if 'Jun' in cols and 'Oct' in cols and 'Mar' in cols:
        cols['Jun'][2] = 1.0
        cols['Oct'][2] = 2.0
        cols['Mar'][2] = 3.0
        cols['Jun'][3] = 5.0
        cols['Oct'][3] = 4.0
        cols['Mar'][3] = 6.0


def _apply_formulas(cols: dict, tm, spec: dict, rng) -> None:
    """Enforce semantic formulas by construction (positive / nonnegative / between)."""
    for (t, c, kind, formula) in spec.get('formulas', []):
        if t != tm.name or c not in cols:
            continue
        vals = cols[c]
        if kind == 'positive':
            for i, v in enumerate(vals):
                if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                    vals[i] = abs(v) + 1 if isinstance(v, (int, float)) else 1
        elif kind == 'nonnegative':
            for i, v in enumerate(vals):
                if v is not None and isinstance(v, (int, float)) and v < 0:
                    vals[i] = abs(v)
        elif kind == 'between':
            lo, hi = 1990, 2030
            for i, v in enumerate(vals):
                if v is not None and isinstance(v, (int, float)) and not (lo <= v <= hi):
                    vals[i] = rng.randint(lo, hi)


def _ensure_parents_without_children(inst: dict, schema, spec: dict, rng) -> None:
    """Ensure at least one parent key is unused by children (never invent a parent key)."""
    for (ct, cc, pt, pc) in spec.get('dependencies', []):
        if ct not in inst or pt not in inst:
            continue
        child = inst[ct].get(cc)
        parent = inst[pt].get(pc)
        if not child or not parent or len(parent) < 2:
            continue
        childset = set(v for v in child if v is not None)
        if childset >= set(parent):
            for i, v in enumerate(child):
                if v in parent:
                    others = [k for k in parent if k != v]
                    if others:
                        child[i] = rng.choice(others)
                    break


def _compact_pk_set(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = schema.original_values
    n = len(tm.columns)
    out = set()
    for i in range(len(cols.get((table, tm.columns[0].name), []))):
        out.add(tuple(cols.get((table, c.name), [None] * (i + 1))[i] for c in tm.columns))
    return out


def _compact_unique(schema, table: str) -> dict:
    out = {}
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.unique:
            out[cm.name] = set(schema.original_values.get((table, cm.name), []))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                boundary = _boundary_for(spec, t, cm.name)
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), boundary=boundary)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        compact_pk = _compact_pk_set(schema, t)
        cols = sample_fresh_primary_keys(tm, cols, compact_pk)
        compact_unique = _compact_unique(schema, t)
        cols = drop_unique_duplicates(tm, cols, compact_unique)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        _apply_formulas(cols, tm, spec, rng)
        for (et, ec), excs in spec.get('exceptions', {}).items():
            if et != t:
                continue
            for exc in excs:
                pat = exc.get('pattern', '')
                if pat == 'ties_for_order_limit':
                    ranks = [1, 3]
                    tg = exc.get('targets')
                    if isinstance(tg, dict) and isinstance(tg.get('tie_at_rank'), list):
                        ranks = [int(x) for x in tg['tie_at_rank']]
                    _plant_ties(cols, tm, ec, ranks, rng)
                elif pat == 'group_sizes':
                    _plant_group_sizes(cols, tm, ec, rng)
                elif pat == 'duplicates_for_distinct':
                    _plant_duplicates(cols, tm, ec, spec.get('duplicate_targets', {}).get((t, ec), (0.2, 0.5)), rng)
                elif pat == 'comparison_boundary':
                    _plant_comparison_boundaries(cols, tm, spec, rng)
        _plant_compound_predicates(cols, tm, spec, rng)
    _ensure_parents_without_children(inst, schema, spec, rng)
    for t in order:
        tm = schema.tables[t]
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        _plant_nulls(cols, tm, n, rng, spec, schema)
    return {t: inst[t] for t in schema.tables}
