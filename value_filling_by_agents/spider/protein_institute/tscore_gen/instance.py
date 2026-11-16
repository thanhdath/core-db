"""Random instance construction (fuzz/fuzz.py:83-196)."""
from . import spec
from .values import _init_sampler, apply_nulls, is_nullable

_GEN_PREFIX = 'gen_'


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_pk_values(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if any(v is None for v in k):
            continue
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    if not columns:
        return columns
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v is not None and v in seen:
                    continue
                seen.add(v)
                keep.append(i)
            columns = _filter(columns, keep)
    if table_meta.primary_key and table_meta.primary_key[0] in columns:
        seen, keep = set(), []
        for i, v in enumerate(columns[table_meta.primary_key[0]]):
            if v is None:
                continue
            if v in seen:
                continue
            seen.add(v)
            keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_values(schema, inst: dict, parent_table: str, parent_col: str) -> list:
    """Compact + generated parent values (non-NULL)."""
    pv = list(schema.original_values.get((parent_table, parent_col), []))
    pv += list(inst.get(parent_table, {}).get(parent_col) or [])
    return [v for v in pv if v is not None]


def fill_foreign_keys_consistently(schema, inst: dict, table: str, n: int, rng,
                                   reserved_parent: set = None) -> dict:
    """FK child columns draw from the parent's compact + generated values."""
    out = {}
    reserved_parent = reserved_parent or set()
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv_all = _parent_values(schema, inst, pt, pc)
        pv = [v for v in pv_all if v not in reserved_parent] if reserved_parent else list(pv_all)
        if not pv:
            pv = list(pv_all)
        share = spec.NULL_SHARE.get(key, spec.DEFAULT_NULL_SHARE)
        null_ok = is_nullable(cm)
        vals = []
        for _ in range(n):
            if null_ok and (not pv or rng.random() < share):
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        if null_ok and n > 0:
            if all(v is not None for v in vals):
                vals[rng.randrange(n)] = None
            if all(v is None for v in vals) and pv:
                vals[rng.randrange(n)] = rng.choice(pv)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (kept at or below the compact sizes)."""
    return {t: spec.TABLE_SIZES.get(t, 0) for t in schema.tables}


def _protected_values(t: str) -> dict:
    """Column -> set of values that tie planting must not overwrite."""
    prot: dict = {}
    for (tt, col), vals in spec.BOUNDARY.items():
        if tt == t:
            prot.setdefault(col, set()).update(str(v) for v in vals)
    for (tt, col), vals in spec.GROUP_SIZE_POOL.items():
        if tt == t:
            prot.setdefault(col, set()).update(str(v) for v in vals)
    return prot


def _plant_ties(t: str, cols: dict, rng) -> None:
    """Plant tie values by overwriting non-protected rows only (never append)."""
    prot = _protected_values(t)
    for (tt, col), target in spec.TIE_TARGETS.items():
        if tt != t or col not in cols:
            continue
        vals = cols[col]
        if len(vals) < 2:
            continue
        protected = prot.get(col, set())
        count = sum(1 for v in vals if v == target)
        need = 2 - count
        if need <= 0:
            continue
        for i in range(len(vals)):
            if need <= 0:
                break
            if vals[i] == target:
                continue
            if str(vals[i]) in protected:
                continue
            vals[i] = target
            need -= 1


def _fresh_pk_value(table: str, i: int, seen: set) -> str:
    """Fresh unique token from a namespace disjoint from compact PKs."""
    k = 0
    while True:
        v = '%s%s_%d_%d' % (_GEN_PREFIX, table, i, k)
        if v not in seen:
            seen.add(v)
            return v
        k += 1


def _repair_parents_without_children(schema, inst: dict, rng) -> None:
    """After PK filtering, verify parent_rows_without_children; repair if violated."""
    for t in list(schema.tables):
        children = []
        for (ct, cc), (pt, pc) in schema.fks.items():
            if pt == t:
                children.append((ct, cc, pc))
        if not children:
            continue
        tm = schema.tables[t]
        if not tm.primary_key:
            continue
        pk = tm.primary_key[0]
        all_parent = set(v for v in schema.original_values.get((t, pk), []) if v is not None)
        all_parent.update(v for v in (inst.get(t, {}).get(pk) or []) if v is not None)
        if not all_parent:
            continue
        for ct, cc, pc in children:
            cvals = inst.get(ct, {}).get(cc)
            if cvals is None:
                continue
            referenced = set(v for v in cvals if v is not None)
            if all_parent - referenced:
                continue
            victim = sorted(all_parent)[-1]
            for i in range(len(cvals)):
                if cvals[i] == victim:
                    cvals[i] = None


def _check_instance(schema, inst: dict) -> None:
    """Post-construction assertions (raise on violation; never silent)."""
    for t, tm in schema.tables.items():
        if not tm.primary_key:
            continue
        compact = _compact_pk_values(schema, t)
        cols = inst.get(t, {})
        n = len(cols.get(tm.primary_key[0], [])) if tm.primary_key[0] in cols else 0
        seen = set()
        for i in range(n):
            k = tuple(cols[c][i] for c in tm.primary_key)
            if any(v is None for v in k):
                raise AssertionError('NULL in PK %s' % t)
            if k in compact or k in seen:
                raise AssertionError('PK collision in %s: %r' % (t, k))
            seen.add(k)
    for (ct, cc), (pt, pc) in schema.fks.items():
        cvals = inst.get(ct, {}).get(cc)
        if cvals is None:
            continue
        cm = next(c for c in schema.tables[ct].columns if c.name == cc)
        if is_nullable(cm):
            if not any(v is None for v in cvals):
                raise AssertionError('no NULL in nullable FK %s.%s' % (ct, cc))
            if not any(v is not None for v in cvals):
                raise AssertionError('no non-NULL in nullable FK %s.%s' % (ct, cc))
        parents = set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        parents.update(v for v in (inst.get(pt, {}).get(pc) or []) if v is not None)
        if parents and not (parents - set(v for v in cvals if v is not None)):
            raise AssertionError('no parent without children for %s.%s' % (ct, cc))
    for (t, col), vals in spec.BOUNDARY.items():
        got = inst.get(t, {}).get(col) or []
        for b in vals:
            if b not in got:
                raise AssertionError('boundary %r missing in %s.%s' % (b, t, col))
    for (t, col), target in spec.TIE_TARGETS.items():
        got = inst.get(t, {}).get(col) or []
        if sum(1 for v in got if v == target) < 2:
            raise AssertionError('tie %r not planted twice in %s.%s' % (target, t, col))
    for (t, col), gvals in spec.GROUP_SIZE_POOL.items():
        got = inst.get(t, {}).get(col) or []
        sizes = sorted(sum(1 for v in got if v == g) for g in gvals)
        if not (sizes and sizes[0] == 1 and 2 in sizes and max(sizes) >= 3):
            raise AssertionError('group sizes %r not 1/2/>=3 in %s.%s' % (sizes, t, col))


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification sizes."""
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
    for level in schema.table_order:
        for t in level:
            tm = schema.tables[t]
            n = int(size.get(t, 0))
            cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                    for cm in tm.columns if (t, cm.name) in samplers}
            for cm in tm.columns:
                if (t, cm.name) in samplers and (t, cm.name) not in schema.fks:
                    cols[cm.name] = apply_nulls(t, cm, cols[cm.name], rng)
            if tm.primary_key and len(tm.primary_key) == 1:
                pk = tm.primary_key[0]
                if pk in cols:
                    seen = set(v for v in schema.original_values.get((t, pk), []) if v is not None)
                    cols[pk] = [_fresh_pk_value(t, i, seen) for i in range(len(cols[pk]))]
            inst[t] = cols
            reserved = set()
            for t2, t2m in schema.tables.items():
                for cmt2 in t2m.columns:
                    if (t2, cmt2.name) in schema.fks and schema.fks[(t2, cmt2.name)][0] == t:
                        pv = [v for v in schema.original_values.get((t, schema.fks[(t2, cmt2.name)][1]), []) if v is not None]
                        pv += [v for v in (inst.get(t, {}).get(schema.fks[(t2, cmt2.name)][1]) or []) if v is not None]
                        if pv:
                            reserved.add(sorted(pv)[0])
            cols.update(fill_foreign_keys_consistently(schema, inst, t, n, rng, reserved))
            keep_cols = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}
            keep_cols = sample_fresh_primary_keys(tm, keep_cols)
            keep_cols = drop_unique_duplicates(tm, keep_cols)
            inst[t] = {cm.name: keep_cols.get(cm.name, cols.get(cm.name)) for cm in tm.columns}
    for t in inst:
        _plant_ties(t, inst[t], rng)
    _repair_parents_without_children(schema, inst, rng)
    _check_instance(schema, inst)
    return {t: inst[t] for t in schema.tables}
