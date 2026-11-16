"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt
import re
import string

from .values import (_init_sampler, BOUNDARY, LIKE_VARIANTS, ENUM, DATE_FORMAT, DATE_RANGE,
                     POSITIVE, NONNEG, DUP_SHARE_COLUMNS, _rand_word, _rand_sentence, _perturb_str)

SPEC_SIZES = {'podcasts': 40, 'categories': 80, 'reviews': 200, 'runs': 12}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing: dict) -> dict:
    """Drop rows repeating any single unique column value or any composite UNIQUE tuple."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(existing.get((cm.name,), ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for uset in table_meta.unique_sets:
        if len(uset) <= 1 or not all(c in columns for c in uset):
            continue
        seen, keep = set(existing.get(tuple(uset), ())), []
        for i in range(_nrows(columns)):
            k = tuple(columns[c][i] for c in uset)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), [])) + list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes, varied per instance (0-230 rows, or level x4 capped at 2500)."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = SPEC_SIZES.get(t, 30)
                sizes[t] = max(0, int(base * rng.uniform(0.5, 1.5)))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _existing_keys(schema, table: str) -> dict:
    """Compact-db key tuples per unique set, so generated keys stay fresh."""
    tm = schema.tables[table]
    out = {}
    for cm in tm.columns:
        if cm.unique:
            out[(cm.name,)] = {v for v in schema.original_values.get((table, cm.name), []) if v is not None}
    for uset in tm.unique_sets:
        if len(uset) > 1:
            cols = [schema.original_values.get((table, c), []) for c in uset]
            n = min((len(c) for c in cols), default=0)
            out[tuple(uset)] = {tuple(c[i] for c in cols) for i in range(n)}
    return out


def _apply_null_rule(schema, table: str, cols: dict, n: int, rng) -> dict:
    """NULL rule: nullable columns get the compact db's NULL share, at least one NULL row."""
    for cm in schema.tables[table].columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
            continue
        share = schema.null_share.get((table, cm.name), 0.0)
        k = max(1, int(round(share * n))) if n > 0 else 0
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _apply_formulas(schema, table: str, cols: dict, n: int, rng) -> dict:
    """Semantic formulas by construction in Python (no SQL evaluation)."""
    tm = schema.tables[table]
    names = {c.name for c in tm.columns}
    if table == 'reviews' and 'rating' in names:
        cols['rating'] = [rng.choice(ENUM[('reviews', 'rating')]) for _ in range(n)]
    if table == 'runs':
        if 'max_rowid' in names:
            cols['max_rowid'] = [max(1, int(v)) if v is not None else None for v in cols['max_rowid']]
        if 'reviews_added' in names:
            cols['reviews_added'] = [max(0, int(v)) if v is not None else None for v in cols['reviews_added']]
    if table == 'podcasts':
        if 'itunes_id' in names:
            cols['itunes_id'] = [max(1, int(v)) if v is not None else None for v in cols['itunes_id']]
        if 'itunes_url' in names and 'slug' in names and 'itunes_id' in names:
            cols['itunes_url'] = ['https://podcasts.apple.com/us/podcast/%s/id%s' % (s, i)
                                  for s, i in zip(cols['slug'], cols['itunes_id'])]
    for c, (lo, hi) in DATE_RANGE.items():
        if c[0] == table and c[1] in names:
            fixed = []
            for v in cols[c[1]]:
                if v is None:
                    fixed.append(None)
                    continue
                s = str(v)
                try:
                    d = dt.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S' if 'T' in s else '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        d = dt.datetime.strptime(s[:10], '%Y-%m-%d')
                    except ValueError:
                        d = lo
                if d < lo:
                    d = lo
                if d > hi:
                    d = hi
                if DATE_FORMAT.get(c) == 'iso':
                    fixed.append(d.strftime('%Y-%m-%dT%H:%M:%S') + '-07:00')
                else:
                    fixed.append(d.strftime('%Y-%m-%d %H:%M:%S'))
            cols[c[1]] = fixed
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) to be appended to the compact database."""
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
        cols = _apply_formulas(schema, t, cols, n, rng)
        cols = _apply_null_rule(schema, t, cols, n, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns},
                                         _existing_keys(schema, t).get(tuple(tm.primary_key), set()))
        cols = drop_unique_duplicates(tm, cols, _existing_keys(schema, t))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
