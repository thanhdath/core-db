"""Random instance construction (fuzz/fuzz.py:83-196) plus specification-driven rules."""
import datetime as dt

from . import specification as spec
from .values import _init_sampler, make_spec_sampler


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


def drop_composite_unique_duplicates(schema, table: str, columns: dict) -> dict:
    """Drop rows repeating any composite UNIQUE tuple."""
    for (t, cols) in schema.unique_constraints:
        if t != table or not all(c in columns for c in cols):
            continue
        n = len(next(iter(columns.values())))
        seen, keep = set(), []
        for i in range(n):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, table: str, col: str) -> list:
    """Parent values = compact original values + generated values (never NULL)."""
    pt, pc = schema.fks[(table, col)]
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pv = _parent_pool(instance, schema, table, cm.name)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes per instance (table_sizes_per_instance)."""
    sizes = {}
    for t in schema.tables:
        sizes[t] = int(spec.TABLE_SIZES.get(t, 0))
    return sizes


def _apply_null_rule(table: str, columns: dict, schema, rng) -> dict:
    """Plant NULLs on nullable columns: at least one NULL row, share from compact data."""
    tm = schema.tables[table]
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in tm.columns:
        if cm.name not in columns or cm.notnull or cm.pk_pos > 0:
            continue
        col = columns[cm.name]
        orig = schema.original_values.get((table, cm.name), [])
        if orig:
            share = sum(1 for v in orig if v is None) / max(1, len(orig))
        else:
            share = 0.05
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            col[i] = None
    return columns


def _apply_booking_date_rule(columns: dict, rng) -> dict:
    """booking_end_date >= booking_start_date (only non-NULL operands constrained)."""
    if 'booking_start_date' not in columns or 'booking_end_date' not in columns:
        return columns
    starts, ends = columns['booking_start_date'], columns['booking_end_date']
    for i in range(len(starts)):
        s, e = starts[i], ends[i]
        if s is None or e is None:
            continue
        try:
            ds = dt.datetime.strptime(str(s), '%Y-%m-%d %H:%M:%S')
            de = dt.datetime.strptime(str(e), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        if de < ds:
            ends[i] = s
    return columns


def _apply_room_count_rule(columns: dict) -> dict:
    """room_count is CHAR(5) numeric string in [3, 9]."""
    if 'room_count' not in columns:
        return columns
    lo, hi = spec.ROOM_COUNT_RANGE
    out = []
    for v in columns['room_count']:
        if v is None:
            out.append(None)
            continue
        try:
            iv = int(str(v).strip())
        except ValueError:
            iv = lo
        out.append(str(max(lo, min(hi, iv))))
    columns['room_count'] = out
    return columns


def _apply_bedroom_different_values(columns: dict, rng) -> dict:
    """Ensure >= 2 rows per group with different bedroom_count values (by apt_type_code)."""
    if 'bedroom_count' not in columns or 'apt_type_code' not in columns:
        return columns
    groups: dict = {}
    for i, t in enumerate(columns['apt_type_code']):
        groups.setdefault(t, []).append(i)
    lo, hi = spec.NUMERIC_RANGES.get(('Apartments', 'bedroom_count'), (3, 6))
    for t, idxs in groups.items():
        if len(idxs) < 2:
            continue
        vals = {columns['bedroom_count'][i] for i in idxs if columns['bedroom_count'][i] is not None}
        if len(vals) < 2:
            for j, i in enumerate(idxs):
                columns['bedroom_count'][i] = lo + (j % (hi - lo + 1))
    return columns


def _apply_aggregate_boundary(columns: dict, rng) -> dict:
    """apt_type_code groups with COUNT(*) in {0,1,2}: ensure at least one group has 2 rows."""
    if 'apt_type_code' not in columns:
        return columns
    n = len(columns['apt_type_code'])
    if n < 2:
        return columns
    counts: dict = {}
    for v in columns['apt_type_code']:
        counts[v] = counts.get(v, 0) + 1
    if not any(c == 2 for c in counts.values()):
        columns['apt_type_code'][1] = columns['apt_type_code'][0]
    return columns


def _apply_tie_order(columns: dict, rng) -> dict:
    """Ensure at least 3 rows share the tie value for apt_type_code (ties at rank 1..3)."""
    if 'apt_type_code' not in columns:
        return columns
    n = len(columns['apt_type_code'])
    if n < 3:
        return columns
    v = columns['apt_type_code'][0]
    for i in range(1, 3):
        columns['apt_type_code'][i] = v
    return columns


def _apply_duplicate_share(columns: dict, table: str, rng) -> dict:
    """For DISTINCT-style columns, force a 20-50 % duplicate share (skip NULL cells)."""
    targets = {
        ('Apartment_Buildings', 'building_address'),
        ('Apartments', 'apt_type_code'),
        ('Apartments', 'apt_number'),
        ('Guests', 'guest_first_name'),
        ('Guests', 'guest_last_name'),
        ('Guests', 'date_of_birth'),
        ('Apartment_Bookings', 'booking_start_date'),
        ('Apartment_Bookings', 'booking_end_date'),
    }
    for (t, c) in targets:
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n < 2:
            continue
        src = next((i for i, v in enumerate(col) if v is not None), None)
        if src is None:
            continue
        k = max(1, int(round(spec.DUPLICATE_SHARE * n)))
        k = min(k, n - 1)
        for i in range(1, k + 1):
            if col[i] is not None:
                col[i] = col[src]
    return columns


def _apply_apt_number_tie(columns: dict, rng) -> dict:
    """apt_number ORDER ASC: ensure at least 3 rows share a value (skip NULL cells)."""
    if 'apt_number' not in columns:
        return columns
    n = len(columns['apt_number'])
    if n < 3:
        return columns
    v = columns['apt_number'][0]
    for i in range(1, 3):
        if columns['apt_number'][i] is not None:
            columns['apt_number'][i] = v
    return columns


def _apply_gender_tie(columns: dict, rng) -> dict:
    """gender_code ORDER COUNT(*) DESC: ensure at least 3 rows share a value (skip NULL cells)."""
    if 'gender_code' not in columns:
        return columns
    n = len(columns['gender_code'])
    if n < 3:
        return columns
    v = columns['gender_code'][0]
    for i in range(1, 3):
        if columns['gender_code'][i] is not None:
            columns['gender_code'][i] = v
    return columns


def _apply_room_count_tie(columns: dict, rng) -> dict:
    """room_count ORDER ASC: ensure at least 3 rows share a value (skip NULL cells)."""
    if 'room_count' not in columns:
        return columns
    n = len(columns['room_count'])
    if n < 3:
        return columns
    v = columns['room_count'][0]
    for i in range(1, 3):
        if columns['room_count'][i] is not None:
            columns['room_count'][i] = v
    return columns


def _apply_unmatched_join(instance: dict, schema, table: str, rng) -> dict:
    """Ensure parent rows without children and child rows with NULL FK exist."""
    tm = schema.tables[table]
    cols = instance.get(table, {})
    if not cols:
        return instance
    n = len(next(iter(cols.values())))
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.notnull:
            continue
        if cm.name not in cols:
            continue
        if n >= 1:
            cols[cm.name][rng.randrange(n)] = None
    return instance


def _reserve_unreferenced_parents(instance: dict, schema, rng) -> dict:
    """For each parent table, ensure at least one generated PK is not referenced by any generated child row
    (parent_rows_without_children)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct == pt:
            continue
        parent_cols = instance.get(pt, {})
        child_cols = instance.get(ct, {})
        if not parent_cols or not child_cols or pc not in parent_cols or cc not in child_cols:
            continue
        parent_vals = [v for v in parent_cols[pc] if v is not None]
        if not parent_vals:
            continue
        child_vals = child_cols[cc]
        referenced = {v for v in child_vals if v is not None}
        unreferenced = [v for v in parent_vals if v not in referenced]
        if unreferenced:
            continue
        compact_vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        if not compact_vals:
            continue
        for i, v in enumerate(child_vals):
            if v is not None:
                child_vals[i] = rng.choice(compact_vals)
                break
    return instance


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification rules by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                spec_s = make_spec_sampler(t, cm.name, cm, rng, literal_pool.get((t, cm.name), []))
                if spec_s is not None:
                    samplers[(t, cm.name)] = spec_s
                else:
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
        cols = drop_composite_unique_duplicates(schema, t, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    for t in order:
        cols = inst.get(t, {})
        if not cols:
            continue
        if t == 'Apartments':
            cols = _apply_bedroom_different_values(cols, rng)
            cols = _apply_aggregate_boundary(cols, rng)
            cols = _apply_tie_order(cols, rng)
            cols = _apply_apt_number_tie(cols, rng)
            cols = _apply_room_count_tie(cols, rng)
        if t == 'Guests':
            cols = _apply_gender_tie(cols, rng)
        cols = _apply_duplicate_share(cols, t, rng)
        inst[t] = cols
    for t in order:
        cols = inst.get(t, {})
        if not cols:
            continue
        if t == 'Apartment_Bookings':
            cols = _apply_booking_date_rule(cols, rng)
        if t == 'Apartments':
            cols = _apply_room_count_rule(cols)
        inst[t] = cols
    for t in order:
        cols = inst.get(t, {})
        if not cols:
            continue
        cols = _apply_null_rule(t, cols, schema, rng)
        inst[t] = cols
    for t in order:
        inst = _apply_unmatched_join(inst, schema, t, rng)
    inst = _reserve_unreferenced_parents(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
