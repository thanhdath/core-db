"""Random instance construction (fuzz/fuzz.py:83-196) + append-only over-construction."""
import random

from .values import _init_sampler

SPEC_SIZES = {'track': 9, 'race': 7}
CLASS_VARIANTS = ['GT', 'gt', 'DP/GT', 'GT ']
TRACK_NAMES = ['Auto Club Speedway', 'Chicagoland Speedway', 'Darlington Raceway',
               'Daytona International Speedway', 'Homestead-Miami Speedway', 'Kansas Speedway',
               'Martinsville Speedway', 'Michigan International Speedway']
TRACK_LOCATIONS = ['Fontana, CA', 'Joliet, IL', 'Darlington, SC', 'Daytona Beach, FL',
                   'Homestead, FL', 'Kansas City, KS', 'Ridgeway, VA', 'Brooklyn, MI']
RACE_NAMES = ['Rolex 24 At Daytona', 'Gainsco Grand Prix of Miami', 'Mexico City 250',
              'Bosch Engineering 250 at VIR', 'RumBum.com 250', 'Lime Rock GT Classic 250',
              "Sahlen's Six Hours of the Glen"]
RACE_DATES = ['January 26 January 27', 'March 29', 'April 19', 'April 27', 'May 17',
              'May 26', 'June 7']


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


def _parent_values(schema, instance: dict, table: str, key: str) -> list:
    """Parent key values: compact rows (full distinct set) + generated rows."""
    out = []
    for v in schema.key_values.get((table, key), []):
        if v is not None:
            out.append(v)
    for v in instance.get(table, {}).get(key, []) or []:
        if v is not None:
            out.append(v)
    return out


def _coerce_fk(child_type: str, parent_type: str, v):
    """Store str(value) when the child column is TEXT and the parent column is INT."""
    if v is None:
        return None
    ct = (child_type or '').lower()
    pt = (parent_type or '').lower()
    if 'char' in ct or 'text' in ct or ct == '':
        if 'int' in pt:
            return str(v)
    return v


def _fk_plan(n: int, parent: list, rng) -> list:
    """Explicit FK plan: NULL child, orphan parent, and child counts 0,1,2,>=3 with a rank-1 tie."""
    if not parent:
        return [None] * n
    if n < 6 or len(parent) < 4:
        out = []
        for _ in range(n):
            r = rng.random()
            if r < 0.15:
                out.append(None)
            elif r < 0.75:
                out.append(parent[rng.randrange(min(3, len(parent)))])
            else:
                out.append(parent[rng.randrange(len(parent))])
        return out
    pool = list(parent)
    rng.shuffle(pool)
    p0, p1, p2, p3 = pool[0], pool[1], pool[2], pool[3]
    counts = {p1: 1, p2: 2, p3: max(3, n - 4)}
    out = [None]
    for k, c in counts.items():
        out.extend([k] * c)
    while len(out) < n:
        out.append(rng.choice([p1, p2, p3]))
    out = out[:n]
    rng.shuffle(out)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with the FK plan."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(schema, instance, pt, pc)
        pcol = next((c for c in schema.tables[pt].columns if c.name == pc), None)
        ptype = pcol.type_str if pcol is not None else ''
        plan = _fk_plan(n, pv, rng)
        out[cm.name] = [_coerce_fk(cm.type_str, ptype, v) for v in plan]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes with a small per-instance jitter (0-230 rows, level x 4 capped at 2500)."""
    sizes = {}
    for t in schema.tables:
        base = SPEC_SIZES.get(t, 0)
        if base:
            sizes[t] = max(0, base + rng.randint(-1, 2))
        else:
            sizes[t] = rng.randint(0, 230)
    return sizes


def _plant_nulls(values: list, share: float, rng, protected: set) -> list:
    """NULL rule: plant NULLs to match max(1/n, compact share) per nullable column."""
    if not values:
        return values
    n = len(values)
    want = max(1, int(round(share * n)))
    want = min(want, n)
    candidates = [i for i in range(n) if i not in protected]
    if not candidates:
        candidates = list(range(n))
    rng.shuffle(candidates)
    for i in candidates[:want]:
        values[i] = None
    return values


def _class_enum(n: int, rng) -> list:
    """race.Class: enum with case variants; guarantees at least one 'GT' and one 'gt'."""
    out = []
    for i in range(n):
        r = rng.random()
        if r < 0.15:
            out.append('GT')
        elif r < 0.30:
            out.append('gt')
        elif r < 0.55:
            out.append('DP/GT')
        else:
            out.append(rng.choice(CLASS_VARIANTS))
    if n >= 2:
        out[0] = 'GT'
        out[1] = 'gt'
    elif n == 1:
        out[0] = 'GT'
    return out


def _variant(base: str, rng) -> str:
    r = rng.random()
    if r < 0.20:
        return base
    if r < 0.35:
        return base.lower()
    if r < 0.50:
        return base + ' '
    if r < 0.62:
        return base.replace(' ', '  ', 1)
    return base


def _track_name_variants(n: int, rng) -> list:
    return [_variant(rng.choice(TRACK_NAMES), rng) for _ in range(n)]


def _track_location_variants(n: int, rng) -> list:
    return [_variant(rng.choice(TRACK_LOCATIONS), rng) for _ in range(n)]


def _race_name_variants(n: int, rng) -> list:
    return [_variant(rng.choice(RACE_NAMES), rng) for _ in range(n)]


def _race_date_variants(n: int, rng) -> list:
    """Unordered month-day pool; the chronological-order rule does not apply to race.Date."""
    out = []
    for _ in range(n):
        base = rng.choice(RACE_DATES)
        out.append(base + ' ' if rng.random() < 0.15 else base)
    return out


def _seating_variants(n: int, rng) -> list:
    out = []
    for _ in range(n):
        r = rng.random()
        if r < 0.15:
            out.append(65000.0)
        elif r < 0.30:
            out.append(92000.0)
        elif r < 0.45:
            out.append(168000.0)
        else:
            out.append(float(rng.randint(50000, 200000)))
    return out


def _year_variants(n: int, rng) -> list:
    out = []
    for _ in range(n):
        r = rng.random()
        if r < 0.15:
            out.append(1959.0)
        elif r < 0.30:
            out.append(1997.0)
        elif r < 0.45:
            out.append(2001.0)
        else:
            out.append(float(rng.randint(1900, 2025)))
    return out


def _child_counts(inst: dict, schema) -> dict:
    """Per-parent child counts for the race.Track_ID -> track.Track_ID FK (generated rows only)."""
    if ('race', 'Track_ID') not in schema.fks:
        return {}
    pt, pc = schema.fks[('race', 'Track_ID')]
    parents = set()
    for v in schema.key_values.get((pt, pc), []):
        if v is not None:
            parents.add(str(v))
    for v in inst.get(pt, {}).get(pc, []) or []:
        if v is not None:
            parents.add(str(v))
    counts = {p: 0 for p in parents}
    for v in inst.get('race', {}).get('Track_ID', []) or []:
        if v is not None:
            counts[str(v)] = counts.get(str(v), 0) + 1
    return counts


def _verify_targets(inst: dict, schema) -> bool:
    """Post-construction target check; returns False if a required target is destroyed."""
    if ('race', 'Track_ID') in schema.fks:
        child_vals = inst.get('race', {}).get('Track_ID', []) or []
        if not any(v is None for v in child_vals):
            return False
        counts = _child_counts(inst, schema)
        if not any(c == 0 for c in counts.values()):
            return False
        vals = set(counts.values())
        if not ({0, 1, 2} <= vals and any(c >= 3 for c in vals)):
            return False
        mx = max(counts.values()) if counts else 0
        if mx < 1 or sum(1 for c in counts.values() if c == mx) < 2:
            return False
    classes = inst.get('race', {}).get('Class', []) or []
    if classes:
        present = {str(v) for v in classes if v is not None}
        if not ({'GT', 'gt'} <= present):
            return False
    for t, c in (('track', 'Name'), ('track', 'Location'), ('race', 'Class')):
        vals = [v for v in (inst.get(t, {}).get(c, []) or []) if v is not None]
        if len(vals) >= 2:
            share = 1.0 - len(set(vals)) / len(vals)
            if not (0.20 <= share <= 0.50):
                return False
    return True


def _build_once(schema, literal_pool: dict, size, rng) -> dict:
    """One construction attempt (fuzz.py:111-196) over the compact schema, append-only."""
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
        if t == 'track':
            if 'Name' in cols:
                cols['Name'] = _track_name_variants(n, rng)
            if 'Location' in cols:
                cols['Location'] = _track_location_variants(n, rng)
            if 'Seating' in cols:
                cols['Seating'] = _seating_variants(n, rng)
            if 'Year_Opened' in cols:
                cols['Year_Opened'] = _year_variants(n, rng)
        if t == 'race':
            if 'Class' in cols:
                cols['Class'] = _class_enum(n, rng)
            if 'Name' in cols:
                cols['Name'] = _race_name_variants(n, rng)
            if 'Date' in cols:
                cols['Date'] = _race_date_variants(n, rng)
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for pk in tm.primary_key:
            if pk in cols:
                base = schema.max_ints.get((t, pk), 0)
                cols[pk] = [base + 1 + i for i in range(n)]
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.nullable and cm.name in cols and not cm.pk_pos:
                protected: set = set()
                if t == 'race' and cm.name == 'Class':
                    protected = {0, 1}
                if t == 'race' and cm.name == 'Track_ID':
                    protected = {0}
                share = schema.null_shares.get((t, cm.name), 0.0)
                cols[cm.name] = _plant_nulls(cols[cm.name], share, rng, protected)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance; retry (bounded) if planting NULLs destroyed a target."""
    last = None
    for _ in range(16):
        inst = _build_once(schema, literal_pool, size, rng)
        last = inst
        if _verify_targets(inst, schema):
            return inst
    return last
