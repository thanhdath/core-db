"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from .spec import col_key
from .values import _init_sampler

_DT = '%Y-%m-%d %H:%M:%S'


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


def drop_unique_tuples(schema, table: str, columns: dict) -> dict:
    """Drop rows repeating a composite UNIQUE tuple (first occurrence kept)."""
    for t, names in getattr(schema, 'unique_tuples', []):
        if t != table or not all(n in columns for n in names):
            continue
        n = len(next(iter(columns.values())))
        seen, keep = set(), []
        for i in range(n):
            k = tuple(columns[c][i] for c in names)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
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
    """Specification sizes (table_sizes_per_instance) with per-instance variation (0-230 rows)."""
    base = spec.get('table_sizes') or {}
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            b = int(base.get(t, 0))
            if b <= 0:
                sizes[t] = 0
            elif b <= 2:
                sizes[t] = b
            else:
                lo = max(1, int(b * 0.6))
                hi = max(lo, int(b * 1.4))
                sizes[t] = rng.randint(lo, hi)
    return sizes


def _domain_for(spec: dict, key: str):
    """Specification domain for a column: ('const', v) | ('range', [..]) | ('enum', [..]) | ('boundary', [..])."""
    if key in spec.get('constants', {}):
        return ('const', spec['constants'][key])
    if key in spec.get('ranges', {}):
        return ('range', list(spec['ranges'][key]))
    if key in spec.get('enums', {}):
        return ('enum', list(spec['enums'][key]))
    if key in spec.get('boundaries', {}):
        return ('boundary', list(spec['boundaries'][key]))
    return None


def _window_for(spec: dict, key: str):
    """Datetime window for a column (spec datetime rule)."""
    if key in spec.get('datetime_columns', []):
        return (dt.datetime(2005, 5, 24, 0, 0, 0), dt.datetime(2006, 2, 15, 23, 59, 59))
    return None


def _null_share(spec: dict, schema, key: str, cm) -> float:
    """NULL share: specification override, else the compact database's share."""
    if not cm.notnull and cm.pk_pos == 0:
        if key in spec.get('null_shares', {}):
            return float(spec['null_shares'][key])
        t, c = key.split('.', 1)
        vals = schema.original_values.get((t, c), [])
        if vals:
            return sum(1 for v in vals if v is None) / float(len(vals))
        return 0.0
    return 0.0


def _plant_nulls(values: list, share: float, rng) -> list:
    """Plant NULLs in a nullable column: at least one, share of the rows, at most n-1."""
    if not values:
        return values
    n = len(values)
    if share <= 0:
        k = 1
    else:
        k = max(1, int(round(share * n)))
    k = min(k, n - 1) if n > 1 else 0
    if k <= 0:
        return list(values)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _fresh_pk_start(schema, table: str, column: str) -> int:
    """First generated key above the compact maximum (keys fresh against compact rows)."""
    vals = [v for v in schema.original_values.get((table, column), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _copy_columns(spec: dict, schema, table: str, inst: dict) -> None:
    """Derived columns computed in Python from in-memory parent rows (film_text copies)."""
    copies = spec.get('copy_columns', {}).get(table)
    if not copies:
        return
    cols = inst.get(table, {})
    if not cols:
        return
    n = len(next(iter(cols.values())))
    fk_col = None
    parent_table = None
    for child_col, parent_key in copies.items():
        pt, pc = parent_key.split('.', 1)
        fk = schema.fks.get((table, child_col))
        if fk is not None:
            fk_col, parent_table = child_col, pt
            break
    if fk_col is None:
        for (ct, cc), (pt, pc) in schema.fks.items():
            if ct == table:
                fk_col, parent_table = cc, pt
                break
    if fk_col is None or parent_table is None:
        return
    parent_cols = inst.get(parent_table, {})
    if not parent_cols:
        return
    pkey = schema.fks[(table, fk_col)][1]
    pvals = parent_cols.get(pkey, [])
    lookup = {}
    for i, k in enumerate(pvals):
        if k is not None and k not in lookup:
            lookup[k] = i
    for child_col, parent_key in copies.items():
        pt, pc = parent_key.split('.', 1)
        if pt != parent_table:
            continue
        pcol = parent_cols.get(pc, [])
        out = []
        for v in cols.get(fk_col, [None] * n):
            i = lookup.get(v)
            out.append(pcol[i] if i is not None and i < len(pcol) else None)
        cols[child_col] = out
    inst[table] = cols


def _drop_rows(inst: dict, table: str, keep: list) -> None:
    """Drop all rows of `table` not in `keep` (indices into the current row list)."""
    for col, vals in list(inst.get(table, {}).items()):
        inst[table][col] = [vals[i] for i in keep]


def _dependent_tables(schema, table: str) -> list:
    """Child tables whose FK references `table` (directly)."""
    out = []
    for (ct, cc), (pt, pc) in schema.fks.items():
        if pt == table and ct != table:
            out.append(ct)
    return out


def _pk_tuple(inst: dict, table: str, schema, i: int) -> tuple:
    """Full primary-key tuple of row i of `table` (all PK columns, not just the first)."""
    pk = schema.tables[table].primary_key
    return tuple(inst[table][c][i] for c in pk)


def _construct_unmatched_join(schema, inst: dict, spec: dict, rng) -> None:
    """For each parent/child FK pair marked unmatched_join_rows, remove all children of at least one chosen parent
    row so that parent has no children (child FK never NULL)."""
    for key in spec.get('unmatched_join', []):
        t, c = key.split('.', 1)
        if (t, c) not in schema.fks:
            continue
        pt, pc = schema.fks[(t, c)]
        parents = inst.get(pt, {}).get(pc) or []
        children = inst.get(t, {}).get(c) or []
        if not parents or not children:
            continue
        counts = {}
        for v in children:
            counts[v] = counts.get(v, 0) + 1
        with_children = [p for p in parents if counts.get(p, 0) > 0]
        if not with_children:
            continue
        chosen = rng.choice(with_children)
        pk_cols = schema.tables[t].primary_key
        if not pk_cols:
            continue
        removed = [i for i, v in enumerate(children) if v == chosen]
        if not removed:
            continue
        removed_pks = {_pk_tuple(inst, t, schema, i) for i in removed}
        for dep in _dependent_tables(schema, t):
            for (dc, dcol), (dcp, dcc) in schema.fks.items():
                if dc != dep or dcp != t:
                    continue
                dvals = inst.get(dep, {}).get(dcol)
                if not dvals:
                    continue
                keep = [i for i, v in enumerate(dvals) if v not in removed_pks]
                if len(keep) != len(dvals):
                    _drop_rows(inst, dep, keep)
        keep = [i for i in range(len(children)) if i not in set(removed)]
        _drop_rows(inst, t, keep)


def _child_fk_for_parent_key(schema, key: str):
    """Map a parent-side 'table.column' key to the child FK column that groups by it."""
    t, c = key.split('.', 1)
    if (t, c) in schema.fks:
        return (t, c)
    for (ct, cc), (pt, pc) in schema.fks.items():
        if pt == t and pc == c:
            return (ct, cc)
    return None


def _construct_ties(schema, inst: dict, spec: dict, rng) -> None:
    """For each column marked ties_for_order_limit, assign at least two child rows to the same parent (the one with
    the highest count) so ordering by COUNT(*) DESC ties at rank 1."""
    for key, target in spec.get('ties_for_order_limit', {}).items():
        mapped = _child_fk_for_parent_key(schema, key)
        if mapped is None:
            continue
        t, c = mapped
        pt, pc = schema.fks[(t, c)]
        parents = inst.get(pt, {}).get(pc) or []
        children = inst.get(t, {}).get(c) or []
        if not parents or len(children) < 2:
            continue
        counts = {}
        for v in children:
            counts[v] = counts.get(v, 0) + 1
        if not counts:
            continue
        top = max(counts.values())
        top_parents = [p for p, n in counts.items() if n == top]
        chosen = rng.choice(top_parents)
        if counts.get(chosen, 0) < 2:
            need = 2 - counts.get(chosen, 0)
            for i in range(len(children)):
                if need <= 0:
                    break
                if children[i] != chosen:
                    children[i] = chosen
                    need -= 1
            inst[t][c] = children


def _construct_aggregate_boundaries(schema, inst: dict, spec: dict, rng) -> None:
    """For each column marked aggregate_boundary, construct child counts per parent to hit the listed target values
    (e.g. 2, 3, 4, 29, 30, 31) for the relevant join."""
    for key, targets in spec.get('aggregate_boundaries', {}).items():
        mapped = _child_fk_for_parent_key(schema, key)
        if mapped is None:
            continue
        t, c = mapped
        pt, pc = schema.fks[(t, c)]
        parents = inst.get(pt, {}).get(pc) or []
        children = inst.get(t, {}).get(c) or []
        if not parents or not children:
            continue
        targets = [int(x) for x in targets]
        need = sum(targets)
        if need > len(children):
            targets = targets[:max(1, len(children) // max(1, min(targets)))]
        assigned = []
        used = set()
        for tgt in targets:
            p = None
            for cand in parents:
                if cand not in used:
                    p = cand
                    break
            if p is None:
                break
            used.add(p)
            assigned.extend([p] * tgt)
        if len(assigned) < len(children):
            assigned.extend(rng.choice(parents) for _ in range(len(children) - len(assigned)))
        assigned = assigned[:len(children)]
        rng.shuffle(assigned)
        inst[t][c] = assigned
        realized = {}
        for v in assigned:
            realized[v] = realized.get(v, 0) + 1
        got = set(realized.values())
        for tgt in targets:
            if tgt not in got:
                for p in parents:
                    if realized.get(p, 0) != tgt:
                        idxs = [i for i, v in enumerate(assigned) if v == p]
                        if len(idxs) < tgt:
                            extra = [i for i, v in enumerate(assigned) if v != p][:tgt - len(idxs)]
                            for i in extra:
                                assigned[i] = p
                        elif len(idxs) > tgt:
                            for i in idxs[tgt:]:
                                assigned[i] = rng.choice(parents)
                        realized = {}
                        for v in assigned:
                            realized[v] = realized.get(v, 0) + 1
                        break
        inst[t][c] = assigned


def _construct_group_sizes(schema, inst: dict, spec: dict, rng) -> None:
    """For each column marked group_sizes, construct groups of size 1, 2 and >= 3 among the column's values."""
    for key in spec.get('group_sizes', []):
        t, c = key.split('.', 1)
        tm = schema.tables.get(t)
        if tm is None:
            continue
        if c in tm.primary_key:
            continue
        cols = inst.get(t, {})
        vals = cols.get(c)
        if not vals or len(vals) < 6:
            continue
        if (t, c) in schema.fks:
            pt, pc = schema.fks[(t, c)]
            parent_vals = inst.get(pt, {}).get(pc) or []
            pool = [v for v in parent_vals if v is not None]
            if len(pool) < 3:
                continue
            a, b, cval = rng.sample(pool, 3)
            out = list(vals)
            out[0] = a
            out[1] = b
            out[2] = b
            out[3] = cval
            out[4] = cval
            out[5] = cval
            cols[c] = out
            inst[t] = cols
            continue
        out = list(vals)
        a = out[0]
        b = out[1] if out[1] != a else (out[2] if out[2] != a else a + '_b')
        cval = out[2] if out[2] not in (a, b) else a + '_c'
        out[0] = a
        out[1] = b
        out[2] = b
        out[3] = cval
        out[4] = cval
        out[5] = cval
        cols[c] = out
        inst[t] = cols


def _construct_comparison_boundaries(schema, inst: dict, spec: dict, rng) -> None:
    """For each column marked comparison_boundary, assign at least one child row whose FK equals a parent key and one
    whose FK is one step from a parent key in the parent's key ordering (existing keys only; never arithmetic
    p±1)."""
    for key, target in spec.get('comparison_boundaries', {}).items():
        t, c = key.split('.', 1)
        if (t, c) not in schema.fks:
            continue
        pt, pc = schema.fks[(t, c)]
        parents = inst.get(pt, {}).get(pc) or []
        children = inst.get(t, {}).get(c) or []
        if not parents or not children:
            continue
        if pc not in schema.tables[pt].primary_key:
            continue
        ordered = sorted(set(p for p in parents if isinstance(p, int)))
        if not ordered:
            continue
        p = rng.choice(ordered)
        children[0] = p
        if len(children) > 1:
            nxt = [q for q in ordered if q > p]
            if nxt:
                children[1] = nxt[0]
            else:
                children[1] = p
        if len(children) > 2:
            prv = [q for q in ordered if q < p]
            if prv:
                children[2] = prv[-1]
            else:
                children[2] = p
        inst[t][c] = children


def _construct_customer_rental_join(schema, inst: dict, spec: dict, rng) -> None:
    """customer.customer_id >= rental.customer_id: ensure some rental.customer_id equals a customer_id and some is
    one step from a customer_id (existing keys only)."""
    if 'customer.customer_id' not in spec.get('comparison_boundaries', {}):
        return
    cust = inst.get('customer', {}).get('customer_id') or []
    rent = inst.get('rental', {}).get('customer_id')
    if not cust or not rent:
        return
    ordered = sorted(set(p for p in cust if isinstance(p, int)))
    if not ordered:
        return
    p = rng.choice(ordered)
    rent[0] = p
    if len(rent) > 1:
        nxt = [q for q in ordered if q > p]
        rent[1] = nxt[0] if nxt else p
    if len(rent) > 2:
        prv = [q for q in ordered if q < p]
        rent[2] = prv[-1] if prv else p
    inst['rental']['customer_id'] = rent


def _repair_fks(schema, inst: dict, rng) -> None:
    """Final FK-repair pass: every FK value must reference an existing parent key."""
    order = [x for lvl in schema.table_order for x in lvl]
    for t in order:
        tm = schema.tables.get(t)
        if tm is None or t not in inst:
            continue
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = inst.get(pt, {}).get(pc) or []
            allowed = set(v for v in parent_vals if v is not None)
            if not allowed:
                continue
            vals = cols.get(cm.name)
            if vals is None:
                continue
            out = []
            for v in vals:
                if v is None or v in allowed:
                    out.append(v)
                else:
                    out.append(rng.choice(sorted(allowed)))
            cols[cm.name] = out


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as compact rows + appended generated rows."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = col_key(t, cm.name)
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), domain=_domain_for(spec, key),
                window=_window_for(spec, key),
                duplicate_share=float(spec.get('duplicate_shares', {}).get(key, 0.0)))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                start = _fresh_pk_start(schema, t, cm.name)
                cols[cm.name] = [start + i for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        cols = drop_unique_tuples(schema, t, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.name in cols:
                share = _null_share(spec, col_key(t, cm.name), cm) if False else _null_share(spec, schema, col_key(t, cm.name), cm)
                if share > 0 or not cm.notnull:
                    cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
        inst[t] = cols
    _repair_fks(schema, inst, rng)
    for t in order:
        _copy_columns(spec, schema, t, inst)
    _construct_unmatched_join(schema, inst, spec, rng)
    _construct_ties(schema, inst, spec, rng)
    _construct_aggregate_boundaries(schema, inst, spec, rng)
    _construct_group_sizes(schema, inst, spec, rng)
    _construct_comparison_boundaries(schema, inst, spec, rng)
    _construct_customer_rental_join(schema, inst, spec, rng)
    return {t: inst[t] for t in schema.tables}
