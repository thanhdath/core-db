"""Specification-driven instance construction: append fresh rows to a copy of the compact DB."""
import datetime as dt
import random
import sqlite3

from .schema import q
from .sampler import ValuePool, parse_ts, stable_hash, _is_int_type, _is_real_type, _is_datetime_type
from .spec import load_specificateion

_TS_LO = dt.datetime(2005, 1, 1)
_TS_HI = dt.datetime(2006, 2, 15)


def _read_compact_rows(orig_path: str, schema) -> dict:
    """Read all compact rows per table into memory (dict table -> list of row tuples)."""
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig_path, uri=True)
    try:
        out = {}
        for t, tm in schema.tables.items():
            sel = 'select %s from %s order by rowid' % (', '.join(q(c.name) for c in tm.columns), q(t))
            try:
                out[t] = con.execute(sel).fetchall()
            except sqlite3.Error:
                out[t] = []
        return out
    finally:
        con.close()


def _build_pools(schema, literal_pool, spec, rng):
    enums = spec.get('enums', {})
    ranges = spec.get('ranges', {})
    exceptions = spec.get('comparison_boundary', {})
    like_variants = spec.get('like_variants', {})
    pools = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            obs = [r for r in schema.original_values.get((t, cm.name), []) if r is not None]
            key = '%s.%s' % (t, cm.name)
            literals = [str(v) for v in literal_pool.get((t, cm.name), [])]
            exc = list(enums.get(key, [])) + list(exceptions.get(key, [])) + list(like_variants.get(key, []))
            r = ranges.get(key)
            if r:
                exc += _range_boundaries(r, cm.type_str)
            pools[(t, cm.name)] = ValuePool(cm.type_str, obs, literals, exc, rng)
    return pools


def _range_boundaries(r, t):
    lo, hi = r
    step = 1 if _is_int_type(t) else 0.01
    return [lo - step, lo, lo + step, hi - step, hi, hi + step]


def _fits_range(r, v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return True
    return r[0] <= f <= r[1]


def _plant_null(i, n, kname, null_targets):
    """Deterministic NULL placement: at least one NULL and at least one non-NULL per nullable column."""
    if kname not in null_targets:
        return False
    if n < 2:
        return False
    if i == 0:
        return True
    return (stable_hash(kname, i) % 100) < 10


def _plant_boundary_ts(kname):
    return kname in ('rental.rental_date', 'payment.payment_date', 'rental.return_date')


def _draw_boundary_ts(rng):
    base = dt.datetime(2005, 5, 27) if rng.random() < 0.5 else dt.datetime(2005, 6, 1)
    base += dt.timedelta(days=rng.randint(-1, 1))
    return base.strftime('%Y-%m-%d %H:%M:%S.0')


def _ts_in(rng):
    d = _TS_LO + dt.timedelta(seconds=rng.randint(0, int((_TS_HI - _TS_LO).total_seconds())))
    return d.strftime('%Y-%m-%d %H:%M:%S.0')


def _existing_pk_max(schema, t, col):
    vals = [v for v in schema.original_values.get((t, col), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _plant_boundary_values(vals, boundary, rng, n, fits=None):
    """Overwrite up to len(boundary) positions with boundary literals (respecting fits)."""
    if not boundary or n == 0:
        return vals
    cand = [b for b in boundary if fits is None or fits(b)]
    if not cand:
        return vals
    k = min(len(cand), max(1, n // 8))
    positions = rng.sample(range(n), k)
    for pos, b in zip(positions, cand[:k]):
        vals[pos] = b
    return vals


def _apply_semantics(t, tm, built, enums, ranges, rng, spec, parent_pool):
    """Compute dependent / derived columns in Python from sampled values (never via SQL)."""
    boundary = spec.get('comparison_boundary', {})
    if t == 'customer':
        if 'active' in built and built['active']:
            built['active'] = [rng.choice(enums.get('customer.active', [0, 1])) for _ in built['active']]
        if 'store_id' in built and built['store_id']:
            pv = parent_pool.get(('store', 'store_id')) or [1, 2]
            built['store_id'] = [rng.choice(pv) for _ in built['store_id']]
    if t == 'staff':
        if 'active' in built and built['active']:
            built['active'] = [rng.choice(enums.get('staff.active', [0, 1])) for _ in built['active']]
        if 'store_id' in built and built['store_id']:
            pv = parent_pool.get(('store', 'store_id')) or [1, 2]
            built['store_id'] = [rng.choice(pv) for _ in built['store_id']]
    if t == 'film':
        if 'rental_duration' in built:
            built['rental_duration'] = [rng.choice(enums.get('film.rental_duration', [3, 4, 5, 6, 7]))
                                        for _ in built['rental_duration']]
            built['rental_duration'] = _plant_boundary_values(
                built['rental_duration'], boundary.get('film.rental_duration'), rng,
                len(built['rental_duration']), fits=lambda v: 3 <= int(v) <= 7)
        if 'rental_rate' in built:
            built['rental_rate'] = [rng.choice(enums.get('film.rental_rate', [0.99, 2.99, 4.99]))
                                    for _ in built['rental_rate']]
            built['rental_rate'] = _plant_boundary_values(
                built['rental_rate'], boundary.get('film.rental_rate'), rng,
                len(built['rental_rate']), fits=lambda v: float(v) in (0.99, 2.99, 4.99))
        if 'rating' in built:
            built['rating'] = [None if v is None else rng.choice(enums.get('film.rating', ['G']))
                               for v in built['rating']]
            built['rating'] = _plant_boundary_values(
                built['rating'], boundary.get('film.rating'), rng, len(built['rating']),
                fits=lambda v: v in ('G', 'PG', 'PG-13', 'R', 'NC-17'))
        if 'replacement_cost' in built:
            r = ranges.get('film.replacement_cost', [9.99, 29.99])
            built['replacement_cost'] = [None if v is None else round(rng.uniform(r[0], r[1]), 2)
                                         for v in built['replacement_cost']]
        if 'length' in built:
            r = ranges.get('film.length', [46, 185])
            built['length'] = [None if v is None else rng.randint(r[0], r[1]) for v in built['length']]
            built['length'] = _plant_boundary_values(
                built['length'], boundary.get('film.length'), rng, len(built['length']),
                fits=lambda v: 46 <= int(v) <= 185)
    if t == 'payment':
        if 'amount' in built:
            r = ranges.get('payment.amount', [0.0, 999.99])
            built['amount'] = [round(rng.uniform(max(r[0], 0.0), r[1]), 2) for _ in built['amount']]
        if 'payment_date' in built:
            built['payment_date'] = [_ts_in(rng) for _ in built['payment_date']]
            built['payment_date'] = _plant_boundary_values(
                built['payment_date'], boundary.get('payment.payment_date'), rng,
                len(built['payment_date']),
                fits=lambda v: '2005-01-01' <= str(v)[:10] <= '2006-02-15')
    if t == 'rental':
        if 'rental_date' in built:
            built['rental_date'] = [_ts_in(rng) for _ in built['rental_date']]
            built['rental_date'] = _plant_boundary_values(
                built['rental_date'], boundary.get('rental.rental_date'), rng, len(built['rental_date']))
        if 'return_date' in built and 'rental_date' in built:
            out = []
            for i, rd in enumerate(built['return_date']):
                if rd is None:
                    out.append(None)
                    continue
                base = parse_ts(built['rental_date'][i]) or _TS_LO
                delta = dt.timedelta(days=rng.randint(1, 10), seconds=rng.randint(0, 86399))
                out.append((base + delta).strftime('%Y-%m-%d %H:%M:%S.0'))
            built['return_date'] = out


def _composite_pairs(parent_a, parent_b, n, rng):
    """Unique (a, b) tuples drawn from two parent pools."""
    if not parent_a or not parent_b:
        return []
    seen = set()
    out = []
    tries = 0
    max_tries = max(1000, n * 50)
    while len(out) < n and tries < max_tries:
        tries += 1
        a = rng.choice(parent_a)
        b = rng.choice(parent_b)
        if (a, b) in seen:
            continue
        seen.add((a, b))
        out.append((a, b))
    return out


def build_spec_instance(schema, literal_pool: dict, rng: random.Random, db_id: str, orig_path: str = '') -> dict:
    """Build one instance as a dict of table -> column -> list of appended values."""
    spec = load_specificateion()
    pools = _build_pools(schema, literal_pool, spec, rng)
    sizes = dict(spec.get('table_sizes_per_instance', {}))
    enums = spec.get('enums', {})
    ranges = spec.get('ranges', {})
    null_targets = set(spec.get('null_targets', []))
    inst_sizes = {}
    for t, base in sizes.items():
        inst_sizes[t] = 0 if base == 0 else max(1, min(230, int(base * rng.uniform(0.5, 1.5))))

    parent_pool = {}
    for t, tm in schema.tables.items():
        for pc in tm.primary_key:
            vals = list(schema.original_values.get((t, pc), []))
            parent_pool[(t, pc)] = [v for v in vals if v is not None]

    inst = {t: {cm.name: [] for cm in schema.tables[t].columns} for t in schema.tables
            if t in inst_sizes and inst_sizes[t] > 0}

    order = [t for lvl in schema.table_order for t in lvl]
    for t in order:
        if t not in inst:
            continue
        tm = schema.tables[t]
        n = inst_sizes[t]
        cols = inst[t]
        built = {c: None for c in cols}
        if len(tm.primary_key) >= 2:
            pk_cols = tm.primary_key
            pa = parent_pool.get(schema.fks.get((t, pk_cols[0]), (None, None)), [])
            pb = parent_pool.get(schema.fks.get((t, pk_cols[1]), (None, None)), [])
            pairs = _composite_pairs(pa, pb, n, rng)
            for cm in tm.columns:
                if cm.name == pk_cols[0]:
                    built[cm.name] = [p[0] for p in pairs]
                elif cm.name == pk_cols[1]:
                    built[cm.name] = [p[1] for p in pairs]
            for cm in tm.columns:
                if built[cm.name] is not None:
                    continue
                key = (t, cm.name)
                kname = '%s.%s' % (t, cm.name)
                if key in schema.fks:
                    pt, pc = schema.fks[key]
                    pv = parent_pool.get((pt, pc), [])
                    nullable = not cm.notnull
                    vals = []
                    for i in range(len(pairs)):
                        if nullable and _plant_null(i, len(pairs), kname, null_targets):
                            vals.append(None)
                        elif pv:
                            vals.append(rng.choice(pv))
                        else:
                            vals.append(None)
                    built[cm.name] = vals
                else:
                    pool = pools[key]
                    nullable = not cm.notnull
                    vals = []
                    for i in range(len(pairs)):
                        if nullable and _plant_null(i, len(pairs), kname, null_targets):
                            vals.append(None)
                        else:
                            vals.append(pool.draw(None))
                    built[cm.name] = vals
            for cm in tm.columns:
                cols[cm.name] = built[cm.name] if built[cm.name] is not None else [None] * len(pairs)
            continue
        for cm in tm.columns:
            key = (t, cm.name)
            kname = '%s.%s' % (t, cm.name)
            r = ranges.get(kname)
            if key in schema.fks:
                pt, pc = schema.fks[key]
                pv = parent_pool.get((pt, pc), [])
                nullable = not cm.notnull
                vals = []
                for i in range(n):
                    if nullable and _plant_null(i, n, kname, null_targets):
                        vals.append(None)
                    elif pv:
                        vals.append(rng.choice(pv))
                    else:
                        vals.append(None)
                built[cm.name] = vals
                continue
            if cm.pk_pos > 0:
                existing = _existing_pk_max(schema, t, cm.name)
                start = existing + 1
                built[cm.name] = list(range(start, start + n))
                if len(tm.primary_key) == 1:
                    parent_pool.setdefault((t, cm.name), []).extend(built[cm.name])
                continue
            pool = pools[key]
            nullable = not cm.notnull
            vals = []
            for i in range(n):
                if nullable and _plant_null(i, n, kname, null_targets):
                    vals.append(None)
                    continue
                if kname in enums:
                    vals.append(rng.choice(enums[kname]))
                else:
                    val = pool.draw((lambda x, r=r: _fits_range(r, x) and not _is_datetime_type(cm.type_str))
                                    if r and not _is_datetime_type(cm.type_str) else None)
                    if _is_datetime_type(cm.type_str) and _plant_boundary_ts(kname):
                        val = _draw_boundary_ts(rng)
                    vals.append(val)
            built[cm.name] = vals
        _apply_semantics(t, tm, built, enums, ranges, rng, spec, parent_pool)
        for cm in tm.columns:
            cols[cm.name] = built[cm.name] if built[cm.name] is not None else [None] * n

    if 'film_text' in inst and 'film' in inst:
        film_cols = inst['film']
        film_ids = film_cols.get('film_id', [])
        titles = film_cols.get('title', [])
        descs = film_cols.get('description', [])
        n_ft = len(inst['film_text'].get('film_id', []))
        if n_ft and film_ids:
            k = min(n_ft, len(film_ids))
            inst['film_text']['film_id'] = list(film_ids[:k])
            inst['film_text']['title'] = list(titles[:k])
            inst['film_text']['description'] = list(descs[:k])
            for c in inst['film_text']:
                if c not in ('film_id', 'title', 'description'):
                    inst['film_text'][c] = inst['film_text'][c][:k]
    return inst
