"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification rules."""
from .values import make_spec_sampler, IntRangeSampler
from .spec import column_spec


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row); first occurrence kept."""
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


def _compact_pk_tuples(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _compact_column(schema, table: str, column: str) -> list:
    return list(schema.original_values.get((table, column), []))


def _next_pk_start(schema, table: str, column: str) -> int:
    vals = [v for v in _compact_column(schema, table, column) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _plant_nulls(cols: dict, table: str, tm, schema, n: int, rng, null_targets: set) -> None:
    """NULL rule: plant NULL only in columns listed in null_targets and only if nullable."""
    if n <= 0 or not null_targets:
        return
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0:
            continue
        key = '%s.%s' % (table, cm.name)
        if key not in null_targets:
            continue
        i = rng.randrange(n)
        cols[cm.name][i] = None


def _fill_fk(schema, table: str, column: str, parent_pool: list, n: int, rng,
             duplicate_share=None, force_unmatched=False) -> list:
    """FK child column draws from the parent's compact+generated values."""
    if not parent_pool:
        return [None] * n
    vals = list(parent_pool)
    out = []
    for v in vals[:n]:
        out.append(v)
    while len(out) < n:
        if duplicate_share and out and rng.random() < rng.uniform(*duplicate_share):
            out.append(rng.choice(out))
        else:
            out.append(rng.choice(vals))
    rng.shuffle(out)
    if duplicate_share and n >= 2 and len(set(out)) == len(out):
        out[-1] = out[0]
        rng.shuffle(out)
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification table sizes (per instance), with small random variation."""
    base = spec.get('table_sizes') or {}
    sizes = {}
    for t in schema.tables:
        b = int(base.get(t, 0))
        if b <= 0:
            sizes[t] = 0
        else:
            sizes[t] = max(1, b + rng.choice((-1, 0, 0, 1)))
    return sizes


def _enforce_group_sizes(values: list, rng) -> list:
    """Post-process a column so that at least one group of size 1, one of size 2 and one of size >= 3 exist."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    bases = list(dict.fromkeys(out))
    if len(bases) < 3:
        return out
    rng.shuffle(bases)
    b1, b2, b3 = bases[0], bases[1], bases[2]
    out[0] = b1
    out[1] = b2
    out[2] = b2
    out[3] = b3
    out[4] = b3
    out[5] = b3
    rng.shuffle(out)
    return out


def _enforce_tie_rank(values: list, rank: int, rng) -> list:
    """Ensure at least two values tie at the given DESC rank (so ORDER BY ... LIMIT has a tie)."""
    n = len(values)
    if n < rank + 1:
        return values
    out = list(values)
    s = sorted(out, reverse=True)
    if len(s) > rank and s[rank - 1] != s[rank]:
        target = s[rank]
        for i, v in enumerate(out):
            if v == s[rank - 1]:
                out[i] = target
                break
    return out


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    null_targets = set(spec.get('null_targets') or [])

    pools: dict = {}
    for t in schema.tables:
        for cm in schema.tables[t].columns:
            pools[(t, cm.name)] = [v for v in _compact_column(schema, t, cm.name) if v is not None]

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            cspec = column_spec(spec, t, cm.name)
            kind = cspec.get('kind')
            if kind == 'int_pk':
                start = _next_pk_start(schema, t, cm.name)
                cols[cm.name] = [start + i for i in range(n)]
                continue
            sampler = make_spec_sampler(cm, cspec, literal_pool.get(key, []),
                                        schema.original_values.get(key, []), p, rng)
            vals = [sampler.sample() for _ in range(n)]
            if isinstance(sampler, IntRangeSampler) and n > 0:
                forced = sampler.seed_boundaries(n)
                for j, v in enumerate(forced):
                    vals[j] = v
            if cspec.get('group_sizes') and n >= 6:
                vals = _enforce_group_sizes(vals, rng)
            if cspec.get('tie_rank') and n >= cspec['tie_rank'] + 1:
                vals = _enforce_tie_rank(vals, int(cspec['tie_rank']), rng)
            cols[cm.name] = vals

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            cspec = column_spec(spec, t, cm.name)
            dup = cspec.get('duplicate_share') if cspec.get('kind') == 'int_fk' else None
            cols[cm.name] = _fill_fk(schema, t, cm.name, pools.get((pt, pc), []), n, rng,
                                     duplicate_share=dup)

        _plant_nulls(cols, t, tm, schema, n, rng, null_targets)

        taken = _compact_pk_tuples(schema, t)
        cols = sample_fresh_primary_keys(tm, cols, taken)
        cols = drop_unique_duplicates(tm, cols)

        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]

        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            pools[key] = pools.get(key, []) + [v for v in cols.get(cm.name, []) if v is not None]

    return {t: inst[t] for t in schema.tables}
