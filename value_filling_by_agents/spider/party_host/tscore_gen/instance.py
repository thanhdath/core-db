"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
from .values import _init_sampler


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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact parent values + generated parent values (in memory)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with a small per-instance jitter (0-230 rows)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 0)
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, min(230, base + jitter))
    if 'host' in sizes:
        sizes['host'] = max(sizes['host'], len(spec.AGE_BOUNDARY))
    if 'party_host' in sizes and 'party' in sizes and 'host' in sizes:
        n_child = sizes['party_host']
        while sizes['party'] * sizes['host'] < n_child:
            sizes['party'] += 1
            sizes['host'] += 1
    return sizes


def _null_share_for(table: str, col: str) -> float:
    if (table, col) in spec.NOT_NULL_COLUMNS:
        return 0.0
    return spec.NULL_SHARE


def _plant_nulls(values: list, share: float, rng, protect: set = None) -> list:
    """Plant NULLs: at least one row when share > 0, otherwise none."""
    if share <= 0.0 or not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    k = min(k, n)
    candidates = [i for i in range(n) if not protect or i not in protect]
    if not candidates:
        return values
    k = min(k, len(candidates))
    idx = rng.sample(candidates, k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _dup_pool(pool: list, n: int, share: float, rng) -> list:
    """Draw n values from pool with a duplicate share in [20%, 50%]."""
    if not pool:
        return [None] * n
    n_dup = max(1, int(round(n * share)))
    n_uniq = max(1, n - n_dup)
    uniq = [rng.choice(pool) for _ in range(n_uniq)]
    dups = [rng.choice(uniq) for _ in range(n_dup)]
    vals = uniq + dups
    rng.shuffle(vals)
    return vals


def _sample_age(n: int, rng) -> tuple:
    """Ages in [18,60] with boundary literals 34,35,36,44,45,46 present."""
    boundary = list(spec.AGE_BOUNDARY)
    assert n >= len(boundary), 'host row count must cover the age boundary set'
    vals = list(boundary)
    while len(vals) < n:
        vals.append(rng.randint(spec.AGE_MIN, spec.AGE_MAX))
    vals = vals[:n]
    order = list(range(n))
    rng.shuffle(order)
    vals = [vals[i] for i in order]
    protected = {i for i, v in enumerate(vals) if v in spec.AGE_BOUNDARY}
    return [str(v) for v in vals], protected


def _sample_year(n: int, rng) -> list:
    return [str(rng.randint(spec.YEAR_MIN, spec.YEAR_MAX)) for _ in range(n)]


def _sample_last_year(first_years: list, n: int, rng) -> list:
    """Last_year >= First_year (SQL three-valued: NULL operands unconstrained)."""
    out = []
    for i in range(n):
        fy = first_years[i] if i < len(first_years) else None
        if fy is None:
            out.append(str(rng.randint(spec.YEAR_MIN, spec.YEAR_MAX)))
        else:
            lo = max(spec.YEAR_MIN, int(fy))
            out.append(str(rng.randint(lo, spec.YEAR_MAX)))
    return out


def _sample_number_of_hosts(n: int, rng) -> list:
    """Positive ints; ensure >= 2 distinct non-NULL values (rows_with_different_values)."""
    vals = [rng.randint(spec.HOSTS_MIN, spec.HOSTS_MAX) for _ in range(n)]
    if n >= 2 and len(set(vals)) < 2:
        vals[0] = spec.HOSTS_MIN
        vals[1] = spec.HOSTS_MAX
    return vals


def _sample_bool(n: int, rng) -> list:
    return [rng.choice([1, 0]) for _ in range(n)]


def _sample_party_theme(n: int, rng) -> list:
    return _dup_pool(spec.PARTY_THEMES, n, spec.DUP_SHARE, rng)


def _sample_location(n: int, rng) -> list:
    return _dup_pool(spec.LOCATIONS, n, spec.DUP_SHARE, rng)


def _sample_name(n: int, rng) -> list:
    return _dup_pool(spec.HOST_NAMES, n, spec.DUP_SHARE, rng)


def _sample_nationality(n: int, rng) -> list:
    return _dup_pool(spec.NATIONALITIES, n, spec.DUP_SHARE, rng)


def _fresh_pk(existing: set, n: int, rng) -> list:
    """Sequential-ish fresh integers not colliding with compact/generated keys."""
    out = []
    start = (max(existing) + 1) if existing else 1
    cur = start
    while len(out) < n:
        if cur not in existing:
            out.append(cur)
            existing.add(cur)
        cur += 1
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz/fuzz.py:111-196) with the specification applied."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
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
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols

    _apply_spec(schema, inst, rng, size)
    return {t: inst[t] for t in schema.tables}


def _apply_spec(schema, inst: dict, rng, size: dict) -> None:
    """Overwrite sampled columns with specification-conforming values."""
    if 'host' in inst:
        h = inst['host']
        n = len(h.get('Host_ID', []))
        if n:
            existing = set(v for v in schema.original_values.get(('host', 'Host_ID'), []) if v is not None)
            h['Host_ID'] = _fresh_pk(existing, n, rng)
            h['Name'] = _plant_nulls(_sample_name(n, rng), _null_share_for('host', 'Name'), rng)
            h['Nationality'] = _plant_nulls(_sample_nationality(n, rng),
                                            _null_share_for('host', 'Nationality'), rng)
            age_vals, age_protected = _sample_age(n, rng)
            h['Age'] = _plant_nulls(age_vals, _null_share_for('host', 'Age'), rng, protect=age_protected)
            non_null = {v for v in h['Age'] if v is not None}
            for b in spec.AGE_BOUNDARY:
                assert str(b) in non_null, 'age boundary literal %r missing' % b

    if 'party' in inst:
        p = inst['party']
        n = len(p.get('Party_ID', []))
        if n:
            existing = set(v for v in schema.original_values.get(('party', 'Party_ID'), []) if v is not None)
            p['Party_ID'] = _fresh_pk(existing, n, rng)
            p['Party_Theme'] = _plant_nulls(_sample_party_theme(n, rng),
                                            _null_share_for('party', 'Party_Theme'), rng)
            p['Location'] = _plant_nulls(_sample_location(n, rng),
                                         _null_share_for('party', 'Location'), rng)
            first = _plant_nulls(_sample_year(n, rng), _null_share_for('party', 'First_year'), rng)
            p['First_year'] = first
            p['Last_year'] = _plant_nulls(_sample_last_year(first, n, rng),
                                          _null_share_for('party', 'Last_year'), rng)
            p['Number_of_hosts'] = _plant_nulls(_sample_number_of_hosts(n, rng),
                                                _null_share_for('party', 'Number_of_hosts'), rng)

    if 'party_host' in inst:
        ph = inst['party_host']
        n = len(ph.get('Party_ID', []))
        if n:
            party_pool = _parent_pool(inst, schema, 'party', 'Party_ID')
            host_pool = _parent_pool(inst, schema, 'host', 'Host_ID')
            party_pool, party_reserved = _reserve_childless(party_pool, rng)
            host_pool, host_reserved = _reserve_childless(host_pool, rng)
            pairs = _draw_unique_pairs(party_pool, host_pool, n, rng)
            ph['Party_ID'] = [a for a, _ in pairs]
            ph['Host_ID'] = [b for _, b in pairs]
            ph['Is_Main_in_Charge'] = _plant_nulls(_sample_bool(n, rng),
                                                   _null_share_for('party_host', 'Is_Main_in_Charge'), rng)
            _verify_childless(schema, inst, party_reserved, host_reserved)
            assert len(set(pairs)) == n, 'party_host composite PK tuples not unique'
            assert len(ph['Party_ID']) == n, 'party_host row count mismatch'


def _reserve_childless(pool: list, rng) -> tuple:
    """Return (sampling_pool, reserved_pk) with at least one element kept childless."""
    if len(pool) >= 2:
        drop = rng.randrange(len(pool))
        return pool[:drop] + pool[drop + 1:], pool[drop]
    return pool, None


def _draw_unique_pairs(party_pool: list, host_pool: list, n: int, rng) -> list:
    """Draw n unique (Party_ID, Host_ID) pairs without replacement."""
    if not party_pool or not host_pool:
        raise ValueError('empty parent pool for party_host composite PK')
    cross = len(party_pool) * len(host_pool)
    if cross < n:
        raise ValueError('party_host cross product %d < %d' % (cross, n))
    seen, out = set(), []
    max_attempts = n * 100 + 1000
    attempts = 0
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        a = rng.choice(party_pool)
        b = rng.choice(host_pool)
        if (a, b) not in seen:
            seen.add((a, b))
            out.append((a, b))
    if len(out) < n:
        for a in party_pool:
            for b in host_pool:
                if (a, b) not in seen:
                    seen.add((a, b))
                    out.append((a, b))
                    if len(out) == n:
                        break
            if len(out) == n:
                break
    assert len(set(out)) == n, 'party_host composite PK tuples not unique'
    return out


def _verify_childless(schema, inst: dict, party_reserved, host_reserved) -> None:
    """Assert at least one parent PK in host and party is unreferenced."""
    ph = inst.get('party_host', {})
    gen_party = set(v for v in ph.get('Party_ID', []) if v is not None)
    gen_host = set(v for v in ph.get('Host_ID', []) if v is not None)
    compact_party = set(v for v in schema.original_values.get(('party_host', 'Party_ID'), []) if v is not None)
    compact_host = set(v for v in schema.original_values.get(('party_host', 'Host_ID'), []) if v is not None)
    ref_party = gen_party | compact_party
    ref_host = gen_host | compact_host
    all_party = set(v for v in schema.original_values.get(('party', 'Party_ID'), []) if v is not None)
    all_party |= set(v for v in inst.get('party', {}).get('Party_ID', []) if v is not None)
    all_host = set(v for v in schema.original_values.get(('host', 'Host_ID'), []) if v is not None)
    all_host |= set(v for v in inst.get('host', {}).get('Host_ID', []) if v is not None)
    assert all_party - ref_party, 'no childless party row'
    assert all_host - ref_host, 'no childless host row'
