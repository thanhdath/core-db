"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact DB."""
from .spec import Specification, default_specification
from .values import _init_sampler, make_column_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _unique_tuples(table_meta) -> list:
    """Single-column UNIQUE columns plus composite UNIQUE tuples (from the schema)."""
    out = []
    for cm in table_meta.columns:
        if cm.unique:
            out.append((cm.name,))
    for tup in getattr(table_meta, 'unique_tuples', ()) or ():
        if len(tup) > 1:
            out.append(tuple(tup))
    return out


def _key_tuples(table_meta) -> list:
    """All key tuples that must stay unique: PK plus UNIQUE (single and composite)."""
    keys = []
    if table_meta.primary_key:
        keys.append(tuple(table_meta.primary_key))
    for t in _unique_tuples(table_meta):
        if t not in keys:
            keys.append(t)
    return keys


def _dedup_keys(table_meta, columns: dict, reserved: dict = None) -> dict:
    """Drop rows repeating any PK / UNIQUE tuple (against compact reserved and generated)."""
    reserved = reserved or {}
    keys = _key_tuples(table_meta)
    if not keys or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen = {k: set(reserved.get(k, ())) for k in keys}
    keep = []
    for i in range(n):
        ok = True
        for k in keys:
            if any(c not in columns for c in k):
                continue
            tup = tuple(columns[c][i] for c in k)
            if tup in seen[k]:
                ok = False
                break
        if ok:
            for k in keys:
                if all(c in columns for c in k):
                    seen[k].add(tuple(columns[c][i] for c in k))
            keep.append(i)
    return _filter(columns, keep)


def sample_fresh_primary_keys(table_meta, columns: dict, reserved: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact key); first occurrence kept."""
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


def drop_unique_duplicates(table_meta, columns: dict, reserved: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    reserved = reserved or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(reserved.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent key pool = compact values + generated values (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []) or [])
    vals += list(instance.get(pt, {}).get(pc, []) or [])
    return [v for v in vals if v is not None]


def _reserved_parent_keys(schema, instance: dict, pt: str, pc: str, rng) -> set:
    """Reserve a subset of parent keys that generated children must NOT reference."""
    gen = [v for v in (instance.get(pt, {}).get(pc, []) or []) if v is not None]
    if not gen:
        return set()
    k = max(1, int(round(len(gen) * 0.10)))
    k = min(k, len(gen))
    return set(rng.sample(gen, k))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: dict, reserved: dict = None) -> dict:
    """FK child columns draw from the parent's key pool; NULL by the NULL rule."""
    reserved = reserved or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        excl = reserved.get((pt, pc), set())
        if excl:
            pv = [v for v in pv if v not in excl]
        share = null_share.get(key, 0.0)
        col = []
        for _ in range(n):
            if pv and rng.random() >= share:
                col.append(rng.choice(pv))
            else:
                col.append(None)
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng, spec: Specification) -> dict:
    """Per-instance sizes: the specification's exact sizes (no jitter)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = int(spec.sizes.get(t, 30))
            sizes[t] = max(0, base)
    return sizes


def _reserved_keys(schema, table: str) -> dict:
    """Reserved PK / UNIQUE tuples from the compact rows, keyed by tuple-of-columns."""
    tm = schema.tables[table]
    out = {}
    for k in _key_tuples(tm):
        cols = [schema.original_values.get((table, c), []) for c in k]
        n = min((len(c) for c in cols), default=0)
        out[k] = {tuple(c[i] for c in cols) for i in range(n)}
    return out


def _reserved_unique(schema, table: str) -> dict:
    out = {}
    for cm in schema.tables[table].columns:
        if cm.unique:
            out[cm.name] = set(schema.original_values.get((table, cm.name), []) or [])
    return out


def _pk_start(schema, table: str) -> int:
    """First fresh integer key after the compact rows (single-column integer PK)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    vals = [v for v in (schema.original_values.get((table, tm.primary_key[0]), []) or [])
            if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _apply_null_rule(cols: dict, table: str, schema, spec: Specification, rng) -> dict:
    """Plant NULLs in every nullable column: at least one, share from the specification."""
    for cm in schema.tables[table].columns:
        if not cm.notnull and cm.pk_pos == 0 and cm.name in cols:
            share = spec.null_share.get((table, cm.name), 0.10)
            n = len(cols[cm.name])
            if n == 0:
                continue
            k = max(1, int(round(share * n)))
            k = min(k, n)
            idx = rng.sample(range(n), k)
            for i in idx:
                cols[cm.name][i] = None
    return cols


def _dup_eligible(table: str, column: str, schema) -> bool:
    """A column may receive the duplicate share only if it is not part of any PK/UNIQUE tuple."""
    tm = schema.tables[table]
    for k in _key_tuples(tm):
        if column in k:
            return False
    return True


def _apply_duplicate_share(cols: dict, table: str, schema, spec: Specification, rng) -> dict:
    """For duplicates_for_distinct columns, repeat values so distinct is 20-50 % of rows."""
    for (t, c) in spec.dup:
        if t != table or c not in cols:
            continue
        if not _dup_eligible(table, c, schema):
            continue
        vals = cols[c]
        n = len(vals)
        if n < 2:
            continue
        target = max(1, int(n * rng.uniform(0.2, 0.5)))
        pool = [v for v in vals if v is not None]
        if not pool:
            continue
        distinct = list(dict.fromkeys(pool))[:target]
        if not distinct:
            continue
        for i in range(n):
            if vals[i] is not None:
                vals[i] = rng.choice(distinct)
        cols[c] = vals
    return cols


def _boundary_sampler(column, spec: Specification, rng):
    """Sampler over the boundary literal pool (case variants / one-char edits)."""
    key = (column.table, column.name)
    pool = spec.boundary.get(key)
    if not pool:
        return None
    return make_column_sampler(column, list(pool), 0.0, float('inf'), rng)


def build_random_instance(schema, literal_pool: dict, size, rng, spec: Specification = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification applied by construction."""
    spec = spec or default_specification()
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t, cm.name)
            if key in spec.enums:
                els = list(spec.enums[key])
                if key in spec.boundary:
                    els = els + [v for v in spec.boundary[key] if v not in els]
                samplers[key] = make_column_sampler(cm, els, 0.0, float('inf'), rng)
                continue
            if key in spec.boundary:
                s = _boundary_sampler(cm, spec, rng)
                if s is not None:
                    samplers[key] = s
                    continue
            if key in spec.ranges and cm.pk_pos == 0:
                lo, hi = spec.ranges[key]
                hi = hi if hi is not None else lo + 1000
                samplers[key] = _RangeSampler(lo, hi, rng)
                continue
            samplers[key] = _init_sampler(cm, literal_pool.get(key, []),
                                          schema.original_values.get(key, []), p, rng,
                                          len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    reserved_parents: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in samplers:
                cols[cm.name] = [samplers[key].sample() for _ in range(n)]
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols and all(isinstance(v, int) for v in cols[pk] if v is not None):
                start = _pk_start(schema, t)
                cols[pk] = [start + i for i in range(n)]
        inst[t] = cols
        fk = fill_foreign_keys_consistently(inst, schema, t, n, rng, spec.null_share,
                                            reserved=reserved_parents)
        cols.update(fk)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         _reserved_keys(schema, t).get(tuple(tm.primary_key), set()))
        cols = drop_unique_duplicates(tm, cols, _reserved_unique(schema, t))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(cols, t, schema, spec, rng)
        cols = _apply_duplicate_share(cols, t, schema, spec, rng)
        cols = _dedup_keys(tm, cols, _reserved_keys(schema, t))
        inst[t] = cols
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            reserved_parents[(t, pk)] = _reserved_parent_keys(schema, inst, t, pk, rng)
    return {t: inst[t] for t in schema.tables}


class _RangeSampler:
    """Uniform integer within [lo, hi]; includes boundary values and one step outside."""

    def __init__(self, lo: int, hi: int, rng):
        self.lo, self.hi, self.rng = int(lo), int(hi), rng

    def sample(self):
        r = self.rng.random()
        if r < 0.1:
            return self.lo
        if r < 0.2:
            return self.hi
        if r < 0.25:
            return self.lo - 1
        if r < 0.30:
            return self.hi + 1
        return self.rng.randint(self.lo, self.hi)
