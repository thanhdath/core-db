"""Random instance construction (fuzz/fuzz.py:83-196) with the specification's semantic rules."""
import datetime as dt

from .values import (DateTextSampler, NameSampler, ObservedIntSampler, ObservedRealSampler,
                     PKTextSampler, _GIVEN_POOL, _SURNAME_POOL, _MONTHS, _SHORT_POOL)


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
    """Uniform rand_lin sizes w.p."""
    sizes = {}
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


def _spec_sizes(schema, rng) -> dict:
    """Table sizes per instance: Rooms 10, Reservations 600 (specification table_sizes_per_instance)."""
    sizes = {}
    for t in schema.tables:
        tl = t.lower()
        if tl == 'rooms':
            sizes[t] = 10
        elif tl == 'reservations':
            sizes[t] = 600
        else:
            sizes[t] = int(30 * rng.random() + rng.random() * 200)
    return sizes


def _parse_dmy(s: str):
    try:
        d, m, y = s.split('-')
        return dt.date(2000 + int(y), _MONTHS.index(m.upper()) + 1, int(d))
    except Exception:
        return None


def _fmt_dmy(d: dt.date) -> str:
    return '%02d-%s-%02d' % (d.day, _MONTHS[d.month - 1], d.year % 100)


def _compact_values(schema, table: str, column: str) -> list:
    """Original column values of a table (case-insensitive)."""
    for t, v in schema.original_values.items():
        if t[0].lower() == table.lower() and t[1].lower() == column.lower():
            return [x for x in v if x is not None]
    return []


def _compact_room_ids(schema) -> set:
    return {str(v) for v in _compact_values(schema, 'Rooms', 'RoomId')}


def _compact_max_code(schema) -> int:
    vals = [int(v) for v in _compact_values(schema, 'Reservations', 'Code') if isinstance(v, (int, float))]
    return max(vals) if vals else 0


def _plant_room_ids(schema, rng, n: int) -> list:
    """Distinct fresh 3-letter uppercase codes disjoint from the compact RoomId values."""
    reserved = _compact_room_ids(schema)
    s = PKTextSampler([], 0.0, float('inf'), rng, reserved=reserved)
    return [s.sample() for _ in range(n)]


def _forced_counts(n: int, k: int) -> list:
    """Deterministic count vector over k values summing to n (balanced, ties at rank 1)."""
    base = n // k
    rem = n % k
    return [base + (1 if i < rem else 0) for i in range(k)]


def _baseprice_domain(schema) -> list:
    """Observed basePrice values from the compact data (fallback to the known compact set)."""
    vals = [int(round(float(v))) for v in _compact_values(schema, 'Rooms', 'basePrice')
            if isinstance(v, (int, float))]
    return sorted(set(vals)) or [75, 100, 125, 150, 175, 250]


def _build_rooms(schema, rng, n: int) -> dict:
    """Rooms rows with the specification's domains and NULL rules."""
    tm = schema.tables.get('Rooms') or next((schema.tables[t] for t in schema.tables if t.lower() == 'rooms'), None)
    if tm is None:
        return {}
    cols: dict = {}
    ids = _plant_room_ids(schema, rng, n)
    cols['RoomId'] = ids
    pool = list(_SHORT_POOL[:3])
    counts = _forced_counts(n, 3)
    name_vals = []
    for k, c in enumerate(counts):
        name_vals.extend([pool[k]] * c)
    rng.shuffle(name_vals)
    cols['roomName'] = name_vals
    cols['beds'] = [rng.choice([1, 2]) for _ in range(n)]
    null_share = 0.05 + 0.25 * rng.random()
    bt = []
    for _ in range(n):
        bt.append(None if rng.random() < null_share else rng.choice(['King', 'Queen', 'Double']))
    if all(v is not None for v in bt) and n:
        bt[rng.randrange(n)] = None
    cols['bedType'] = bt
    cols['maxOccupancy'] = [rng.choice([2, 4]) for _ in range(n)]
    bp = ObservedIntSampler(_baseprice_domain(schema), 0.0, float('inf'), rng, step=25, nullable=False)
    prices = [bp.sample() for _ in range(n)]
    boundary = [140, 141, 142, 159, 160, 161]
    for k, v in enumerate(boundary):
        if k < n:
            prices[k] = v
    cols['basePrice'] = prices
    dec = ['modern', 'traditional', 'rustic']
    dc = _forced_counts(n, 3)
    decor = []
    for k, c in enumerate(dc):
        decor.extend([dec[k]] * c)
    rng.shuffle(decor)
    cols['decor'] = decor
    return cols


def _build_room_fk(room_ids: list, n: int, rng) -> list:
    """Controlled Reservations.Room multiset: 5% NULL, group sizes 1/2/>=3, at least one childless parent room."""
    if not room_ids:
        return [None] * n
    child_pool = room_ids[:-1] if len(room_ids) > 1 else room_ids
    n_null = max(1, int(round(0.05 * n)))
    n_nonnull = n - n_null
    k = len(child_pool)
    k = max(2, min(k, n_nonnull))
    chosen = child_pool[:k]
    counts = [1, 2, max(3, n_nonnull // 2)]
    if len(counts) > k:
        counts = counts[:k]
    counts = counts + [0] * (k - len(counts))
    rest = n_nonnull - sum(counts)
    if rest > 0:
        extra = rest // k
        for i in range(k):
            counts[i] += extra
        rem = rest - extra * k
        for i in range(rem):
            counts[i] += 1
    vals = []
    for c, v in zip(counts, chosen):
        vals.extend([v] * c)
    vals = vals[:n_nonnull]
    rng.shuffle(vals)
    out = vals + [None] * n_null
    rng.shuffle(out)
    return out


def _build_reservations(schema, rng, n: int, rooms: dict) -> dict:
    """Reservations rows with the specification's domains, boundaries and FK rule."""
    tm = schema.tables.get('Reservations') or next(
        (schema.tables[t] for t in schema.tables if t.lower() == 'reservations'), None)
    if tm is None:
        return {}
    cols: dict = {}
    start = _compact_max_code(schema) + 1
    cols['Code'] = list(range(start, start + n))
    room_ids = [r for r in rooms.get('RoomId', []) if r is not None]
    room_vals = _build_room_fk(room_ids, n, rng)
    cols['Room'] = room_vals
    ds = DateTextSampler([], 0.0, float('inf'), rng, nullable=False)
    ci, co = [], []
    for _ in range(n):
        a = ds.sample()
        b = ds.sample()
        da, db = _parse_dmy(a), _parse_dmy(b)
        if da is None or db is None:
            da = dt.date(2010, 1, 1)
            db = dt.date(2010, 1, 2)
        if db < da:
            da, db = db, da
        ci.append(_fmt_dmy(da))
        co.append(_fmt_dmy(db))
    cols['CheckIn'] = ci
    cols['CheckOut'] = co
    rs = ObservedRealSampler([90.0, 100.0, 150.0, 175.0, 201.25, 218.75, 287.5, 312.5], 0.0, float('inf'), rng,
                             step=6.25, nullable=False)
    rates = [rs.sample() for _ in range(n)]
    price_by_room = {}
    for rid, pr in zip(rooms.get('RoomId', []), rooms.get('basePrice', [])):
        if rid is not None and pr is not None:
            price_by_room[rid] = pr
    boundary_rows = [i for i in range(n) if room_vals[i] is not None and room_vals[i] in price_by_room][:6]
    offsets = [-1.0, 0.0, 1.0]
    for j, i in enumerate(boundary_rows):
        rates[i] = float(price_by_room[room_vals[i]]) + offsets[j % 3]
    cols['Rate'] = rates
    ln = NameSampler([], 0.0, float('inf'), rng, _SURNAME_POOL, nullable=False)
    fn = NameSampler([], 0.0, float('inf'), rng, _GIVEN_POOL, nullable=False)
    last = [ln.sample() for _ in range(n)]
    first = [fn.sample() for _ in range(n)]
    if n:
        last[0] = 'SWEAZY'
        first[0] = 'ROY'
    cols['LastName'] = last
    cols['FirstName'] = first
    cols['Adults'] = [rng.choice([1, 2, 3, 4]) for _ in range(n)]
    cols['Kids'] = [rng.choice([0, 1, 2, 3]) for _ in range(n)]
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification's semantic rules."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = _spec_sizes(schema, rng) if size is None else size
    inst: dict = {}
    for t in order:
        tl = t.lower()
        n = int(sizes.get(t, 0))
        if tl == 'rooms':
            cols = _build_rooms(schema, rng, n)
        elif tl == 'reservations':
            cols = _build_reservations(schema, rng, n, inst.get('Rooms', {}))
        else:
            cols = {}
        if not cols:
            continue
        tm = schema.tables[t]
        for cm in tm.columns:
            if cm.name in cols:
                continue
            key = (t, cm.name)
            if key in schema.fks:
                pt, pc = schema.fks[key]
                pv = inst.get(pt, {}).get(pc) or []
                cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols and cm.name in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables if t in inst}
