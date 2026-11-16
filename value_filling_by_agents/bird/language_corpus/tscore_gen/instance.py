"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, _like_near_variants

SPEC_SIZES = {'langs': 1, 'words': 200, 'pages': 120, 'langs_words': 200, 'pages_words': 230, 'biwords': 230}

BOUNDARIES = {
    ('langs', 'lid'): [0, 1, 2],
    ('pages', 'lid'): [0, 1, 2],
    ('langs_words', 'lid'): [0, 1, 2],
    ('biwords', 'lid'): [0, 1, 2],
    ('words', 'wid'): [7, 8, 9, 8967, 8968, 8969],
    ('langs_words', 'occurrences'): [179, 180, 181, 199999, 200000, 200001],
    ('biwords', 'w1st'): [0, 1, 2, 85, 86, 87],
    ('words', 'occurrences'): [15999, 16000, 16001, 199999, 200000, 200001],
    ('biwords', 'w2nd'): [108, 109, 110, 8967, 8968, 8969],
    ('pages', 'words'): [9, 10, 11, 9999, 10000, 10001],
}
TEXT_BOUNDARIES = {
    ('langs', 'lang'): ['ca', 'CA'],
    ('words', 'word'): ['\u00e0bac', '\u00c0BAC', 'xin\u00e8s', 'XIN\u00c8S', 'grec', 'GREC'],
    ('pages', 'title'): ['Llista de conflictes armats', 'llista de conflictes armats', 'Anys 90', 'anys 90',
                         'Afluent', 'afluent'],
}
LIKE_NEAR = {
    ('pages', 'title'): ['%Art%', '%Art', 'Art%', 'Art', 'Aru', 'Art x', 'art', 'x Art'],
}

DEFAULT_NULL_SHARE = 0.05


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
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
    """Drop rows repeating any UNIQUE tuple (composite keys included)."""
    if not columns:
        return columns
    for t, cols in schema.unique_tuples:
        if t != table or not all(c in columns for c in cols):
            continue
        n = _n_rows(columns)
        seen, keep = set(), []
        for i in range(n):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _assign_autoincrement_pks(schema, table: str, n: int, rng) -> list:
    """Fresh sequential PKs not present in the compact rows, with planted boundaries."""
    pk = schema.autoincrement.get(table)
    if pk is None:
        return None
    existing = {v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)}
    start = (max(existing) + 1) if existing else 1
    seq = list(range(start, start + n))
    bnd = [b for b in BOUNDARIES.get((table, pk), []) if isinstance(b, int) and b not in existing]
    if bnd:
        planted = list(dict.fromkeys(bnd))
        rest = [v for v in seq if v not in set(planted)]
        vals = (planted + rest)[:n]
        if len(vals) < n:
            extra = start + n
            while len(vals) < n:
                if extra not in existing and extra not in vals:
                    vals.append(extra)
                extra += 1
        return vals
    return seq


def _final_parent_keys(inst: dict, schema, table: str, col: str) -> list:
    """Final parent key values (compact + generated) for FK sampling."""
    vals = list(inst.get(table, {}).get(col, []) or [])
    vals += [v for v in schema.original_values.get((table, col), []) if v is not None]
    return vals


def _null_share(schema, table: str, col: str) -> float:
    """Per-column NULL share from the compact database (at least one NULL row)."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return DEFAULT_NULL_SHARE
    n_null = sum(1 for v in vals if v is None)
    share = n_null / float(len(vals))
    return max(share, 1.0 / max(1, len(vals)))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's FINAL rows (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _final_parent_keys(instance, schema, pt, pc)
        nullable = (not cm.notnull) and cm.pk_pos == 0
        share = _null_share(schema, table, cm.name) if nullable else 0.0
        col = []
        for _ in range(n):
            if nullable and rng.random() < share:
                col.append(None)
            elif pv:
                col.append(rng.choice(pv))
            else:
                col.append(None if nullable else None)
        if nullable and n > 0 and all(v is not None for v in col):
            col[rng.randrange(n)] = None
        out[cm.name] = col
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Exact specification sizes (no jitter)."""
    return {t: int(SPEC_SIZES.get(t, 100)) for t in schema.tables}


def _plant_nulls(schema, table: str, cols: dict, rng) -> None:
    """NULL rule: at least one NULL row per nullable column, compact NULL share."""
    tm = schema.tables[table]
    n = _n_rows(cols)
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        share = _null_share(schema, table, cm.name)
        idx = rng.randrange(n)
        cols[cm.name][idx] = None
        for i in range(n):
            if rng.random() < share:
                cols[cm.name][i] = None


def _recompute_aggregates(schema, inst: dict) -> None:
    """Trigger-maintained aggregates computed in Python from the FINAL in-memory rows."""
    if 'langs' in inst and 'pages' in inst and 'lid' in inst['langs']:
        cnt = {}
        for lid in inst['pages'].get('lid', []):
            if lid is not None:
                cnt[lid] = cnt.get(lid, 0) + 1
        if 'pages' in inst['langs']:
            inst['langs']['pages'] = [cnt.get(l, 0) if l is not None else 0 for l in inst['langs']['lid']]
    if 'langs' in inst and 'langs_words' in inst and 'lid' in inst['langs']:
        cnt = {}
        for lid in inst['langs_words'].get('lid', []):
            if lid is not None:
                cnt[lid] = cnt.get(lid, 0) + 1
        if 'words' in inst['langs']:
            inst['langs']['words'] = [cnt.get(l, 0) if l is not None else 0 for l in inst['langs']['lid']]
    if 'pages' in inst and 'pages_words' in inst and 'pid' in inst['pages']:
        cnt = {}
        for pid in inst['pages_words'].get('pid', []):
            if pid is not None:
                cnt[pid] = cnt.get(pid, 0) + 1
        if 'words' in inst['pages']:
            inst['pages']['words'] = [cnt.get(p, 0) if p is not None else 0 for p in inst['pages']['pid']]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of appended rows (fuzz.py:111-196)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                key = (t, cm.name)
                bnd = BOUNDARIES.get(key, [])
                near = _like_near_variants(LIKE_NEAR.get(key, [])) + TEXT_BOUNDARIES.get(key, [])
                samplers[key] = _init_sampler(cm, literal_pool.get(key, []),
                                              schema.original_values.get(key, []), p, rng,
                                              len(tm.primary_key), boundaries=bnd, near_variants=near)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if t in schema.autoincrement:
            pk = schema.autoincrement[t]
            cols[pk] = _assign_autoincrement_pks(schema, t, n, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        cols = drop_unique_tuples(schema, t, cols)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, _n_rows(cols), rng))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _plant_nulls(schema, t, cols, rng)
        inst[t] = cols
    _recompute_aggregates(schema, inst)
    return {t: inst[t] for t in schema.tables}
