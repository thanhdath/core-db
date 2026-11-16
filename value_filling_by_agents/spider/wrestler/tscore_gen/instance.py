"""Random instance construction (fuzz/fuzz.py:83-196) + specification-driven samplers."""
import re

from .values import _init_sampler

FRESH_SHARE = 0.15
DUP_SHARE = (0.20, 0.50)
NULL_SHARE = (0.05, 0.30)
MAX_ROWS = 230
LEVEL_CAP = 2500

SPEC_TABLE_SIZES = {'wrestler': 10, 'Elimination': 6}

LOCATION_POOL = ['Tokyo , Japan', 'tokyo , japan', 'Tokyo,Japan', 'tokyo,japan', 'J', 'j',
                 'Tokan', 'tokan', 'Tokyon', 'tokyon', 'o , J', 'o , j']
ELIMINATED_BY_POOL = ['Benjamin', 'benjamin', 'Orton', 'orton']
DAYS_HELD_BOUNDARY = [49, 50, 51]
REIGN_DOMAIN = ['1', '2']
TIME_RE = re.compile(r'^[0-5][0-9]:[0-5][0-9]$')
NAME_POOL = ['Rey Misterio Sr.', 'Fishman', 'Villaño IV', 'Gran Hamada', 'El Samurai',
             'The Great Sasuke §', 'Último Dragón §', 'Jushin Liger §']
TEAM_POOL = ['Team Orton', 'Team Batista']
MOVE_POOL = ['Go To Sleep', 'Paydirt', 'Rope hung DDT', 'Silver Spoon DDT',
             "World's Strongest Slam", 'Spear']
EVENT_POOL = ['Live event', 'Wrestling World 1997']


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_int_col(cm) -> bool:
    t = (cm.type_str or '').lower()
    return 'int' in t


def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _perturb_text(rng, v: str) -> str:
    """10-20 % near-variants: case, spacing, punctuation."""
    u = rng.random()
    if u < 0.25:
        return v.lower()
    if u < 0.5:
        return v.upper()
    if u < 0.7:
        return v.replace(' , ', ',')
    if u < 0.85:
        return v.replace(',', ' , ')
    return v + ' '


def _perturb_int(rng, v: int) -> int:
    """numbers +-1 / +-2."""
    return v + rng.choice([-2, -1, 1, 2])


def _fresh_text(rng, lo: int = 3, hi: int = 12) -> str:
    import string
    chars = string.ascii_letters + ' '
    return ''.join(rng.choice(chars) for _ in range(rng.randint(lo, hi))).strip() or 'x'


def _group_sizes(rng, n: int) -> list:
    """Group sizes '1, 2 and >= 3' summing to n (as far as possible)."""
    sizes, left = [], n
    while left > 0:
        s = rng.choice([1, 2, 3, 3, 4])
        s = min(s, left)
        sizes.append(s)
        left -= s
    return sizes


def _assign_groups(rng, n: int, pool: list) -> list:
    """Assign n rows to groups of sizes 1, 2 and >= 3 drawn from pool (duplicate share 20-50 %)."""
    if n <= 0:
        return []
    out = []
    idx = 0
    for s in _group_sizes(rng, n):
        val = pool[idx % len(pool)] if pool else _fresh_text(rng)
        idx += 1
        out.extend([val] * s)
    rng.shuffle(out)
    return out


def _reserve_boundary(rng, n: int, out: list, boundary_values: list, force_distinct: bool) -> None:
    """Overwrite reserved slots (indices 0..len(boundary_values)-1) with boundary values."""
    if n <= 0 or not boundary_values:
        return
    k = min(n, len(boundary_values))
    vals = list(boundary_values)
    rng.shuffle(vals)
    for i in range(k):
        out[i] = vals[i] if not force_distinct else vals[i % len(vals)]


def _force_duplicates(rng, n: int, out: list, protected: int = 0) -> None:
    """Force 20-50 % duplicate values among slots [protected, n) only."""
    lo = max(0, protected)
    span = n - lo
    if span < 2:
        return
    k = max(1, int(span * rng.uniform(*DUP_SHARE)))
    for _ in range(k):
        i = rng.randrange(lo, n)
        j = rng.randrange(lo, n)
        out[i] = out[j]


def _sample_location(rng, n: int, orig: list) -> list:
    """wrestler.Location: pool of 'City , Country' + near-variants, duplicate share 20-50 %, all comparison-boundary
    values present (reserved slots, ASC ties)."""
    pool = list(LOCATION_POOL) + [str(v) for v in orig if v is not None]
    out = []
    for _ in range(n):
        if rng.random() < FRESH_SHARE:
            out.append(_fresh_text(rng, 3, 10) + ' , ' + _fresh_text(rng, 3, 8))
        elif rng.random() < 0.5:
            out.append(rng.choice(pool))
        else:
            out.append(_perturb_text(rng, rng.choice(pool)))
    _force_duplicates(rng, n, out)
    _reserve_boundary(rng, n, out, LOCATION_POOL, force_distinct=True)
    return out


def _sample_days_held(rng, n: int, orig: list) -> list:
    """wrestler.Days_held: integer-valued strings >= 0, boundary 49/50/51 (reserved), duplicate share 20-50 %."""
    base = [v for v in (_to_int(x) for x in orig) if v is not None and v >= 0]
    out = []
    for _ in range(n):
        u = rng.random()
        if u < 0.3 + FRESH_SHARE:
            out.append(str(rng.randint(0, 1500)))
        elif base and u < 0.75:
            out.append(str(rng.choice(base)))
        else:
            v = rng.choice(base) if base else rng.randint(0, 1500)
            out.append(str(max(0, _perturb_int(rng, v))))
    _force_duplicates(rng, n, out)
    _reserve_boundary(rng, n, out, [str(v) for v in DAYS_HELD_BOUNDARY], force_distinct=True)
    return out


def _sample_reign(rng, n: int, orig: list) -> list:
    """wrestler.Reign IN ('1','2'), group sizes 1, 2 and >= 3 (ties on COUNT(*) at rank 1)."""
    return _assign_groups(rng, n, REIGN_DOMAIN)


def _sample_name(rng, n: int, orig: list) -> list:
    """wrestler.Name: distinct names + near-variants, group sizes 1, 2 and >= 3, duplicate share."""
    pool = list(NAME_POOL) + [str(v) for v in orig if v is not None]
    out = _assign_groups(rng, n, pool)
    for i in range(len(out)):
        if rng.random() < FRESH_SHARE:
            out[i] = _fresh_text(rng, 4, 14)
    rng.shuffle(out)
    return out


def _sample_event(rng, n: int, orig: list) -> list:
    pool = list(EVENT_POOL) + [str(v) for v in orig if v is not None]
    out = []
    for _ in range(n):
        if rng.random() < FRESH_SHARE:
            out.append(_fresh_text(rng, 4, 14))
        elif rng.random() < 0.5:
            out.append(rng.choice(pool))
        else:
            out.append(_perturb_text(rng, rng.choice(pool)))
    return out


def _sample_team(rng, n: int, orig: list) -> list:
    """Elimination.Team: group sizes 1, 2 and >= 3, duplicate share 20-50 %."""
    pool = list(TEAM_POOL) + [str(v) for v in orig if v is not None]
    return _assign_groups(rng, n, pool)


def _sample_eliminated_by(rng, n: int, orig: list) -> list:
    """Elimination.Eliminated_By: boundary values Benjamin/Orton (+case variants) reserved, NULL share 5-30 % (at
    least one NULL)."""
    pool = list(ELIMINATED_BY_POOL) + [str(v) for v in orig if v is not None]
    out = []
    for _ in range(n):
        if rng.random() < FRESH_SHARE:
            out.append(_fresh_text(rng, 3, 10))
        elif rng.random() < 0.5:
            out.append(rng.choice(pool))
        else:
            out.append(_perturb_text(rng, rng.choice(pool)))
    _reserve_boundary(rng, n, out, ELIMINATED_BY_POOL, force_distinct=False)
    if n > 0:
        protected = min(n, len(ELIMINATED_BY_POOL))
        k = max(1, int(n * rng.uniform(*NULL_SHARE)))
        k = min(k, n - protected) if n > protected else 0
        if k <= 0 and n > 0:
            k = 1
        candidates = list(range(protected, n))
        if candidates:
            for i in rng.sample(candidates, min(k, len(candidates))):
                out[i] = None
    return out


def _sample_move(rng, n: int, orig: list) -> list:
    pool = list(MOVE_POOL) + [str(v) for v in orig if v is not None]
    out = []
    for _ in range(n):
        if rng.random() < FRESH_SHARE:
            out.append(_fresh_text(rng, 4, 14))
        elif rng.random() < 0.5:
            out.append(rng.choice(pool))
        else:
            out.append(_perturb_text(rng, rng.choice(pool)))
    return out


def _sample_time(rng, n: int, orig: list) -> list:
    """Elimination.Time: 'MM:SS' with MM,SS in 00-59, duplicate share 20-50 %."""
    base = [str(v) for v in orig if v is not None and TIME_RE.match(str(v))]
    out = []
    for _ in range(n):
        if base and rng.random() < 0.5:
            out.append(rng.choice(base))
        else:
            out.append('%02d:%02d' % (rng.randrange(60), rng.randrange(60)))
    _force_duplicates(rng, n, out)
    return out


_SPECIAL = {
    ('wrestler', 'Location'): _sample_location,
    ('wrestler', 'Days_held'): _sample_days_held,
    ('wrestler', 'Reign'): _sample_reign,
    ('wrestler', 'Name'): _sample_name,
    ('wrestler', 'Event'): _sample_event,
    ('Elimination', 'Team'): _sample_team,
    ('Elimination', 'Eliminated_By'): _sample_eliminated_by,
    ('Elimination', 'Elimination_Move'): _sample_move,
    ('Elimination', 'Time'): _sample_time,
}


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


def _fresh_pk_values(cm, n: int, existing: set, rng) -> list:
    """Fresh PK values against the compact rows (sequential integers / integer strings)."""
    out = []
    if _is_int_col(cm):
        start = max([v for v in existing if isinstance(v, int)] + [0]) + 1
        for k in range(n):
            out.append(start + k)
    else:
        ints = [v for v in (_to_int(x) for x in existing) if v is not None]
        start = (max(ints) if ints else 0) + 1
        for k in range(n):
            out.append(str(start + k))
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = max(1, int(min_c + int(rng.random() * 200)))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = max(1, int(min(s, LEVEL_CAP)))
            s *= 4
    return sizes


def _compact_columns(schema, t: str) -> dict:
    """Compact rows of table t as {column: [values]} (read-only, never changed)."""
    tm = schema.tables[t]
    return {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as compact rows + appended generated rows."""
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
    compact = {t: _compact_columns(schema, t) for t in schema.tables}

    gen: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        n = max(0, min(n, MAX_ROWS))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            fn = _SPECIAL.get((t, cm.name))
            if fn is not None:
                cols[cm.name] = fn(rng, n, schema.original_values.get((t, cm.name), []))
            else:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        gen[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = gen[t]
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                existing = set(compact[t].get(cm.name, []))
                cols[cm.name] = _fresh_pk_values(cm, len(cols[cm.name]), existing, rng)

    for t in order:
        tm = schema.tables[t]
        cols = gen[t]
        if cols:
            cols = filter_rows(tm, cols)
            gen[t] = cols

    for t in order:
        tm = schema.tables[t]
        cols = gen[t]
        n = len(cols[next(iter(cols))]) if cols else 0
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            final_parent = set()
            for v in gen.get(pt, {}).get(pc, []):
                if v is not None:
                    final_parent.add(v)
            for v in compact.get(pt, {}).get(pc, []):
                if v is not None:
                    final_parent.add(v)
            if not final_parent:
                cols[cm.name] = [None] * n
                continue
            pv = sorted(final_parent, key=str)
            vals = [rng.choice(pv) for _ in range(n)]
            if not cm.notnull and n > 0:
                k = max(1, int(n * rng.uniform(*NULL_SHARE)))
                k = min(k, n)
                for i in rng.sample(range(n), k):
                    vals[i] = None
            cols[cm.name] = [v if (v is None or v in final_parent) else rng.choice(pv) for v in vals]
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols and cm.name in cols:
                final = set(v for v in cols[pc] if v is not None)
                cols[cm.name] = [v if (v is None or v in final) else (rng.choice(sorted(final, key=str)) if final else None)
                                 for v in cols[cm.name]]
        gen[t] = cols

    out = {}
    for t in schema.tables:
        tm = schema.tables[t]
        g = gen.get(t, {})
        merged = {}
        for cm in tm.columns:
            merged[cm.name] = list(compact[t].get(cm.name, [])) + list(g.get(cm.name, []))
        out[t] = merged
    return out


def filter_rows(table_meta, columns: dict) -> dict:
    """Keep the first occurrence of each PK tuple and each unique column value consistently."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    keep = list(range(n))
    if table_meta.primary_key:
        seen, kept = set(), []
        for i in keep:
            k = tuple(columns[c][i] for c in table_meta.primary_key)
            if k not in seen:
                seen.add(k)
                kept.append(i)
        keep = kept
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns and keep:
            seen, kept = set(), []
            for i in keep:
                v = columns[cm.name][i]
                if v not in seen:
                    seen.add(v)
                    kept.append(i)
            keep = kept
    return _filter(columns, keep)
