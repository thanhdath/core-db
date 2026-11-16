"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from . import spec
from .values import (DateWindowSampler, DuplicateShareSampler, EnumSampler,
                     GroupSizeSampler)


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


def _compact_keys(schema, table: str) -> set:
    """PK tuples already present in the compact database."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    idx = [c.name for c in tm.columns]
    pos = [idx.index(c) for c in tm.primary_key]
    return {tuple(r[p] for p in pos) for r in schema.compact_rows.get(table, [])}


def _fresh_int_keys(schema, table: str, n: int, rng) -> list:
    """Sequential fresh integer PKs starting after the compact max (never reused)."""
    tm = schema.tables[table]
    pk = tm.primary_key[0] if tm.primary_key else tm.columns[0].name
    idx = [c.name for c in tm.columns].index(pk)
    used = {r[idx] for r in schema.compact_rows.get(table, []) if r[idx] is not None}
    start = (max(used) + 1) if used else 1
    out, v = [], start
    while len(out) < n:
        if v not in used:
            out.append(v)
        v += 1
    return out


def _parent_values(schema, inst, table: str, col: str) -> list:
    """All values of a parent column: compact rows first, then generated rows."""
    tm = schema.tables[table]
    idx = [c.name for c in tm.columns].index(col)
    vals = [r[idx] for r in schema.compact_rows.get(table, []) if r[idx] is not None]
    vals += [v for v in inst.get(table, {}).get(col, []) if v is not None]
    return vals


def _fk_values(schema, inst, table: str, col: str, n: int, rng, omit: set = None) -> list:
    """FK child column draws from the parent's values (compact + generated)."""
    pt, pc = schema.fks[(table, col)]
    pv = _parent_values(schema, inst, pt, pc)
    if omit:
        pv = [v for v in pv if v not in omit]
    if not pv:
        return [None] * n
    return [rng.choice(pv) for _ in range(n)]


def _apply_null_rule(table: str, col: str, values: list, compact_share: float, rng) -> list:
    """Plant NULLs: share in [NULL_SHARE_MIN, NULL_SHARE_MAX], at least one NULL row."""
    n = len(values)
    if n == 0:
        return values
    share = min(max(compact_share, spec.NULL_SHARE_MIN), spec.NULL_SHARE_MAX)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = list(range(n))
    rng.shuffle(idx)
    out = list(values)
    for i in idx[:k]:
        out[i] = None
    return out


def _compact_null_share(schema, table: str, col: str) -> float:
    tm = schema.tables[table]
    idx = [c.name for c in tm.columns].index(col)
    rows = schema.compact_rows.get(table, [])
    if not rows:
        return spec.NULL_SHARE_MIN
    nulls = sum(1 for r in rows if r[idx] is None)
    return nulls / len(rows)


def _enum_or_pool(table: str, col: str, schema, literal_pool: dict) -> list:
    key = (table, col)
    if key in spec.ENUMS:
        return list(spec.ENUMS[key])
    pool = [str(v) for v in literal_pool.get(key, [])]
    ov = [str(v) for v in schema.original_values.get(key, []) if v is not None]
    return pool + ov


def _text_pool(table: str, col: str, schema, literal_pool: dict, fallback: list) -> list:
    key = (table, col)
    pool = [str(v) for v in literal_pool.get(key, [])]
    ov = [str(v) for v in schema.original_values.get(key, []) if v is not None]
    out = pool + ov + list(fallback)
    return out or ['x']


def _sample_text(table: str, col: str, n: int, schema, literal_pool: dict, fallback: list, rng) -> list:
    pool = _text_pool(table, col, schema, literal_pool, fallback)
    return [rng.choice(pool) for _ in range(n)]


def _sample_date_window(n: int, rng) -> list:
    s = DateWindowSampler(rng)
    return [s.sample() for _ in range(n)]


def _parse_dt(s):
    if s is None:
        return None
    if isinstance(s, dt.datetime):
        return s
    try:
        return dt.datetime.strptime(str(s), spec.DATE_FMT)
    except ValueError:
        return None


def _enforce_ge(values_a: list, values_b: list) -> list:
    """Return values_a with each non-NULL value >= the paired values_b value."""
    out = []
    for a, b in zip(values_a, values_b):
        da, db = _parse_dt(a), _parse_dt(b)
        if da is None or db is None:
            out.append(a)
            continue
        if da < db:
            out.append(db.strftime(spec.DATE_FMT))
        else:
            out.append(a)
    return out


def _enforce_nonnegative(values: list) -> list:
    out = []
    for v in values:
        if v is None:
            out.append(v)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(v)
            continue
        out.append(str(max(0, int(round(f)))))
    return out


def _group_size_column(table: str, col: str, n: int, schema, literal_pool: dict, rng) -> list:
    """Values whose value-groups have sizes 1, 2 and >= 3."""
    pool = _enum_or_pool(table, col, schema, literal_pool)
    if not pool:
        pool = ['g%d' % i for i in range(4)]
    s = GroupSizeSampler(pool, rng)
    return s.draw(n)


def _duplicate_column(table: str, col: str, n: int, schema, literal_pool: dict, fallback: list, rng) -> list:
    pool = _text_pool(table, col, schema, literal_pool, fallback)
    share = rng.uniform(spec.DUP_SHARE_MIN, spec.DUP_SHARE_MAX)
    s = DuplicateShareSampler(pool, share, rng)
    return [s.sample() for _ in range(n)]


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes per instance (TABLE_SIZES); fall back to the fuzz rule for unknown tables."""
    sizes = {}
    for t in schema.tables:
        if t in spec.TABLE_SIZES:
            sizes[t] = spec.TABLE_SIZES[t]
        else:
            sizes[t] = int(30 * rng.random() + int(rng.random() * 200))
    return sizes


def _build_table(schema, inst, table: str, n: int, literal_pool: dict, rng) -> dict:
    """Generate n new rows for one table (all columns), by construction."""
    tm = schema.tables[table]
    cols: dict = {}
    fk_cols = {c.name for c in tm.columns if (table, c.name) in schema.fks}
    pk_cols = set(tm.primary_key)

    if tm.primary_key and len(tm.primary_key) == 1:
        pk = tm.primary_key[0]
        cols[pk] = _fresh_int_keys(schema, table, n, rng)

    for c in tm.columns:
        if c.name in fk_cols:
            cols[c.name] = _fk_values(schema, inst, table, c.name, n, rng)

    for c in tm.columns:
        if c.name in cols:
            continue
        key = (table, c.name)
        if key in spec.ENUMS:
            cols[c.name] = [rng.choice(spec.ENUMS[key]) for _ in range(n)]
        elif key in spec.DUPLICATE_COLUMNS:
            fallback = _fallback_pool(table, c.name)
            cols[c.name] = _duplicate_column(table, c.name, n, schema, literal_pool, fallback, rng)
        elif key in spec.GROUP_SIZE_COLUMNS:
            cols[c.name] = _group_size_column(table, c.name, n, schema, literal_pool, rng)
        elif 'date' in (c.type_str or '').lower() or 'timestamp' in (c.type_str or '').lower():
            cols[c.name] = _sample_date_window(n, rng)
        elif 'int' in (c.type_str or '').lower():
            cols[c.name] = [rng.randint(1, 1000) for _ in range(n)]
        else:
            fallback = _fallback_pool(table, c.name)
            cols[c.name] = _sample_text(table, c.name, n, schema, literal_pool, fallback, rng)

    for (t, col, ot, ocol) in spec.FORMULAS:
        if t == table and col in cols and ocol in cols:
            cols[col] = _enforce_ge(cols[col], cols[ocol])
    for (t, col) in spec.NONNEGATIVE:
        if t == table and col in cols:
            cols[col] = _enforce_nonnegative(cols[col])

    for c in tm.columns:
        if c.name in pk_cols:
            continue
        if c.notnull:
            continue
        key = (table, c.name)
        if key in spec.NULL_TARGETS or c.name in fk_cols:
            share = _compact_null_share(schema, table, c.name)
            cols[c.name] = _apply_null_rule(table, c.name, cols[c.name], share, rng)

    cols = sample_fresh_primary_keys(tm, cols)
    cols = drop_unique_duplicates(tm, cols)
    return cols


def _fallback_pool(table: str, col: str) -> list:
    """Small vocabulary per column (spec free-text pools)."""
    if table == 'Third_Party_Companies':
        return {'company_name': spec.COMPANY_NAMES, 'company_address': spec.COMPANY_ADDRESSES,
                'other_company_details': spec.COUNTRIES}.get(col, ['x'])
    if table == 'Maintenance_Engineers':
        return {'first_name': spec.FIRST_NAMES, 'last_name': spec.LAST_NAMES,
                'other_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Staff':
        return {'staff_name': spec.STAFF_NAMES, 'other_staff_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Parts':
        return {'part_name': spec.PART_NAMES, 'other_part_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Assets':
        return {'asset_details': spec.ASSET_DETAILS, 'asset_make': spec.ASSET_MAKES,
                'asset_model': spec.ASSET_MODELS, 'other_asset_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Fault_Log':
        return {'fault_description': spec.FAULT_DESCRIPTIONS, 'other_fault_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Part_Faults':
        return {'fault_short_name': spec.FAULT_SHORT, 'fault_description': spec.FAULT_LONG,
                'other_fault_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Maintenance_Contracts':
        return {'other_contract_details': spec.OTHER_DETAILS}.get(col, ['x'])
    if table == 'Engineer_Visits':
        return {'other_visit_details': spec.OTHER_DETAILS}.get(col, ['x'])
    return ['x']


def _surviving_parent_values(schema, inst, table: str, col: str) -> list:
    """Parent values that actually survive insertion (compact + generated rows)."""
    return _parent_values(schema, inst, table, col)


def _apply_unmatched(schema, inst, rng) -> None:
    """Ensure parent rows without children (unmatched_join_rows)."""
    for (ct, cc, pt, pc) in spec.UNMATCHED:
        if ct not in inst or pt not in inst:
            continue
        child_col = inst[ct].get(cc)
        if not child_col:
            continue
        parent_vals = _surviving_parent_values(schema, inst, pt, pc)
        if not parent_vals:
            continue
        child_vals = set(v for v in child_col if v is not None)
        if any(v not in child_vals for v in parent_vals):
            continue
        tm = schema.tables[ct]
        cm = next((c for c in tm.columns if c.name == cc), None)
        if cm is not None and not cm.notnull:
            for i, v in enumerate(child_col):
                if v is not None:
                    child_col[i] = None
                    break
        else:
            omit = {parent_vals[0]}
            n = len(child_col)
            new_vals = _fk_values(schema, inst, ct, cc, n, rng, omit=omit)
            if all(v in omit for v in new_vals if v is not None):
                keep = [v for v in parent_vals if v not in omit]
                if keep:
                    new_vals[0] = keep[0]
            inst[ct][cc] = new_vals


def _apply_tie_fault_log_parts(schema, inst, rng) -> None:
    """Fault_Log.fault_log_entry_id: rank 1 DESC on COUNT(fault_log_parts.part_fault_id) is tied."""
    if not spec.TIE_FAULT_LOG_PARTS:
        return
    fl = inst.get('Fault_Log', {}).get('fault_log_entry_id', [])
    flp = inst.get('Fault_Log_Parts', {}).get('fault_log_entry_id', [])
    if len(fl) < 2 or not flp:
        return
    counts: dict = {}
    for v in flp:
        counts[v] = counts.get(v, 0) + 1
    for v in fl:
        counts.setdefault(v, 0)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top_two = [v for v, _ in ranked[:2]]
    if len(top_two) < 2:
        return
    target = max(counts.values())
    for v in top_two:
        have = counts.get(v, 0)
        need = target - have
        if need > 0:
            for _ in range(need):
                flp.append(v)
        elif need < 0:
            removed = 0
            for i in range(len(flp) - 1, -1, -1):
                if flp[i] == v and removed < -need:
                    del flp[i]
                    removed += 1
    inst['Fault_Log_Parts']['fault_log_entry_id'] = flp


def _apply_aggregate_boundary(schema, inst, rng) -> None:
    """Aggregate-boundary patterns on non-key columns."""
    for (t, col), (op, val) in spec.AGGREGATE_BOUNDARY.items():
        if t not in inst or col not in inst[t]:
            continue
        vals = inst[t][col]
        if not vals:
            continue
        counts: dict = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        if op == 'lt' and val == 2:
            if not any(c == 1 for c in counts.values()):
                vals[-1] = '__uniq_%d' % rng.randint(0, 10 ** 9)
        elif op == 'gt' and val == 2:
            if not any(c > 2 for c in counts.values()) and len(vals) >= 3:
                v = vals[0]
                vals[1] = v
                vals[2] = v
    pf = inst.get('Part_Faults', {}).get('part_id')
    parts = inst.get('Parts', {}).get('part_id')
    if pf and parts:
        counts: dict = {}
        for v in pf:
            counts[v] = counts.get(v, 0) + 1
        if not any(c >= spec.PARTS_FAULT_GROUP_MIN for c in counts.values()):
            target = parts[0]
            have = counts.get(target, 0)
            need = spec.PARTS_FAULT_GROUP_MIN - have
            for _ in range(max(0, need)):
                pf.append(target)
            inst['Part_Faults']['part_id'] = pf


def _apply_acquired_date_distinct(schema, inst, rng) -> None:
    """Assets.asset_acquired_date: >= 2 rows per group with different values."""
    if not spec.ACQUIRED_DATE_DISTINCT:
        return
    if 'Assets' not in inst or 'asset_acquired_date' not in inst['Assets']:
        return
    vals = inst['Assets']['asset_acquired_date']
    groups = inst['Assets'].get('maintenance_contract_id')
    if not groups or len(groups) != len(vals):
        if len(vals) >= 2 and vals[0] == vals[1]:
            s = DateWindowSampler(rng)
            vals[1] = s.sample()
        return
    by_group: dict = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    s = DateWindowSampler(rng)
    for g, idxs in by_group.items():
        if len(idxs) < 2:
            continue
        distinct = {vals[i] for i in idxs if vals[i] is not None}
        if len(distinct) >= 2:
            continue
        first = vals[idxs[0]]
        new = s.sample()
        if new == first:
            new = s.sample()
        vals[idxs[1]] = new


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        n = int(size.get(t, 0))
        inst[t] = _build_table(schema, inst, t, n, literal_pool, rng)
    _apply_unmatched(schema, inst, rng)
    _apply_tie_fault_log_parts(schema, inst, rng)
    _apply_aggregate_boundary(schema, inst, rng)
    _apply_acquired_date_distinct(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}
