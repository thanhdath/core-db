"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .spec import time_ladder_ok
from .values import _init_sampler, TimeLadderSampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (compact rows or earlier generated rows); first kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def drop_unique_tuples(unique_tuples: list, table: str, columns: dict, taken: set) -> dict:
    """Drop rows repeating a composite UNIQUE / PK tuple (record(Swimmer_ID, Event_ID))."""
    for t, cols in unique_tuples:
        if t != table or not all(c in columns for c in cols):
            continue
        n = len(next(iter(columns.values())))
        seen, keep = set(taken), []
        for i in range(n):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact+generated values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        col = '%s.%s' % (table, cm.name)
        nullable = not cm.notnull and cm.pk_pos == 0
        share = spec.get('null_share', {}).get(col, 0.0)
        vals = []
        for _ in range(n):
            if nullable and (rng.random() < max(share, 1.0 / max(n, 1))):
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification sizes (table_sizes_per_instance) with per-instance variation; else fuzz sizes."""
    sizes = {}
    fixed = spec.get('table_sizes') or {}
    if fixed:
        for t in schema.tables:
            base = int(fixed.get(t, 0))
            if base <= 0:
                sizes[t] = 0
                continue
            jitter = rng.choice([-1, 0, 0, 1])
            sizes[t] = max(1, base + jitter)
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _pk_start(schema, table: str, rng) -> int:
    """First fresh integer PK value above the compact maximum."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    pk = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None):
    """Build one random instance (fuzz.py:111-196) as *appended* rows."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    ladders = {}
    for t in order:
        tm = schema.tables[t]
        ladder = spec.get('time_ladders', {}).get(t)
        if ladder:
            ladders[t] = TimeLadderSampler(ladder, {c: schema.original_values.get((t, c), []) for c in ladder}, rng)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if ladder and cm.name in ladder:
                continue
            col = '%s.%s' % (t, cm.name)
            meta = spec.get('tables', {}).get(t, {}).get(cm.name, {})
            kind = meta.get('kind')
            enum = spec.get('enums', {}).get(col)
            rng_ = spec.get('ranges', {}).get(col)
            lo, hi = (rng_[0], rng_[1]) if rng_ else (None, None)
            boundary = spec.get('boundaries', {}).get(col)
            lit = spec.get('literal_pool', {}).get(col)
            if kind == 'pk' and cm.pk_pos > 0:
                start = _pk_start(schema, t, rng)
                samplers[(t, cm.name)] = ('pk', start)
                continue
            if col in spec.get('year_text', set()):
                samplers[(t, cm.name)] = ('year', lo if lo is not None else 1900,
                                          hi if hi is not None else 2030)
                continue
            samplers[(t, cm.name)] = _init_sampler(
                cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                p, rng, len(tm.primary_key), kind=kind, lo=lo, hi=hi, boundary=boundary,
                pool_literals=lit, enum=enum)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    dropped: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if t in ladders and cm.name in ladders[t].ladder:
                continue
            s = samplers.get((t, cm.name))
            if isinstance(s, tuple) and s[0] == 'pk':
                cols[cm.name] = [s[1] + i for i in range(n)]
            elif isinstance(s, tuple) and s[0] == 'year':
                lo, hi = s[1], s[2]
                cols[cm.name] = [str(rng.randint(int(lo), int(hi))) for _ in range(n)]
            elif s is not None:
                cols[cm.name] = [s.sample() for _ in range(n)]
        if t in ladders:
            rows = [ladders[t].sample_row() for _ in range(n)]
            for c in ladders[t].ladder:
                cols[c] = [r[c] for r in rows]
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
                continue
            col = '%s.%s' % (t, cm.name)
            share = spec.get('null_share', {}).get(col, 0.0)
            k = max(1, int(round(share * n)))
            if n > 0 and not any(v is None for v in cols[cm.name]):
                for j in rng.sample(range(n), min(k, n)):
                    cols[cm.name][j] = None
        taken_pk = set()
        if tm.primary_key:
            rows = list(zip(*[schema.original_values.get((t, c), []) for c in tm.primary_key]))
            taken_pk = set(rows)
        cols = sample_fresh_primary_keys(tm, cols, taken_pk)
        taken_u = {cm.name: set(v for v in schema.original_values.get((t, cm.name), []) if v is not None)
                   for cm in tm.columns if cm.unique}
        cols = drop_unique_duplicates(tm, cols, taken_u)
        taken_t = set()
        for ut, uc in spec.get('unique_tuples', []):
            if ut == t:
                taken_t |= set(zip(*[schema.original_values.get((t, c), []) for c in uc]))
        cols = drop_unique_tuples(spec.get('unique_tuples', []), t, cols, taken_t)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        if t in ladders:
            n2 = len(next(iter(cols.values()))) if cols else 0
            keep = []
            for i in range(n2):
                row = {c: cols[c][i] for c in cols}
                if time_ladder_ok(spec, t, row):
                    keep.append(i)
            dropped[t] = n2 - len(keep)
            cols = _filter(cols, keep)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}, dropped
