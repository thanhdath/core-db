"""Instances = copy of compact DB + appended generated rows."""
import os
import random
import shutil
import sqlite3

from . import specification as S
from .schema import q
from .values import make_sampler, _safe_choice, _safe_sample, _safe_shuffle


def _compact_rows(schema, table: str) -> dict:
    """Return column -> list of compact values for a table."""
    names = [c.name for c in schema.tables[table].columns]
    ov = schema.original_values
    return {n: list(ov.get((table, n), [])) for n in names}


def _fk_lookup_values(parent_rows: dict, parent_col: str) -> list:
    return [v for v in parent_rows.get(parent_col, []) if v is not None]


def _target_sizes(spec: dict, table: str, rng: random.Random) -> int:
    base = spec['sizes'].get(table, 0)
    lo = int(base * 0.8)
    hi = int(base * 1.2)
    if hi < lo:
        hi = lo
    return rng.randint(lo, hi)


def _dedup(columns: dict, key_cols: list) -> dict:
    n = len(next(iter(columns.values()))) if columns else 0
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in key_cols if c in columns)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _compact_null_share(schema, table: str, column: str, fallback: float) -> float:
    """NULL share of a nullable column in the compact database, clamped to [0, 0.30]."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return max(0.0, min(0.30, fallback))
    n_null = sum(1 for v in vals if v is None)
    share = n_null / float(len(vals))
    return max(0.0, min(0.30, share))


def _force_nulls(cols: dict, column: str, nullable: bool, rng, share: float = 0.02,
                 min_count: int = 1) -> None:
    """Plant NULLs in a nullable column at the target share (>= min_count rows)."""
    if not nullable:
        return
    vals = cols.get(column)
    if not vals:
        return
    n = len(vals)
    target = max(min_count, int(round(share * n)))
    target = min(target, n)
    have = sum(1 for v in vals if v is None)
    need = target - have
    if need <= 0:
        return
    idxs = [i for i, v in enumerate(vals) if v is not None]
    _safe_shuffle(rng, idxs)
    for i in idxs[:need]:
        vals[i] = None


def _force_ties(cols: dict, column: str, min_tie: int, rng) -> None:
    """Force at least min_tie rows to share the maximum COUNT(*) value of a column."""
    vals = cols.get(column)
    if not vals or min_tie < 2:
        return
    counts: dict = {}
    for v in vals:
        if v is None:
            continue
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return
    top = max(counts.values())
    if top >= min_tie:
        return
    best = max(counts, key=lambda k: counts[k])
    need = min_tie - counts[best]
    idxs = [i for i, v in enumerate(vals) if v is not None and v != best]
    _safe_shuffle(rng, idxs)
    for i in idxs[:need]:
        vals[i] = best


def _seed_boundary_text(cols: dict, column: str, lits: list, rng) -> None:
    """Seed boundary literals into a column (overwriting sampled values)."""
    vals = cols.get(column)
    if not vals or not lits:
        return
    idxs = list(range(len(vals)))
    _safe_shuffle(rng, idxs)
    for j, L in enumerate(lits):
        if j < len(idxs):
            vals[idxs[j]] = L


def _seed_boundary_pk(cols: dict, column: str, lits: list, rng) -> None:
    """Reserve boundary PK literals as real keys before filling the rest of the sequence."""
    vals = cols.get(column)
    if not vals or not lits:
        return
    lit_set = set(lits)
    used = set(vals)
    free = [i for i, v in enumerate(vals) if v not in lit_set]
    _safe_shuffle(rng, free)
    for j, L in enumerate(lits):
        if L in used:
            continue
        if j < len(free):
            i = free[j]
            vals[i] = L
            used.add(L)


def _generate_geographic(schema, spec, pool, rng, n) -> dict:
    """Primary key first; city pool drives uniqueness (PK: no duplicates)."""
    city_sampler = make_sampler(schema, 'geographic', 'city',
                                [x for x in pool.get(('geographic', 'city'), [])],
                                spec, rng)
    county_sampler = make_sampler(schema, 'geographic', 'county',
                                  [x for x in pool.get(('geographic', 'county'), [])],
                                  spec, rng)
    region_sampler = make_sampler(schema, 'geographic', 'region',
                                  [x for x in pool.get(('geographic', 'region'), [])],
                                  spec, rng)
    cols = {
        'city': [city_sampler.draw() for _ in range(n)],
        'county': [county_sampler.draw() for _ in range(n)],
        'region': [region_sampler.draw() for _ in range(n)],
    }
    fallback = list(S.CITIES) or ['city']
    for i, v in enumerate(cols['city']):
        if v is None:
            base = _safe_choice(rng, fallback) or 'city'
            cols['city'][i] = base + str(rng.randint(1, 9999))
    lits = spec['boundary'].get(('geographic', 'city')) or []
    _seed_boundary_text(cols, 'city', lits, rng)
    cols = _dedup(cols, ['city'])
    _force_nulls(cols, 'county', True, rng,
                 _compact_null_share(schema, 'geographic', 'county', 0.02))
    _force_nulls(cols, 'region', True, rng,
                 _compact_null_share(schema, 'geographic', 'region', 0.02))
    _force_ties(cols, 'region', spec['ties'].get(('geographic', 'region'), 2), rng)
    _force_ties(cols, 'county', spec['ties'].get(('geographic', 'county'), 2), rng)
    return cols


def _generate_generalinfo(schema, spec, pool, rng, n, geographic_rows) -> dict:
    city_parents = _fk_lookup_values(geographic_rows, 'city')
    city_sampler = make_sampler(schema, 'generalinfo', 'city',
                                [x for x in pool.get(('generalinfo', 'city'), [])],
                                spec, rng)
    label_sampler = make_sampler(schema, 'generalinfo', 'label',
                                 [x for x in pool.get(('generalinfo', 'label'), [])],
                                 spec, rng)
    food_sampler = make_sampler(schema, 'generalinfo', 'food_type',
                                [x for x in pool.get(('generalinfo', 'food_type'), [])],
                                spec, rng)
    review_sampler = make_sampler(schema, 'generalinfo', 'review',
                                  [x for x in pool.get(('generalinfo', 'review'), [])],
                                  spec, rng)
    compact_ids = [v for v in schema.original_values.get(('generalinfo', 'id_restaurant'), [])
                   if isinstance(v, int)]
    start = (max(compact_ids) + 1) if compact_ids else 1
    cols = {
        'id_restaurant': list(range(start, start + n)),
        'label': [label_sampler.draw() for _ in range(n)],
        'food_type': [food_sampler.draw() for _ in range(n)],
        'city': [city_sampler.draw() for _ in range(n)],
        'review': [review_sampler.draw() for _ in range(n)],
    }
    lits = spec['boundary_num'].get(('generalinfo', 'id_restaurant')) or []
    _seed_boundary_pk(cols, 'id_restaurant', lits, rng)
    cols = _dedup(cols, ['id_restaurant'])
    for i, v in enumerate(cols['city']):
        if v is None:
            continue
        if city_parents and v not in city_parents:
            cols['city'][i] = rng.choice(city_parents)
        elif not city_parents:
            cols['city'][i] = None
    flits = spec['boundary'].get(('generalinfo', 'food_type')) or []
    _seed_boundary_text(cols, 'food_type', flits, rng)
    for i, v in enumerate(cols['review']):
        if v is not None:
            cols['review'][i] = min(5.0, max(1.0, float(v)))
    _force_nulls(cols, 'label', True, rng,
                 _compact_null_share(schema, 'generalinfo', 'label', 0.02))
    _force_nulls(cols, 'food_type', True, rng,
                 _compact_null_share(schema, 'generalinfo', 'food_type', 0.02))
    _force_nulls(cols, 'city', True, rng,
                 _compact_null_share(schema, 'generalinfo', 'city', 0.02))
    _force_nulls(cols, 'review', True, rng,
                 _compact_null_share(schema, 'generalinfo', 'review', 0.02))
    _ensure_groups_different(cols, 'food_type', 'review', rng)
    _force_ties(cols, 'food_type', spec['ties'].get(('generalinfo', 'food_type'), 2), rng)
    return cols


def _ensure_groups_different(cols: dict, group_col: str, value_col: str, rng):
    """Ensure every group with >= 2 non-NULL values has >= 2 distinct values."""
    buckets = {}
    for i, (g, v) in enumerate(zip(cols.get(group_col, []), cols.get(value_col, []))):
        if g is None or v is None:
            continue
        buckets.setdefault(g, []).append((i, v))
    for g, pairs in buckets.items():
        if len(pairs) < 2:
            continue
        if len({v for _, v in pairs}) >= 2:
            continue
        i, v = pairs[1]
        cols[value_col][i] = round(min(5.0, max(1.0, v + 0.3)), 1)


def _generate_location(schema, spec, pool, rng, n, geographic_rows, generalinfo_rows) -> dict:
    parent_ids = _fk_lookup_values(generalinfo_rows, 'id_restaurant')
    parent_cities = _fk_lookup_values(geographic_rows, 'city')

    city_sampler = make_sampler(schema, 'location', 'city',
                                [x for x in pool.get(('location', 'city'), [])],
                                spec, rng)
    street_sampler = make_sampler(schema, 'location', 'street_name',
                                  [x for x in pool.get(('location', 'street_name'), [])],
                                  spec, rng)
    num_sampler = make_sampler(schema, 'location', 'street_num',
                               [x for x in pool.get(('location', 'street_num'), [])],
                               spec, rng)

    uniq_parent_ids = sorted(set(parent_ids))
    if uniq_parent_ids:
        k = min(n, len(uniq_parent_ids))
        ids = _safe_sample(rng, uniq_parent_ids, k)
        if k < n:
            extra = [v for v in uniq_parent_ids if v not in set(ids)]
            _safe_shuffle(rng, extra)
            while len(ids) < n and extra:
                ids.append(extra.pop())
        m = len(ids)
        cols = {
            'id_restaurant': ids,
            'street_num': [num_sampler.draw() for _ in range(m)],
            'street_name': [street_sampler.draw() for _ in range(m)],
            'city': [city_sampler.draw() for _ in range(m)],
        }
    else:
        compact_ids = [v for v in schema.original_values.get(('location', 'id_restaurant'), [])
                       if isinstance(v, int)]
        start = (max(compact_ids) + 1) if compact_ids else 1
        cols = {
            'id_restaurant': list(range(start, start + n)),
            'street_num': [num_sampler.draw() for _ in range(n)],
            'street_name': [street_sampler.draw() for _ in range(n)],
            'city': [city_sampler.draw() for _ in range(n)],
        }
    for i, v in enumerate(cols['city']):
        if v is None:
            continue
        if parent_cities and v not in parent_cities:
            cols['city'][i] = rng.choice(parent_cities)
        elif not parent_cities:
            cols['city'][i] = None
    slits = spec['boundary'].get(('location', 'street_name')) or []
    _seed_boundary_text(cols, 'street_name', slits, rng)
    for i, v in enumerate(cols['street_num']):
        if v is not None:
            cols['street_num'][i] = max(1, min(9999, int(v)))
    _force_nulls(cols, 'street_num', True, rng,
                 _compact_null_share(schema, 'location', 'street_num', 0.048))
    _force_nulls(cols, 'street_name', True, rng,
                 _compact_null_share(schema, 'location', 'street_name', 0.02))
    _force_nulls(cols, 'city', True, rng,
                 _compact_null_share(schema, 'location', 'city', 0.15))
    _force_ties(cols, 'street_name', spec['ties'].get(('location', 'street_name'), 2), rng)
    return cols


def _construct_unmatched(gen_new, loc_new, rng):
    """Ensure unmatched_join_rows: >=2 NULL child FKs (parent rows without children are naturally present because not
    every parent is referenced)."""
    for cols, col in ((gen_new, 'city'), (loc_new, 'city')):
        vals = cols.get(col)
        if not vals:
            continue
        have = sum(1 for v in vals if v is None)
        need = 2 - have
        if need > 0:
            idxs = [i for i, v in enumerate(vals) if v is not None]
            _safe_shuffle(rng, idxs)
            for i in idxs[:need]:
                vals[i] = None


def build_and_write_instance(schema, pool: dict, orig_path: str, out_path: str,
                             rng: random.Random) -> dict:
    """Copy compact DB, generate rows in FK order, append them, and commit."""
    spec = S.get_spec()

    geo_compact = _compact_rows(schema, 'geographic')
    gen_compact = _compact_rows(schema, 'generalinfo')
    loc_compact = _compact_rows(schema, 'location')

    table_rows: dict = {}
    if 'geographic' in schema.tables:
        n = _target_sizes(spec, 'geographic', rng)
        geo_new = _generate_geographic(schema, spec, pool, rng, n)
        table_rows['geographic'] = geo_new
        geo_all = _merge(geo_compact, geo_new)
    else:
        geo_all = {}
    if 'generalinfo' in schema.tables:
        n = _target_sizes(spec, 'generalinfo', rng)
        gen_new = _generate_generalinfo(schema, spec, pool, rng, n, geo_all)
        table_rows['generalinfo'] = gen_new
        gen_all = _merge(gen_compact, gen_new)
    else:
        gen_all = {}
    if 'location' in schema.tables:
        n = _target_sizes(spec, 'location', rng)
        loc_new = _generate_location(schema, spec, pool, rng, n, geo_all, gen_all)
        table_rows['location'] = loc_new
    else:
        loc_new = {}

    _construct_unmatched(gen_new if 'generalinfo' in schema.tables else {},
                         loc_new, rng)

    return _write(schema, orig_path, out_path, table_rows)


def _merge(compact: dict, new: dict) -> dict:
    out = {}
    for c in compact:
        out[c] = list(compact[c]) + list(new.get(c, [])) if c in new else list(compact[c])
    for c in new:
        if c not in out:
            out[c] = list(new[c])
    return out


def _write(schema, orig_path: str, out_path: str, table_rows: dict) -> dict:
    """Copy orig, insert generated rows with executemany in one transaction."""
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    part = out_path + '.part'
    if os.path.exists(part):
        os.remove(part)
    shutil.copyfile(orig_path, part)
    added, skipped = {}, {}
    con = sqlite3.connect(part)
    try:
        con.execute('PRAGMA foreign_keys = OFF')
        con.execute('PRAGMA journal_mode = MEMORY')
        con.execute('PRAGMA synchronous = OFF')
        con.execute('PRAGMA temp_store = MEMORY')
        con.execute('BEGIN')
        for t, cols in table_rows.items():
            names = [c.name for c in schema.tables[t].columns]
            n = len(cols.get(names[0], [])) if names else 0
            added[t] = 0
            skipped[t] = 0
            if n == 0:
                continue
            payload = [tuple(cols[c][i] for c in names) for i in range(n)]
            sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
            try:
                con.executemany(sql, payload)
                added[t] = n
            except sqlite3.Error:
                for row in payload:
                    try:
                        con.execute(sql, row)
                        added[t] += 1
                    except (sqlite3.Error, OverflowError):
                        skipped[t] += 1
        con.commit()
    finally:
        con.close()
    os.chmod(part, 0o644)
    os.replace(part, out_path)
    return {t: (added[t], skipped[t]) for t in added}
