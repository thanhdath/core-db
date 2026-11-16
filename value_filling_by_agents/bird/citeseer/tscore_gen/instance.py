"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler

SPEC_SIZES = {'paper': 40, 'cites': 60, 'content': 200}
CLASS_ENUM = {'Agents', 'IR', 'ML', 'AI', 'DB', 'HCI'}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
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


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes per instance, with small random variation (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = SPEC_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        sizes[t] = max(0, min(230, base + rng.randint(-5, 5)))
    return sizes


def _compact_keys(schema, table: str, col: str) -> list:
    return [v for v in schema.original_values.get((table, col), []) if v is not None]


def _enforce_rules(schema, table: str, cols: dict, rng) -> dict:
    """Semantic rules by construction (Python, never SQL)."""
    t = table.lower()
    if t == 'cites':
        cited = cols.get('cited_paper_id', [])
        citing = cols.get('citing_paper_id', [])
        for i in range(len(cited)):
            if cited[i] is not None and cited[i] == citing[i]:
                pass
    if t == 'content':
        w = cols.get('word_cited_id', [])
        for i, v in enumerate(w):
            if v is None or not str(v).startswith('word'):
                w[i] = 'word%d' % rng.randint(1, 4000)
    if t == 'paper':
        c = cols.get('class_label', [])
        for i, v in enumerate(c):
            if v not in CLASS_ENUM:
                c[i] = rng.choice(sorted(CLASS_ENUM))
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of appended rows (fuzz.py:111-196)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact = {t: {c.name: _compact_keys(schema, t, c.name) for c in schema.tables[t].columns}
               for t in schema.tables}
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        taken = set()
        if tm.primary_key and len(tm.primary_key) == 1:
            taken = set(compact[t].get(tm.primary_key[0], []))
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), taken=taken)
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
        cols = _enforce_rules(schema, t, cols, rng)
        taken = set()
        if tm.primary_key and len(tm.primary_key) == 1:
            taken = set(compact[t].get(tm.primary_key[0], []))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
