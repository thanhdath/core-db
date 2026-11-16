"""Random instance construction (fuzz/fuzz.py:83-196) + round-1 specification by construction."""
import re

from .values import _init_sampler, _near_variant, _like_variants

TABLE_SIZES = {'venue': 20, 'author': 60, 'dataset': 20, 'journal': 20, 'keyphrase': 40,
               'paper': 200, 'cite': 300, 'paperDataset': 150, 'paperKeyphrase': 300, 'writes': 300}

BOUNDARY_NUMERIC = {
    ('paper', 'paperId'): [1057, 1058, 1059],
    ('writes', 'paperId'): [-1, 0, 1, 2009, 2010, 2011],
    ('paper', 'year'): [2010, 2011, 2012, 2014, 2015, 2016],
    ('paper', 'venueId'): [2014, 2015, 2016],
    ('venue', 'venueId'): [2014, 2015, 2016],
    ('paperKeyphrase', 'paperId'): [0, 1, 2, 3],
    ('author', 'authorId'): [0, 1, 2],
    ('writes', 'authorId'): [0, 1, 2],
}

BOUNDARY_TEXT = {
    ('author', 'authorName'): ['michael i. jordan', 'MICHAEL I. JORDAN', 'Mark Steedman', 'mark steedman',
                               'Samuel Madden', 'samuel madden'],
    ('venue', 'venueName'): ['ACL', 'acl', 'nature communications', 'NATURE COMMUNICATIONS', 'PVLDB', 'pvldb'],
    ('keyphrase', 'keyphraseName'): ['deep learning', 'DEEP LEARNING', 'Genetic Identity', 'genetic identity',
                                     'question answering', 'QUESTION ANSWERING'],
    ('dataset', 'datasetName'): ['ImageNet', 'imagenet', 'PVLDB', 'pvldb', 'eNet', 'enet'],
}

LIKE_VARIANTS = {
    ('author', 'authorName'): ['Noah Smith'],
    ('keyphrase', 'keyphraseName'): ['%parsing%', '%convolutional%', '%neural networks%'],
    ('dataset', 'datasetName'): ['ImageNet'],
}

DISTINCT_TARGETS = {('paper', 'paperId'), ('writes', 'paperId'), ('cite', 'citedPaperId'),
                    ('author', 'authorId'), ('paper', 'venueId')}

TIE_RANK_TARGETS = {('paper', 'paperId'), ('paper', 'year')}

NULL_TARGETS = {('paper', 'venueId'), ('paper', 'journalId'), ('paper', 'numCiting'), ('paper', 'numCitedBy'),
                ('paper', 'title'), ('venue', 'venueName'), ('author', 'authorName'), ('dataset', 'datasetName'),
                ('journal', 'journalName'), ('keyphrase', 'keyphraseName')}
NULL_SHARE = 0.20

YEAR_LO, YEAR_HI = 1990, 2020
COUNT_LO, COUNT_HI = 0, 5000

UNMATCHED_SHARE = 0.15


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


def drop_unique_sets(table_meta, columns: dict) -> dict:
    """Drop rows repeating any composite UNIQUE tuple (round-1 addition)."""
    for uset in getattr(table_meta, 'unique_sets', []) or []:
        if not all(c in columns for c in uset):
            continue
        n = len(next(iter(columns.values())))
        seen, keep = set(), []
        for i in range(n):
            k = tuple(columns[c][i] for c in uset)
            if k not in seen:
                seen.add(k)
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


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes with per-instance variation (0-230 rows per table, or level x4 capped at 2500)."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = TABLE_SIZES.get(t, 30)
                jitter = int(base * (0.7 + 0.6 * rng.random()))
                sizes[t] = max(0, min(230, jitter))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _fresh_pk_values(schema, table: str, n: int, rng) -> list:
    """Sequential integers starting at 1, fresh against the compact PKs of the table."""
    tm = schema.tables[table]
    pk = tm.primary_key
    if len(pk) != 1:
        return None
    col = pk[0]
    existing = set()
    for tup in schema.original_pks.get(table, []):
        if tup and tup[0] is not None:
            existing.add(tup[0])
    start = 1
    if existing:
        start = max(existing) + 1
    vals = []
    v = start
    while len(vals) < n:
        if v not in existing:
            vals.append(v)
        v += 1
    return vals


def _plant_boundary_numeric(cols: dict, col: str, values: list, rng) -> None:
    """boundary_numeric: emit L-1, L, L+1 for each listed literal L."""
    if col not in cols:
        return
    n = len(cols[col])
    if n == 0:
        return
    planted = []
    for L in values:
        planted.extend([L - 1, L, L + 1])
    for i, v in enumerate(planted):
        if i >= n:
            break
        cols[col][i] = v


def _plant_boundary_text(cols: dict, col: str, values: list, rng) -> None:
    """boundary_text: exact L, lower(L), upper(L), one near-variant."""
    if col not in cols:
        return
    n = len(cols[col])
    if n == 0:
        return
    planted = []
    for L in values:
        planted.extend([L, L.lower(), L.upper(), _near_variant(L, rng)])
    for i, v in enumerate(planted):
        if i >= n:
            break
        cols[col][i] = v


def _plant_like_variants(cols: dict, col: str, literals: list, rng) -> None:
    """like_near_variant: base token, typo, upper-case, trailing-char variants."""
    if col not in cols:
        return
    n = len(cols[col])
    if n == 0:
        return
    planted = []
    for lit in literals:
        planted.extend(_like_variants(lit, rng))
    for i, v in enumerate(planted):
        if i >= n:
            break
        cols[col][i] = v


def _plant_duplicates(cols: dict, col: str, rng) -> None:
    """duplicate_share: 20-50% of rows repeat an earlier value."""
    if col not in cols:
        return
    n = len(cols[col])
    if n < 2:
        return
    share = 0.2 + 0.3 * rng.random()
    k = int(n * share)
    for _ in range(k):
        i = rng.randrange(1, n)
        j = rng.randrange(0, i)
        cols[col][i] = cols[col][j]


def _plant_ties(cols: dict, col: str, rng) -> None:
    """tie_rank: at least two rows share the boundary value."""
    if col not in cols:
        return
    n = len(cols[col])
    if n < 2:
        return
    v = cols[col][0]
    cols[col][1] = v


def _apply_null_rule(cols: dict, table: str, col: str, rng) -> None:
    """NULL rule: at least one NULL row per nullable column, share ~20%."""
    if col not in cols:
        return
    n = len(cols[col])
    if n == 0:
        return
    k = max(1, int(n * NULL_SHARE))
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs[:k]:
        cols[col][i] = None


def _apply_semantic_rules(cols: dict, table: str, rng) -> None:
    """Semantic rules by construction (paper.year range, counts >= 0, cite self-exclusion)."""
    if table == 'paper':
        if 'year' in cols:
            cols['year'] = [None if v is None else max(YEAR_LO, min(YEAR_HI, int(v))) for v in cols['year']]
        for c in ('numCiting', 'numCitedBy'):
            if c in cols:
                cols[c] = [None if v is None else max(COUNT_LO, min(COUNT_HI, int(v))) for v in cols[c]]
    if table == 'cite':
        if 'citingPaperId' in cols and 'citedPaperId' in cols:
            n = len(cols['citingPaperId'])
            for i in range(n):
                if cols['citingPaperId'][i] is not None and cols['citingPaperId'][i] == cols['citedPaperId'][i]:
                    cols['citedPaperId'][i] = (cols['citedPaperId'][i] or 0) + 1


def _apply_unmatched_join(schema, instance: dict, table: str, rng) -> None:
    """unmatched_join_rows: leave 10-20% of parent PKs unreferenced by any child row."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            continue
        keep_n = max(1, int(len(pv) * (1.0 - UNMATCHED_SHARE)))
        keep = set(rng.sample(pv, min(keep_n, len(pv))))
        col = instance[table].get(cm.name)
        if col is None:
            continue
        for i, v in enumerate(col):
            if v is not None and v not in keep:
                col[i] = rng.choice(list(keep)) if keep else None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the round-1 specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                lo = hi = None
                if (t, cm.name) == ('paper', 'year'):
                    lo, hi = YEAR_LO, YEAR_HI
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), lo=lo, hi=hi)
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
        pk_vals = _fresh_pk_values(schema, t, n, rng)
        if pk_vals is not None and tm.primary_key:
            cols[tm.primary_key[0]] = pk_vals
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        cols = drop_unique_sets(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        cols = inst[t]
        for (tt, cc), vals in BOUNDARY_NUMERIC.items():
            if tt == t:
                _plant_boundary_numeric(cols, cc, vals, rng)
        for (tt, cc), vals in BOUNDARY_TEXT.items():
            if tt == t:
                _plant_boundary_text(cols, cc, vals, rng)
        for (tt, cc), lits in LIKE_VARIANTS.items():
            if tt == t:
                _plant_like_variants(cols, cc, lits, rng)
        for (tt, cc) in DISTINCT_TARGETS:
            if tt == t:
                _plant_duplicates(cols, cc, rng)
        for (tt, cc) in TIE_RANK_TARGETS:
            if tt == t:
                _plant_ties(cols, cc, rng)
        for (tt, cc) in NULL_TARGETS:
            if tt == t:
                _apply_null_rule(cols, tt, cc, rng)
        _apply_semantic_rules(cols, t, rng)
    for t in order:
        _apply_unmatched_join(schema, inst, t, rng)
    return {t: inst[t] for t in schema.tables}
