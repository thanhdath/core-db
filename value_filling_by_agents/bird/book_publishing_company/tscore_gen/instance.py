"""Random instance construction: append generated rows to a copy of the compact database."""
import datetime as dt

from . import spec
from .values import _init_sampler, _parse_date, _fmt_date


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _compact_pk_set(schema, table: str) -> set:
    """Set of compact primary-key tuples for a table."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pks: set = None) -> dict:
    """Drop rows whose PK tuple repeats (within batch or against compact rows)."""
    if not table_meta.primary_key or not columns:
        return columns
    compact_pks = compact_pks or set()
    n = _n_rows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k in seen or k in compact_pks:
            continue
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


def drop_unique_tuples(table: str, columns: dict) -> dict:
    """Drop rows repeating a composite unique tuple (spec.UNIQUE_TUPLES)."""
    for tup in spec.UNIQUE_TUPLES.get(table, []):
        if not all(c in columns for c in tup):
            continue
        seen, keep = set(), []
        for i in range(_n_rows(columns)):
            k = tuple(columns[c][i] for c in tup)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_values(schema, instance, table, column) -> list:
    """All values of a parent column: compact rows first, then generated rows."""
    vals = list(schema.original_values.get((table, column), []))
    vals += list(instance.get(table, {}).get(column, []))
    return [v for v in vals if v is not None]


def _null_share(schema, table, column) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.15
    return sum(1 for v in vals if v is None) / len(vals)


def _group_size_plan(n: int, rng) -> list:
    """Multiplicities for a group_sizes column: some 1, some 2, some >= 3."""
    plan = []
    while len(plan) < n:
        plan.extend([1, 2, 3, 3])
    plan = plan[:n]
    rng.shuffle(plan)
    return plan


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact or generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(schema, instance, pt, pc)
        nullable = not cm.notnull
        share = _null_share(schema, table, cm.name) if nullable else 0.0
        col = []
        null_emitted = 0
        nonnull_emitted = 0
        group_plan = None
        if spec.has_pattern(table, cm.name, 'group_sizes') and pv:
            group_plan = _group_size_plan(n, rng)
        gi = 0
        for i in range(n):
            want_null = False
            if nullable:
                if null_emitted == 0 and nonnull_emitted >= max(1, n - 1):
                    want_null = True
                elif null_emitted == 0 and n > 0 and rng.random() < 0.5:
                    want_null = True
                else:
                    want_null = rng.random() < share
            if want_null:
                null_emitted += 1
                col.append(None)
            elif pv:
                if group_plan is not None:
                    if gi == 0 or col[-1] is None:
                        cur = rng.choice(pv)
                        gi = group_plan[i] if i < len(group_plan) else 1
                    col.append(cur)
                    gi -= 1
                else:
                    col.append(rng.choice(pv))
                nonnull_emitted += 1
            else:
                col.append(None)
                null_emitted += 1
        out[cm.name] = col
    return out


def _apply_semantic_rules(schema, instance, table, rng) -> None:
    """Derived / dependent columns computed in Python from sampled values held in memory."""
    cols = instance.get(table, {})
    n = _n_rows(cols)
    if n == 0:
        return
    if table == 'jobs':
        for i in range(n):
            mn = cols['min_lvl'][i]
            mx = cols['max_lvl'][i]
            if mn is not None and mn < 0:
                cols['min_lvl'][i] = 0
                mn = 0
            if mx is not None and mn is not None and mx < mn:
                cols['max_lvl'][i] = mn
    elif table == 'employee':
        jobs = {}
        for jid, mn, mx in zip(instance.get('jobs', {}).get('job_id', []),
                               instance.get('jobs', {}).get('min_lvl', []),
                               instance.get('jobs', {}).get('max_lvl', [])):
            jobs[jid] = (mn, mx)
        for i in range(n):
            jid = cols['job_id'][i]
            lvl = cols['job_lvl'][i]
            if lvl is not None and jid in jobs:
                mn, mx = jobs[jid]
                if mn is not None and lvl < mn:
                    cols['job_lvl'][i] = mn
                elif mx is not None and lvl > mx:
                    cols['job_lvl'][i] = mx
    elif table == 'discounts':
        for i in range(n):
            lo = cols['lowqty'][i]
            hi = cols['highqty'][i]
            if lo is not None and lo < 0:
                cols['lowqty'][i] = 0
                lo = 0
            if hi is not None and lo is not None and hi < lo:
                cols['highqty'][i] = lo
    elif table == 'titles':
        for i in range(n):
            for c in ('price', 'advance', 'ytd_sales'):
                v = cols[c][i]
                if v is not None and v < 0:
                    cols[c][i] = 0
            r = cols['royalty'][i]
            if r is not None and (r < 0 or r > 100):
                cols['royalty'][i] = max(0, min(100, r))
    elif table == 'sales':
        for i in range(n):
            q = cols['qty'][i]
            if q is not None and q <= 0:
                cols['qty'][i] = 1
    elif table == 'titleauthor':
        for i in range(n):
            o = cols['au_ord'][i]
            if o is not None and o < 1:
                cols['au_ord'][i] = 1
            rp = cols['royaltyper'][i]
            if rp is not None and (rp < 0 or rp > 100):
                cols['royaltyper'][i] = max(0, min(100, rp))


def _pk_start(schema, table: str, column: str) -> int:
    """Fresh integer start above the compact max for an integer PK."""
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance: generated rows per table, in foreign-key order."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = dict(spec.TABLE_SIZES)
    if size is not None:
        sizes.update(size)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        pk_cols = set(tm.primary_key)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            is_pk = cm.name in pk_cols
            start = _pk_start(schema, t, cm.name) if is_pk else 1
            samplers[(t, cm.name)] = _init_sampler(
                t, cm.name, cm.type_str, not cm.notnull,
                literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key),
                null_share=_null_share(schema, t, cm.name), n_rows=n,
                is_pk=is_pk, pk_start=start)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         _compact_pk_set(schema, t))
        cols = drop_unique_duplicates(tm, cols)
        cols = drop_unique_tuples(t, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        _apply_semantic_rules(schema, inst, t, rng)
    return {t: inst[t] for t in schema.tables}
