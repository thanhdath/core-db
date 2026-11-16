"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from . import spec
from .values import (DateSampler, _init_sampler, fmt_dt, parse_dt, perturb_int, perturb_text,
                     rand_dt)


def null_share_for(schema, table: str, col: str, default: float = 0.1) -> float:
    """Per-column NULL share from the compact database; fall back to `default` (at least one NULL)."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return default
    n_null = sum(1 for v in vals if v is None)
    share = n_null / float(len(vals))
    if share <= 0.0:
        return default
    return max(share, 1.0 / float(max(1, len(vals))))


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _min_len(columns: dict) -> int:
    """Minimum length across present columns (0 if empty)."""
    return min((len(v) for v in columns.values()), default=0)


def _truncate(columns: dict, n: int) -> dict:
    """Truncate every present column to n elements (column_length_invariant)."""
    return {c: list(v[:n]) for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (in-delta or against compact rows); first kept."""
    if not table_meta.primary_key or not columns:
        return columns
    pk_present = [c for c in table_meta.primary_key if c in columns]
    if not pk_present:
        return columns
    n = _min_len(columns)
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in pk_present)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value (in-delta or compact)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            n = _min_len(columns)
            seen, keep = set(existing.get(cm.name, ())), []
            for i in range(n):
                v = columns[cm.name][i]
                if v is None or v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_pk_set(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _compact_unique_sets(schema, table: str) -> dict:
    tm = schema.tables[table]
    out = {}
    for cm in tm.columns:
        if cm.unique:
            out[cm.name] = set(schema.original_values.get((table, cm.name), []))
    return out


def _next_int_pk(schema, table: str, n: int, rng) -> list:
    """Sequential integers starting after the compact max (never collide)."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) != 1:
        return None
    col = pk[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    start = (max(vals) + 1) if vals else 1
    return list(range(start, start + n))


def _plant_group_sizes(values: list, sizes: list, rng) -> list:
    """Overwrite the first sum(sizes) values so that groups of the requested sizes appear."""
    out = list(values)
    pos = 0
    for sz in sizes:
        if pos >= len(out):
            break
        base = out[pos]
        for k in range(sz):
            if pos + k < len(out):
                out[pos + k] = base
        pos += sz
    return out


def _plant_nulls(values: list, rng, share: float) -> list:
    """Ensure at least one NULL and ~share NULLs (NULL is a value to generate)."""
    out = list(values)
    if not out:
        return out
    k = max(1, int(round(len(out) * share)))
    idx = rng.sample(range(len(out)), min(k, len(out)))
    for i in idx:
        out[i] = None
    return out


def _plant_distinct_dups(values: list, rng, share: float) -> list:
    """Make ~share of values duplicates of earlier values (DISTINCT duplicate share)."""
    out = list(values)
    if len(out) < 2:
        return out
    k = max(1, int(round(len(out) * share)))
    for i in rng.sample(range(1, len(out)), min(k, len(out) - 1)):
        out[i] = out[rng.randrange(0, i)]
    return out


def _parent_column_pool(schema, pt: str, pc: str, generated: dict) -> list:
    """Non-NULL parent values from compact + generated rows (ordered)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(generated.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _fk_values(schema, table: str, col: str, n: int, rng, generated: dict, nullable: bool) -> list:
    """FK child column draws from parent rows (compact + generated) or NULL."""
    pt, pc = schema.fks[(table, col)]
    parent_vals = _parent_column_pool(schema, pt, pc, generated)
    if not parent_vals:
        return [None] * n
    out = [rng.choice(parent_vals) for _ in range(n)]
    if nullable:
        out = _plant_nulls(out, rng, null_share_for(schema, table, col))
    return out


def _parent_tuples(schema, pt: str, pcols: list, generated: dict) -> list:
    """Full parent tuples (compact + generated) for a composite FK target."""
    pvals = []
    for pc in pcols:
        pvals.append(list(schema.original_values.get((pt, pc), [])) + list(generated.get(pt, {}).get(pc, [])))
    m = min((len(v) for v in pvals), default=0)
    tuples = [tuple(v[i] for v in pvals) for i in range(m)]
    return [t for t in tuples if all(x is not None for x in t)]


def _composite_fk_columns(schema, table: str) -> list:
    """Group child columns by the (parent table) of their FK."""
    tm = schema.tables[table]
    groups: dict = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, _ = schema.fks[key]
        if pt == table:
            continue
        groups.setdefault(pt, []).append(cm.name)
    return {pt: cols for pt, cols in groups.items() if len(cols) > 1}


def apply_composite_fks(schema, table: str, cols: dict, rng, generated: dict) -> dict:
    """Re-derive composite-FK components from parent tuples AFTER per-column overrides."""
    out = dict(cols)
    groups = _composite_fk_columns(schema, table)
    if not groups:
        return out
    n = _min_len(out)
    for pt, child_cols in groups.items():
        pcols = [schema.fks[(table, c)][1] for c in child_cols]
        tuples = _parent_tuples(schema, pt, pcols, generated)
        tupset = set(tuples)
        any_nullable = any(not schema.tables[table].columns[
            next(i for i, c in enumerate(schema.tables[table].columns) if c.name == cname)].notnull
            for cname in child_cols)
        new_cols = {c: [None] * n for c in child_cols}
        for i in range(n):
            cur = tuple(out[c][i] if c in out else None for c in child_cols)
            if cur in tupset:
                continue
            if any(x is None for x in cur):
                for c in child_cols:
                    new_cols[c][i] = None
                continue
            if tuples:
                t = rng.choice(tuples)
                for c, v in zip(child_cols, t):
                    new_cols[c][i] = v
            else:
                if any_nullable:
                    for c in child_cols:
                        new_cols[c][i] = None
                else:
                    raise RuntimeError(
                        'no parent tuples for NOT NULL composite FK %s.%s' % (table, child_cols))
        for c in child_cols:
            out[c] = new_cols[c]
    return out


def apply_not_null_checks(schema, table: str, cols: dict) -> dict:
    """Drop rows violating NOT NULL (or whose primary key component is NULL); keep columns aligned."""
    tm = schema.tables[table]
    n = _min_len(cols)
    keep = []
    for i in range(n):
        ok = True
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if (not cm.notnull) and cm.pk_pos == 0:
                continue
            if cols[cm.name][i] is None:
                ok = False
                break
        if ok:
            keep.append(i)
    return _filter(cols, keep)


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes with per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.BASE_SIZES.get(t, 10)
        jitter = rng.randint(-3, 3)
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _sync_lengths(cols: dict) -> dict:
    """Force every present column to the same minimal length (column_length_invariant)."""
    return _truncate(cols, _min_len(cols))


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random *delta* instance (fuzz.py:111-196) implementing the specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}

        seq = _next_int_pk(schema, t, n, rng)
        if seq is not None:
            cols[tm.primary_key[0]] = seq
            n = len(seq)

        composite_child_cols = set()
        for pt, ccols in _composite_fk_columns(schema, t).items():
            composite_child_cols.update(ccols)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            if pt == t:
                continue
            if cm.name in composite_child_cols:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            cols[cm.name] = _fk_values(schema, t, cm.name, n, rng, inst, nullable)

        for (gt, gc), sizes in spec.GROUP_SIZE_TARGETS.items():
            if gt == t and gc in cols and cols[gc]:
                cols[gc] = _plant_group_sizes(cols[gc], sizes, rng)

        for (dt_t, dt_c) in spec.DISTINCT_DUP_TARGETS:
            if dt_t == t and dt_c in cols and cols[dt_c] and dt_c not in tm.primary_key:
                cols[dt_c] = _plant_distinct_dups(cols[dt_c], rng, spec.DISTINCT_DUP_SHARE)

        for (nt, nc) in spec.NULL_TARGETS:
            if nt == t and nc in cols:
                cols[nc] = _plant_nulls(cols[nc], rng, null_share_for(schema, t, nc))

        if t == 'Residents':
            din = [parse_dt(v) for v in cols.get('date_moved_in', [])]
            dout = []
            for d in din:
                if d is None:
                    dout.append(fmt_dt(rand_dt(rng)))
                else:
                    dout.append(fmt_dt(rand_dt(rng, d, spec.DATE_HI)))
            if 'date_moved_out' in cols:
                cols['date_moved_out'] = dout
        if t == 'Residents_Services':
            req = cols.get('date_requested', [])
            prov = []
            for r in req:
                rd = parse_dt(r) if r is not None else None
                if rd is None:
                    prov.append(None)
                else:
                    prov.append(fmt_dt(rand_dt(rng, rd, spec.DATE_HI)))
            if 'date_provided' in cols:
                cols['date_provided'] = prov
        if t == 'Customer_Events':
            if 'date_moved_in' in cols and 'customer_id' in cols:
                for i in range(_min_len(cols)):
                    if cols['date_moved_in'][i] is None and cols['customer_id'][i] is not None:
                        cols['date_moved_in'][i] = fmt_dt(rand_dt(rng))

        if t == 'Residents_Services' and 'resident_id' in cols and cols['resident_id']:
            n_cur = _min_len(cols)
            k = max(1, n_cur // 4)
            for _ in range(k):
                if n_cur == 0:
                    break
                i = rng.randrange(n_cur)
                for c in cols:
                    if c == 'service_id':
                        continue
                    cols[c].append(cols[c][i])
            if 'service_id' in cols:
                base = list(cols['service_id'])
                while len(cols['service_id']) < _min_len(cols):
                    cols['service_id'].append(rng.choice(base) if base else 0)

        cols = apply_composite_fks(schema, t, cols, rng, inst)

        cols = _sync_lengths(cols)

        cols = apply_not_null_checks(schema, t, cols)

        cols = sample_fresh_primary_keys(tm, cols, _compact_pk_set(schema, t))
        cols = drop_unique_duplicates(tm, cols, _compact_unique_sets(schema, t))

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and cm.name in cols and pc in cols:
                final = [v for v in cols[pc] if v is not None]
                fs = set(final)
                m = _min_len(cols)
                new_vals = []
                for i in range(m):
                    v = cols[cm.name][i]
                    if v is None or v in fs:
                        new_vals.append(v)
                    elif final:
                        new_vals.append(rng.choice(final))
                    else:
                        new_vals.append(None)
                cols[cm.name] = new_vals

        inst[t] = _sync_lengths(cols)
    return {t: inst[t] for t in schema.tables}
