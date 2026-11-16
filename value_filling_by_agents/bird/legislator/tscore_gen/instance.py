"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, null_share, BOUNDARY, NOT_NULL, is_numeric_boundary_column

BASE_SIZES = {'current': 40, 'current-terms': 120, 'historical': 40, 'historical-terms': 40, 'social-media': 35}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns.get(c, [None] * n)[i] for c in table_meta.primary_key)
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


def fill_foreign_keys_consistently(existing: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (generated first, else compact) with replacement; empty parent ->
    NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = existing.get(pt, {}).get(pc)
        if not pv:
            pv = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Base sizes from the specification with per-instance variation (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = BASE_SIZES.get(t, 40)
        lo = max(0, int(base * 0.5))
        hi = min(230, int(base * 1.5) + 1)
        sizes[t] = rng.randint(lo, hi)
    return sizes


def _apply_null_rule(table: str, columns: dict, rng) -> dict:
    """NULL is a value: each nullable column gets NULL rows with the compact share and at least one NULL row."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for c, vals in columns.items():
        if (table, c) in NOT_NULL:
            for i in range(n):
                if vals[i] is None:
                    raise ValueError('NULL in NOT NULL column %s.%s' % (table, c))
            continue
        share = null_share(table, c)
        if share <= 0.0 or (table, c) not in _NULLABLE_TABLES:
            continue
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            vals[i] = None
    return columns


_NULLABLE_TABLES = {
    ('current', 'ballotpedia_id'), ('current', 'birthday_bio'), ('current', 'cspan_id'),
    ('current', 'fec_id'), ('current', 'first_name'), ('current', 'gender_bio'),
    ('current', 'google_entity_id_id'), ('current', 'govtrack_id'), ('current', 'house_history_id'),
    ('current', 'icpsr_id'), ('current', 'lis_id'), ('current', 'maplight_id'), ('current', 'middle_name'),
    ('current', 'nickname_name'), ('current', 'official_full_name'), ('current', 'opensecrets_id'),
    ('current', 'religion_bio'), ('current', 'suffix_name'), ('current', 'thomas_id'),
    ('current', 'votesmart_id'), ('current', 'wikidata_id'), ('current', 'wikipedia_id'),
    ('current-terms', 'address'), ('current-terms', 'caucus'), ('current-terms', 'chamber'),
    ('current-terms', 'class'), ('current-terms', 'contact_form'), ('current-terms', 'district'),
    ('current-terms', 'fax'), ('current-terms', 'last'), ('current-terms', 'name'), ('current-terms', 'office'),
    ('current-terms', 'party'), ('current-terms', 'party_affiliations'), ('current-terms', 'phone'),
    ('current-terms', 'relation'), ('current-terms', 'rss_url'), ('current-terms', 'start'),
    ('current-terms', 'state'), ('current-terms', 'state_rank'), ('current-terms', 'title'),
    ('current-terms', 'type'), ('current-terms', 'url'),
    ('historical', 'ballotpedia_id'), ('historical', 'bioguide_previous_id'), ('historical', 'birthday_bio'),
    ('historical', 'cspan_id'), ('historical', 'fec_id'), ('historical', 'google_entity_id_id'),
    ('historical', 'house_history_alternate_id'), ('historical', 'house_history_id'), ('historical', 'icpsr_id'),
    ('historical', 'lis_id'), ('historical', 'maplight_id'), ('historical', 'middle_name'),
    ('historical', 'nickname_name'), ('historical', 'official_full_name'), ('historical', 'opensecrets_id'),
    ('historical', 'religion_bio'), ('historical', 'suffix_name'), ('historical', 'thomas_id'),
    ('historical', 'votesmart_id'),
    ('historical-terms', 'address'), ('historical-terms', 'chamber'), ('historical-terms', 'class'),
    ('historical-terms', 'contact_form'), ('historical-terms', 'district'), ('historical-terms', 'fax'),
    ('historical-terms', 'last'), ('historical-terms', 'middle'), ('historical-terms', 'name'),
    ('historical-terms', 'office'), ('historical-terms', 'party'), ('historical-terms', 'party_affiliations'),
    ('historical-terms', 'phone'), ('historical-terms', 'relation'), ('historical-terms', 'rss_url'),
    ('historical-terms', 'state'), ('historical-terms', 'state_rank'), ('historical-terms', 'title'),
    ('historical-terms', 'type'), ('historical-terms', 'url'),
    ('social-media', 'facebook'), ('social-media', 'facebook_id'), ('social-media', 'govtrack'),
    ('social-media', 'instagram'), ('social-media', 'instagram_id'), ('social-media', 'thomas'),
    ('social-media', 'twitter'), ('social-media', 'twitter_id'), ('social-media', 'youtube'),
    ('social-media', 'youtube_id'),
}


def _enforce_start_le_end(table: str, columns: dict) -> dict:
    """start <= end in Python (SQL three-valued logic: only non-NULL operands are constrained)."""
    if 'start' not in columns or 'end' not in columns:
        return columns
    for i in range(len(columns['start'])):
        s, e = columns['start'][i], columns['end'][i]
        if s is not None and e is not None and str(s) > str(e):
            columns['start'][i], columns['end'][i] = e, s
    return columns


def _plant_boundaries(table: str, columns: dict, rng) -> dict:
    """Guarantee each boundary literal appears at least once (exact value, no variant)."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for (tt, col), vals in BOUNDARY.items():
        if tt != table or col not in columns or not vals:
            continue
        if (table, col) in NOT_NULL and any(v is None for v in vals):
            continue
        idxs = list(range(n))
        rng.shuffle(idxs)
        for j, v in enumerate(vals):
            if j >= len(idxs):
                break
            if is_numeric_boundary_column(table, col) and v in ('', 'x'):
                columns[col][idxs[j]] = v
            else:
                columns[col][idxs[j]] = v
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification rules by construction."""
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
        existing = dict(inst)
        existing[t] = cols
        fks = fill_foreign_keys_consistently(existing, schema, t, n, rng)
        cols.update(fks)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _plant_boundaries(t, cols, rng)
        cols = _apply_null_rule(t, cols, rng)
        cols = _enforce_start_le_end(t, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
