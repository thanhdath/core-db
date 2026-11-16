"""Random instance construction as appended rows on a copy of the compact database."""
import random

from . import spec
from .inmemory import ParentStore, fk_values, one_tie_plan
from .samplers import draw_column
from .writer import append_rows


def build_and_write_instance(schema, literal_pool: dict, orig: str, path: str, rng, spec_obj: dict) -> dict:
    store = ParentStore(schema)
    sizes = {t: spec.table_rows(schema, t, rng) for t in schema.tables}
    instance_rows: dict = {}
    order = [t for lvl in schema.table_order for t in lvl]

    comp_by_child: dict = {}
    for cf in schema.composite_fks:
        comp_by_child.setdefault(cf.child_table, []).append(cf)
    comp_child_cols = schema.composite_child_cols

    for t in order:
        tm = schema.tables[t]
        n = sizes.get(t, 0)
        cols: dict = {cm.name: [None] * n for cm in tm.columns}
        composite_cols = set(comp_child_cols.get(t, ()))
        single_fks = {(ct, cc): v for (ct, cc), v in schema.single_fk_cols.items() if ct == t}
        pk_cols = list(tm.primary_key)

        for cm in tm.columns:
            if (t, cm.name) in single_fks:
                continue
            if cm.name in composite_cols:
                continue
            if len(pk_cols) == 1 and cm.name == pk_cols[0]:
                cols[cm.name] = _sequential_pk(store, t, cm.name, n)
                continue
            excl = set(_nonnull(store.keys(t, cm.name))) if cm.unique else set()
            vals = draw_column(schema, t, cm.name, n, literal_pool.get((t, cm.name), []), rng, spec_obj, excl)
            cols[cm.name] = vals

        if t in comp_by_child:
            cols = _apply_composite_fks(t, comp_by_child[t], cols, n, store, rng)

        for (ct, cc), (pt, pc) in single_fks.items():
            cm = _get_col(tm, cc)
            if cm is None:
                continue
            if cm.name in pk_cols and pt == t:
                continue
            allow_null = (not cm.notnull) and cm.pk_pos == 0
            share = spec.null_share(t, cm.name, 0.0, allow_null)
            parent_values_all = _parent_values(store, pt, pc)
            compact_parent = [v for v in schema.original_values.get((pt, pc), []) or [] if v is not None]
            force = _boundary_force(t, cm.name, spec_obj, compact_parent, parent_values_all, n)
            cols[cm.name] = fk_values(rng, parent_values_all, n, allow_null, share,
                                      compact_parent, force_values=force)

        if t == 'IMG_OBJ_ATT':
            _shape_img_obj_att(cols, n, store, rng)
        elif t == 'IMG_REL':
            _shape_img_rel(cols, n, store, rng)

        cols = _dedupe_keys(tm, t, cols, store, schema, rng, n)

        rows = _rows_as_dicts(tm, cols)
        instance_rows[t] = rows
        for row in rows:
            store.add_row(t, row)

    stats = append_rows(schema, orig, instance_rows, path)
    return stats


def _get_col(tm, name: str):
    for c in tm.columns:
        if c.name == name:
            return c
    return None


def _nonnull(vals) -> list:
    return [v for v in vals if v is not None]


def _sequential_pk(store, table: str, column: str, n: int) -> list:
    """Sequential integers starting after the compact maximum (unique per table)."""
    existing = [v for v in store.keys(table, column) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 0
    return [start + i for i in range(n)]


def _parent_values(store, table: str, column: str) -> list:
    return store.distinct_columns(table, column)


def _boundary_force(table: str, column: str, spec_obj: dict, compact_parent: list, parent_pool: list,
                    n: int) -> list:
    """Return boundary values that must be forced (present in parent pool) for this FK column."""
    want = spec.boundary_ints(table, column, spec_obj)
    if not want:
        return []
    have = set(x for x in parent_pool if isinstance(x, int))
    out = [x for x in want if x in have]
    if not out and compact_parent:
        ce = [x for x in want if x in set(compact_parent)]
        out = ce
    return out


def _apply_composite_fks(t: str, fks: list, cols: dict, n: int, store, rng) -> dict:
    """Fill composite FK columns for child table `t` from real parent row tuples."""
    if not fks:
        return cols
    common_cols = set(fks[0].child_cols)
    for cf in fks[1:]:
        common_cols &= set(cf.child_cols)

    if len(fks) == 1:
        cf = fks[0]
        pairs = store.row_tuples(cf.parent_table, cf.parent_cols)
        if not pairs:
            return cols
        for i in range(n):
            pick = rng.choice(pairs)
            for c, v in zip(cf.child_cols, pick):
                cols[c][i] = v
        return cols

    shared_parent_cols = [pc for cc, pc in zip(fks[0].child_cols, fks[0].parent_cols) if cc in common_cols]
    if not shared_parent_cols:
        return cols
    sp = shared_parent_cols[0]
    shared_child = [cc for cc in fks[0].child_cols if cc in common_cols][0]
    parent_keys = store.distinct_columns(fks[0].parent_table, sp)
    if not parent_keys:
        return cols
    plan = _img_id_group_plan_children(parent_keys, n, rng, target_sizes=[1, 2, 3])
    cols[shared_child] = plan

    rem_parent = [pc for cc, pc in zip(fks[0].child_cols, fks[0].parent_cols) if cc not in common_cols]
    pairs_by_key = store.pairs_by_key(fks[0].parent_table, sp, rem_parent)

    for cf in fks:
        rem_child = [c for c in cf.child_cols if c not in common_cols]
        if not rem_child:
            continue
        for i in range(n):
            img_id = cols[shared_child][i]
            rows = pairs_by_key.get(img_id, [])
            if not rows:
                all_rows = [r for vs in pairs_by_key.values() for r in vs]
                if not all_rows:
                    continue
                pick = rng.choice(all_rows)
            else:
                pick = rng.choice(rows)
            for j, c in enumerate(rem_child):
                cols[c][i] = pick[j] if j < len(pick) else None

    if 'OBJ1_SAMPLE_ID' in cols and 'OBJ2_SAMPLE_ID' in cols:
        for i in range(n):
            a = cols['OBJ1_SAMPLE_ID'][i]
            b = cols['OBJ2_SAMPLE_ID'][i]
            if a is None or b is None or a != b:
                continue
            img_id = cols[shared_child][i]
            rows = pairs_by_key.get(img_id, [])
            alts = [r[0] for r in rows if r and r[0] != a]
            if alts:
                cols['OBJ2_SAMPLE_ID'][i] = rng.choice(alts)
    return cols


def _img_id_group_plan_children(parent_keys: list, n: int, rng, target_sizes: list) -> list:
    """Return n parent-key references whose group sizes include target_sizes."""
    if not parent_keys:
        return [0] * n
    keys = list(dict.fromkeys(parent_keys))
    rng.shuffle(keys)
    plan: list = []
    ki = 0
    for s in target_sizes:
        if ki < len(keys) and len(plan) + s <= n:
            plan.extend([keys[ki]] * s)
            ki += 1
    while len(plan) < n:
        plan.append(rng.choice(keys))
    rng.shuffle(plan)
    return plan[:n]


def _shape_img_obj_att(cols, n, store, rng):
    """For IMG_OBJ_ATT: ensure rank-1 tie on COUNT(att_class_id) without touching FK columns."""
    if n <= 0:
        return
    att_pool = store.distinct_columns('ATT_CLASSES', 'ATT_CLASS_ID')
    if att_pool:
        cols['ATT_CLASS_ID'] = one_tie_plan(att_pool, n, rng)


def _shape_img_rel(cols, n, store, rng):
    """For IMG_REL: enforce OBJ1_SAMPLE_ID <> OBJ2_SAMPLE_ID within the same IMG_ID's rows."""
    if n <= 0:
        return
    pairs_by_key = store.pairs_by_key('IMG_OBJ', 'IMG_ID', ['OBJ_SAMPLE_ID'])
    for i in range(n):
        a = cols['OBJ1_SAMPLE_ID'][i]
        b = cols['OBJ2_SAMPLE_ID'][i]
        if a is None or b is None or a != b:
            continue
        img_id = cols['IMG_ID'][i]
        rows = pairs_by_key.get(img_id, [])
        alts = [r[0] for r in rows if r and r[0] != a]
        if alts:
            cols['OBJ2_SAMPLE_ID'][i] = rng.choice(alts)


def _dedupe_keys(tm, t: str, cols: dict, store, schema, rng, n: int) -> dict:
    """Dedupe PKs (and singleton UNIQUE columns) against compact and already-generated tuples."""
    seen = set(store.compact_pk_tuples(t)) if tm.primary_key else set()
    seen_unique: dict = {}
    for (tt, ucols) in schema.unique_tuples:
        if tt == t:
            seen_unique[tuple(ucols)] = set()
    for ucols in seen_unique:
        lists = [store.keys(t, c) for c in ucols]
        if not lists or any(not l for l in lists):
            continue
        k = min(len(l) for l in lists)
        for i in range(k):
            tup = tuple(l[i] for l in lists)
            seen_unique[ucols].add(tup)
    pk_cols = list(tm.primary_key)
    comp_fk_for_pk = _composite_fk_for_pk(schema, t, set(pk_cols))
    for i in range(n):
        pk = tuple(cols[c][i] for c in pk_cols)
        if pk in seen:
            if comp_fk_for_pk is not None:
                _redraw_composite_row(cols, i, comp_fk_for_pk, store, rng)
                pk = tuple(cols[c][i] for c in pk_cols)
            else:
                c0 = pk_cols[0]
                v = cols[c0][i]
                if isinstance(v, int):
                    while (v,) in seen:
                        v = spec.fresh_key_int(v, {x[0] for x in seen if len(x) == 1}, rng)
                    cols[c0][i] = v
                else:
                    s = str(v)
                    while (s,) in seen:
                        s = spec.perturb_string(s, rng, {x[0] for x in seen if len(x) == 1})
                    cols[c0][i] = s
                pk = tuple(cols[c][i] for c in pk_cols)
            tries = 0
            while pk in seen and tries < 30:
                if comp_fk_for_pk is not None:
                    _redraw_composite_row(cols, i, comp_fk_for_pk, store, rng)
                else:
                    c0 = pk_cols[0]
                    v = cols[c0][i]
                    if isinstance(v, int):
                        v = spec.fresh_key_int(v, {x[0] for x in seen if len(x) == 1}, rng)
                        cols[c0][i] = v
                    else:
                        cols[c0][i] = spec.perturb_string(str(v), rng, {x[0] for x in seen if len(x) == 1})
                pk = tuple(cols[c][i] for c in pk_cols)
                tries += 1
        seen.add(pk)
        for ucols, seen_set in seen_unique.items():
            tup = tuple(cols[c][i] for c in ucols)
            if tup in seen_set:
                killed = False
                for c in ucols:
                    if (t, c) in schema.fks:
                        continue
                    v = cols[c][i]
                    if v is None:
                        continue
                    if isinstance(v, int):
                        v = spec.fresh_key_int(v, {x[0] for x in seen_set if len(x) == 1}, rng)
                    else:
                        v = spec.perturb_string(str(v), rng, {x[0] for x in seen_set if len(x) == 1})
                    cols[c][i] = v
                    killed = True
                    break
                if not killed:
                    cf = _composite_fk_for_pk(schema, t, set(ucols))
                    if cf is not None:
                        _redraw_composite_row(cols, i, cf, store, rng)
                tup = tuple(cols[c][i] for c in ucols)
            seen_set.add(tup)
    return cols


def _composite_fk_for_pk(schema, table: str, pk_set: set):
    """Return the composite FK whose child cols are all PK cols (so PK dedupe must redraw it)."""
    for cf in schema.composite_fks:
        if cf.child_table == table and set(cf.child_cols) <= pk_set:
            return cf
    return None


def _redraw_composite_row(cols, i: int, cf, store, rng) -> None:
    """Pick a different parent row for the given composite FK at row i (in place)."""
    parent_pairs = store.row_tuples(cf.parent_table, cf.parent_cols)
    if not parent_pairs:
        return
    current = tuple(cols[c][i] for c in cf.child_cols)
    for _ in range(20):
        pick = rng.choice(parent_pairs)
        if pick != current:
            for c, v in zip(cf.child_cols, pick):
                cols[c][i] = v
            return
    for c, v in zip(cf.child_cols, parent_pairs[0]):
        cols[c][i] = v


def _rows_as_dicts(tm, cols: dict) -> list:
    n = len(next(iter(cols.values()))) if cols else 0
    out = []
    for i in range(n):
        out.append({cm.name: (cols[cm.name][i] if cm.name in cols and i < len(cols[cm.name]) else None)
                    for cm in tm.columns})
    return out
