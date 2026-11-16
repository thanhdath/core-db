"""Random instance construction (fuzz/fuzz.py:83-196), adapted for Round 1."""
import datetime as dt

from .values import _init_sampler

_SPEC_SIZES = {
    'Problem_Category_Codes': 0,
    'Problem_Status_Codes': 0,
    'Staff': 15,
    'Product': 15,
    'Problems': 15,
    'Problem_Log': 15,
}

_CATEGORY_CODES = ['Datatabase', 'GUI', 'Middleware']
_STATUS_CODES = ['Reported', 'Solved']

_NULL_TARGETS = {
    'Problem_Log.log_entry_date', 'Problem_Log.log_entry_description', 'Problem_Log.log_entry_fix',
    'Problem_Log.other_log_details', 'Problems.date_problem_closed', 'Problems.problem_description',
    'Problems.other_problem_details', 'Product.product_name', 'Product.product_details',
    'Staff.staff_first_name', 'Staff.staff_last_name', 'Staff.other_staff_details',
    'Problem_Category_Codes.problem_category_description', 'Problem_Status_Codes.problem_status_description',
}

_SPEC_TARGET_LITERALS = {
    ('Product', 'product_name'): ['voluptatem', 'VOLUPTATEM', 'pta', 'PTA', 'up', 'UP', 'volup', 'VOLUP'],
    ('Staff', 'staff_last_name'): ['Berge', 'berge', 'Medhurst', 'medhurst', 'Bosco', 'bosco', 'Turcotte', 'turcotte'],
    ('Staff', 'staff_first_name'): ['Christop', 'christop', 'Ashley', 'ashley', 'Lysanne', 'lysanne'],
}


def _filter_rows(columns: dict, keep: list) -> dict:
    """Keep the given row indices across ALL columns of a table."""
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    for v in columns.values():
        return len(v)
    return 0


def _pk_tuple(tm, cols: dict, i: int) -> tuple:
    return tuple(cols[c][i] for c in tm.primary_key)


def sample_fresh_primary_keys(table_meta, columns: dict, compact_pk: set) -> dict:
    """Drop rows whose PK tuple repeats or collides with compact rows (fuzz.py:188-190 + Round 1)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
    seen = set(compact_pk or ())
    keep = []
    for i in range(n):
        k = _pk_tuple(table_meta, columns, i)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter_rows(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_unique: dict) -> dict:
    """Drop rows repeating any single unique column value or colliding with compact rows."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(compact_unique.get((table_meta.name, cm.name), ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter_rows(columns, keep)
    return columns


def _fresh_int_pk(table_meta, n: int, compact_pk: set, rng) -> list:
    """Sequential integers starting at 1, skipping compact PKs (single-column PK only)."""
    if len(table_meta.primary_key) != 1:
        return None
    used = {k[0] for k in (compact_pk or ()) if k and k[0] is not None}
    out = []
    cand = 1
    while len(out) < n:
        if cand not in used:
            out.append(cand)
            used.add(cand)
        cand += 1
    return out


def _apply_null_rule(table: str, tm, cols: dict, rng) -> dict:
    """Spec NULL rule: each nullable column gets at least one NULL row; NULL share ~5-10%."""
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        key = '%s.%s' % (table, cm.name)
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        if key not in _NULL_TARGETS:
            continue
        idx = rng.randrange(n)
        cols[cm.name][idx] = None
        share = rng.uniform(0.05, 0.10)
        for i in range(n):
            if i != idx and rng.random() < share:
                cols[cm.name][i] = None
    return cols


def _apply_enum_domains(table: str, cols: dict, rng) -> dict:
    """Spec enum domains for category/status codes."""
    if table == 'Problem_Category_Codes' and 'problem_category_code' in cols:
        cols['problem_category_code'] = [rng.choice(_CATEGORY_CODES) for _ in cols['problem_category_code']]
    if table == 'Problem_Status_Codes' and 'problem_status_code' in cols:
        cols['problem_status_code'] = [rng.choice(_STATUS_CODES) for _ in cols['problem_status_code']]
    if table == 'Problem_Log':
        if 'problem_category_code' in cols:
            cols['problem_category_code'] = [rng.choice(_CATEGORY_CODES) for _ in cols['problem_category_code']]
        if 'problem_status_code' in cols:
            cols['problem_status_code'] = [rng.choice(_STATUS_CODES) for _ in cols['problem_status_code']]
    return cols


def _parse_dt(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v
    s = str(v).strip()
    for t in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y%m%d'):
        try:
            return dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None


def _fmt_dt(d: dt.datetime) -> str:
    return d.strftime('%Y-%m-%d %H:%M:%S')


def _apply_date_rules(table: str, cols: dict, rng) -> dict:
    """Soft preference: date_problem_closed >= date_problem_reported (non-NULL operands)."""
    if table == 'Problems' and 'date_problem_reported' in cols and 'date_problem_closed' in cols:
        rep = cols['date_problem_reported']
        clo = cols['date_problem_closed']
        for i in range(len(rep)):
            r = _parse_dt(rep[i])
            c = _parse_dt(clo[i])
            if r is None or c is None:
                continue
            if c < r:
                clo[i] = _fmt_dt(r + dt.timedelta(seconds=rng.randint(0, 86400 * 365)))
    return cols


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_parent: dict) -> dict:
    """FK child columns draw from parent's generated+compact values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += list(compact_parent.get((pt, pc), []))
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes per instance; fall back to upstream rand_lin/level sizes for unknown tables."""
    sizes = {}
    for t in schema.tables:
        if t in _SPEC_SIZES:
            sizes[t] = _SPEC_SIZES[t]
        else:
            sizes[t] = int(30 * rng.random() + int(rng.random() * 200))
    return sizes


def _compact_parent_values(schema) -> dict:
    """(parent_table, parent_col) -> compact values for FK drawing."""
    out = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        out.setdefault((pt, pc), list(schema.original_values.get((pt, pc), [])))
    return out


def _inject_spec_literals(literal_pool: dict) -> dict:
    """Inject spec per_column_exceptions target literals into the pool (Round 1 revision)."""
    pool = {k: list(v) for k, v in literal_pool.items()}
    for (t, c), vals in _SPEC_TARGET_LITERALS.items():
        pool.setdefault((t, c), [])
        for v in vals:
            if v not in pool[(t, c)]:
                pool[(t, c)].append(v)
    return pool


def _assign_problem_product_ids(problems_cols: dict, product_ids: list, rng) -> None:
    """Assign Problems.product_id to satisfy ties_for_order_limit and group_sizes."""
    n = len(problems_cols.get('problem_id', []))
    if n == 0 or not product_ids:
        return
    plan = [1, 2, 3, 3, 3]
    remaining = n - sum(plan)
    extra = []
    i = 0
    while remaining > 0:
        extra.append(product_ids[i % len(product_ids)])
        i += 1
        remaining -= 1
    assigned = []
    pid_iter = iter(product_ids)
    for cnt in plan:
        try:
            p = next(pid_iter)
        except StopIteration:
            break
        assigned.extend([p] * cnt)
    assigned.extend(extra)
    while len(assigned) < n:
        assigned.append(rng.choice(product_ids))
    assigned = assigned[:n]
    rng.shuffle(assigned)
    problems_cols['product_id'] = assigned


def _assign_log_problem_ids(log_cols: dict, problem_ids: list, rng) -> None:
    """Assign Problem_Log.problem_id so at least one problem has >= 2 log rows with different log_entry_date values
    (rows_with_different_values)."""
    n = len(log_cols.get('problem_log_id', []))
    if n == 0 or not problem_ids:
        return
    dup_pid = rng.choice(problem_ids)
    assigned = [dup_pid, dup_pid]
    while len(assigned) < n:
        assigned.append(rng.choice(problem_ids))
    assigned = assigned[:n]
    rng.shuffle(assigned)
    log_cols['problem_id'] = assigned
    led = log_cols.get('log_entry_date')
    if led is not None:
        idxs = [i for i, p in enumerate(assigned) if p == dup_pid]
        if len(idxs) >= 2:
            base = _parse_dt(led[idxs[0]]) or dt.datetime(2000, 1, 1)
            led[idxs[1]] = _fmt_dt(base + dt.timedelta(seconds=rng.randint(1, 86400 * 30)))


def _reserve_unmatched_staff(problems_cols: dict, staff_ids: list, rng) -> None:
    """Ensure at least one Staff row has no referencing Problems row (unmatched_join_rows)."""
    if not staff_ids or 'reported_by_staff_id' not in problems_cols:
        return
    reserved = rng.choice(staff_ids)
    pool = [s for s in staff_ids if s != reserved]
    if not pool:
        return
    n = len(problems_cols['reported_by_staff_id'])
    problems_cols['reported_by_staff_id'] = [rng.choice(pool) for _ in range(n)]


def _harmonize_self_fks(table: str, tm, cols: dict, schema, rng) -> dict:
    """For FK columns whose parent is the same table (or an already-finalized table), clamp generated values to the
    table's final key set; NULL when no valid value exists."""
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        if pt != table:
            continue
        if pc not in cols or cm.name not in cols:
            continue
        final = [v for v in cols[pc] if v is not None]
        fs = set(final)
        if not fs:
            cols[cm.name] = [None] * len(cols[cm.name])
            continue
        cols[cm.name] = [v if (v is None or v in fs) else rng.choice(final) for v in cols[cm.name]]
    return cols


def _parent_pool(instance: dict, schema, compact_parent: dict, table: str, col: str) -> list:
    """All usable (non-NULL) parent key values for an FK, generated + compact."""
    pv = list(instance.get(table, {}).get(col) or [])
    pv += list(compact_parent.get((table, col), []))
    return [v for v in pv if v is not None]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196), Round 1 adapted."""
    literal_pool = _inject_spec_literals(literal_pool)
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
    compact_parent = _compact_parent_values(schema)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if tm.primary_key and len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            fresh = _fresh_int_pk(tm, n, schema.compact_pk.get(t, set()), rng)
            if fresh is not None:
                cols[tm.primary_key[0]] = fresh
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = _parent_pool(inst, schema, compact_parent, pt, pc)
            cols[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
        cols = _apply_enum_domains(t, cols, rng)
        cols = _apply_null_rule(t, tm, cols, rng)
        cols = _apply_date_rules(t, cols, rng)
        if t == 'Problems' and 'product_id' in cols:
            pids = _parent_pool(inst, schema, compact_parent, 'Product', 'product_id')
            if pids:
                _assign_problem_product_ids(cols, pids, rng)
        if t == 'Problems' and 'reported_by_staff_id' in cols:
            sids = _parent_pool(inst, schema, compact_parent, 'Staff', 'staff_id')
            if sids:
                _reserve_unmatched_staff(cols, sids, rng)
        if t == 'Problem_Log' and 'problem_id' in cols:
            pids = _parent_pool(inst, schema, compact_parent, 'Problems', 'problem_id')
            if pids:
                _assign_log_problem_ids(cols, pids, rng)
        cols = sample_fresh_primary_keys(tm, cols, schema.compact_pk.get(t, set()))
        cols = drop_unique_duplicates(tm, cols, schema.compact_unique)
        cols = _harmonize_self_fks(t, tm, cols, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
