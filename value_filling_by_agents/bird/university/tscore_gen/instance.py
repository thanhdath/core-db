"""Random instance construction (fuzz/fuzz.py:83-196) + specification rules by construction."""
from . import specification as S
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


def _pk_offset(schema, table: str) -> int:
    """Largest integer id in the compact rows of table (0 if none / non-integer)."""
    tm = schema.tables.get(table)
    if tm is None or len(tm.primary_key) != 1:
        return 0
    pk = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _compact_id_set(schema, table: str, col: str) -> set:
    return {v for v in schema.original_values.get((table, col), []) if v is not None}


def _apply_pk_offsets(schema, instance: dict) -> None:
    """Shift integer PKs above the compact maximum and remap FK references to generated parents."""
    offsets = {}
    remaps = {}
    for lvl in schema.table_order:
        for t in lvl:
            if t not in instance or not instance[t]:
                continue
            tm = schema.tables[t]
            if len(tm.primary_key) != 1:
                continue
            pk = tm.primary_key[0]
            cols = instance[t]
            if pk not in cols:
                continue
            off = _pk_offset(schema, t) + 1
            offsets[t] = off
            old = cols[pk]
            new = []
            remap = {}
            used = _compact_id_set(schema, t, pk)
            next_id = off
            for v in old:
                if not isinstance(v, int):
                    new.append(v)
                    continue
                cand = v + off
                while cand in used:
                    cand += 1
                used.add(cand)
                remap[v] = cand
                new.append(cand)
            cols[pk] = new
            remaps[t] = (pk, remap)
        for t in lvl:
            if t not in instance:
                continue
            for cm in schema.tables[t].columns:
                key = (t, cm.name)
                if key not in schema.fks:
                    continue
                pt, pc = schema.fks[key]
                if pt not in remaps or pc not in instance.get(pt, {}):
                    continue
                remap = remaps[pt][1]
                colv = instance[t].get(cm.name)
                if not colv:
                    continue
                instance[t][cm.name] = [None if v is None else remap.get(v, v) for v in colv]


def _apply_null_rule(schema, instance: dict, rng) -> None:
    """Per nullable column: at least one NULL and a NULL share following compact stats / spec targets."""
    for t, cols in instance.items():
        tm = schema.tables[t]
        for cm in tm.columns:
            if not cm.name in cols or cm.pk_pos > 0:
                continue
            key = (t, cm.name)
            share = S.NULL_SHARE.get(key)
            if share is None and key in schema.fks:
                share = S.DEFAULT_FK_NULL_SHARE
            if share is None:
                continue
            vals = list(cols[cm.name])
            n = len(vals)
            if n == 0:
                continue
            existing = sum(1 for v in vals if v is None)
            target = max(1, int(round(n * share)))
            target = min(target, n)
            if existing == target:
                continue
            idx = list(range(n))
            rng.shuffle(idx)
            if target > existing:
                need = target - existing
                for i in idx:
                    if need <= 0:
                        break
                    if vals[i] is not None:
                        vals[i] = None
                        need -= 1
            elif target < existing:
                need = existing - target
                for i in idx:
                    if need <= 0:
                        break
                    if vals[i] is None:
                        need -= 1
                        vals[i] = None
            cols[cm.name] = vals


def _apply_rule_bounds(schema, instance: dict) -> None:
    """Semantic formula clamps by construction (rules constrain only non-NULL operands)."""
    def clamp_col(t, c, lo, hi):
        cols = instance.get(t)
        if not cols or c not in cols:
            return
        out = []
        for v in cols[c]:
            if v is None:
                out.append(None)
                continue
            if lo is not None and v < lo:
                v = lo
            if hi is not None and v > hi:
                v = hi
            out.append(v)
        cols[c] = out
    clamp_col('university_year', 'num_students', 1, None)
    clamp_col('university_year', 'student_staff_ratio', 0.1, None)
    clamp_col('university_year', 'pct_international_students', 0, 100)
    clamp_col('university_year', 'pct_female_students', 0, 100)
    clamp_col('university_ranking_year', 'score', 0, 100)
    clamp_col('university_ranking_year', 'year', S.YEAR_LO, S.YEAR_HI)
    clamp_col('university_year', 'year', S.YEAR_LO, S.YEAR_HI)


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
                sizes[t] = int(min(s, S.LEVEL_CAP))
            s *= 4
    for t in list(sizes):
        lo = S.TABLE_SIZE_MIN
        hi = S.TABLE_SIZE_MAX
        sizes[t] = max(lo, min(hi if sizes[t] <= hi else min(sizes[t], S.LEVEL_CAP), S.LEVEL_CAP))
    return sizes


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of generated rows (fuzz.py:111-196) with specification rules applied."""
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
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc)
                if final is None:
                    continue
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    inst = {t: inst[t] for t in schema.tables}
    _apply_pk_offsets(schema, inst)
    _apply_rule_bounds(schema, inst)
    _apply_null_rule(schema, inst, rng)
    return inst
