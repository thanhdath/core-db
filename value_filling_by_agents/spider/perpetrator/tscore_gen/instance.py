"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import re

from .values import _init_sampler


_ONE_SIDED_HI = {'killed': 200, 'injured': 200, 'year': 2025}


def _spec_domain(spec: dict, table: str, column: str) -> dict:
    """Build a sampler domain dict for (table, column) from the specification."""
    dom: dict = {}
    for rule in spec.get('semantic_rules_and_formulas', []):
        if rule.get('table') != table or rule.get('column') != column:
            continue
        f = rule.get('formula', '')
        m = re.search(r'BETWEEN\s+(-?[\d.]+)\s+AND\s+(-?[\d.]+)', f, re.I)
        if m:
            dom['lo'], dom['hi'] = float(m.group(1)), float(m.group(2))
        m = re.search(r'>=\s*(-?[\d.]+)', f)
        if m and 'lo' not in dom:
            dom['lo'] = float(m.group(1))
        m = re.search(r'<=\s*(-?[\d.]+)', f)
        if m and 'hi' not in dom:
            dom['hi'] = float(m.group(1))
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m:
            vals = [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]
            if vals:
                dom['enum'] = vals
                dom['pool_only'] = True
    if 'lo' in dom and 'hi' not in dom:
        dom['hi'] = float(_ONE_SIDED_HI.get(column.lower(), dom['lo'] + 1000))
    if 'hi' in dom and 'lo' not in dom:
        dom['lo'] = 0.0
    for exc in spec.get('per_column_exceptions', []):
        if exc.get('column') != '%s.%s' % (table, column):
            continue
        pat = exc.get('pattern')
        if pat == 'comparison_boundary':
            dom['boundary'] = list(exc.get('targets', {}).get('values', []))
        if pat == 'ties_for_order_limit':
            dom['tie_rank'] = exc.get('targets', {}).get('tie_at_rank')
        if pat == 'rows_with_different_values':
            dom.setdefault('pool_size', 3)
            dom['need_distinct'] = True
    return dom


def _table_size(spec: dict, table: str, rng) -> int:
    """Specified size with per-instance variation (0-230 rows, or level x4 up to 2500)."""
    base = int(spec.get('table_sizes_per_instance', {}).get(table, 0))
    if base <= 0:
        return 0
    if rng.random() < 0.5:
        return max(1, int(base * rng.uniform(0.6, 1.4)))
    return max(1, min(2500, base * rng.choice([1, 1, 2, 4])))


def _null_share(spec: dict, table: str, column: str, rng) -> float:
    """NULL share for a nullable column: 5-30 % (specification), 0 for NOT NULL columns."""
    for exc in spec.get('per_column_exceptions', []):
        if exc.get('column') == '%s.%s' % (table, column) and exc.get('pattern') == 'null_rows':
            tgt = exc.get('targets', {}).get('null_share', '')
            if 'none' in str(tgt):
                return 0.0
    return rng.uniform(0.05, 0.30)


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    """Row count of a column dict; 0 when empty (guards every empty-list index)."""
    if not columns:
        return 0
    first = next(iter(columns.values()))
    return len(first)


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, unique_tuples=()) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195) or a composite UNIQUE tuple."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    for cols in unique_tuples:
        if not all(c in columns for c in cols):
            continue
        n = _nrows(columns)
        seen, keep = set(), []
        for i in range(n):
            k = tuple(columns[c][i] for c in cols)
            if k not in seen:
                seen.add(k)
                keep.append(i)
        columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(schema.original_values.get((pt, pc), []))
        pv += list(instance.get(pt, {}).get(pc) or [])
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specified sizes when available, else uniform rand_lin / level sizes x4 (fuzz.py:83-110)."""
    if spec and spec.get('table_sizes_per_instance'):
        return {t: _table_size(spec, t, rng) for t in schema.tables}
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


def _fresh_pk_values(schema, table: str, column: str, n: int, rng) -> list:
    """Sequential integers starting after the compact maximum; unique per table."""
    used = {v for v in schema.original_values.get((table, column), []) if isinstance(v, int)}
    start = (max(used) + 1) if used else 1
    return list(range(start, start + n))


def _boundary_values(dom: dict, n: int, rng) -> list:
    """Values around a comparison boundary (c-1, c, c+1 for each c)."""
    b = dom.get('boundary') or []
    pool = sorted({int(x) for x in b})
    if not pool:
        return [rng.randint(0, 100) for _ in range(n)]
    return [rng.choice(pool) for _ in range(n)]


def _apply_tie_rank(values: list, rank, rng) -> list:
    """Force a tie at the given DESC rank (rank 1 -> the maximum value appears >= 2 times)."""
    if not values:
        return values
    if rank in (1, [1], '1', [1.0]):
        mx = max(values)
        idx = [i for i, v in enumerate(values) if v == mx]
        if len(idx) < 2:
            j = rng.randrange(len(values))
            values[j] = mx
    return values


def _build_columns(schema, spec, table: str, n: int, rng, literal_pool: dict) -> dict:
    """Sample every non-FK column of `table` by construction."""
    tm = schema.tables[table]
    cols: dict = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key in schema.fks:
            continue
        dom = _spec_domain(spec, table, cm.name)
        if cm.pk_pos > 0 and len(tm.primary_key) == 1:
            cols[cm.name] = _fresh_pk_values(schema, table, cm.name, n, rng)
            continue
        if 'enum' in dom:
            pool = dom['enum']
            cols[cm.name] = [rng.choice(pool) for _ in range(n)]
            continue
        if 'boundary' in dom:
            cols[cm.name] = _boundary_values(dom, n, rng)
            continue
        if 'date' in (cm.type_str or '').lower() or 'timestamp' in (cm.type_str or '').lower():
            dom.setdefault('style', 'MM.DD Month DD')
        sampler = _init_sampler(cm, literal_pool.get(key, []), schema.original_values.get(key, []),
                                0.2, rng, len(tm.primary_key), domain=dom)
        vals = [sampler.sample() for _ in range(n)]
        if 'tie_rank' in dom:
            vals = _apply_tie_rank(vals, dom['tie_rank'], rng)
        cols[cm.name] = vals
    return cols


def _plant_nulls(schema, spec, table: str, cols: dict, rng) -> dict:
    """NULL rule: for every nullable column, 5-30 % NULL rows and at least one NULL row."""
    tm = schema.tables[table]
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.pk_pos > 0 or cm.notnull:
            continue
        share = _null_share(spec, table, cm.name, rng)
        if share <= 0:
            continue
        k = max(1, int(round(share * n)))
        k = min(k, n)
        idx = rng.sample(range(n), k)
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _enforce_null_mix(schema, spec, table: str, cols: dict, rng) -> dict:
    """Per-instance NULL rule: each nullable column has >=1 NULL and >=1 non-NULL row."""
    tm = schema.tables[table]
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        vals = cols[cm.name]
        has_null = any(v is None for v in vals)
        has_val = any(v is not None for v in vals)
        if has_null and has_val:
            continue
        if not has_null:
            vals[rng.randrange(n)] = None
        if not has_val:
            dom = _spec_domain(spec, table, cm.name)
            if 'enum' in dom:
                v = rng.choice(dom['enum'])
            elif 'lo' in dom and 'hi' in dom:
                v = round(rng.uniform(dom['lo'], dom['hi']), 1)
            else:
                ov = [x for x in schema.original_values.get((table, cm.name), []) if x is not None]
                v = rng.choice(ov) if ov else 'x'
            idx = [i for i, x in enumerate(vals) if x is None]
            if idx:
                vals[rng.choice(idx)] = v
    return cols


def _enforce_distinct(schema, spec, table: str, cols: dict, rng) -> dict:
    """Per-instance rows_with_different_values: >= 2 distinct non-NULL values per column."""
    tm = schema.tables[table]
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        dom = _spec_domain(spec, table, cm.name)
        if not dom.get('need_distinct'):
            continue
        vals = cols[cm.name]
        distinct = {v for v in vals if v is not None}
        if len(distinct) >= 2:
            continue
        idx = [i for i, v in enumerate(vals) if v is not None]
        if not idx:
            continue
        base = vals[idx[0]]
        if isinstance(base, (int, float)) and not isinstance(base, bool):
            alt = base + 1
            if 'lo' in dom and 'hi' in dom:
                alt = min(dom['hi'], max(dom['lo'], alt))
                if alt == base:
                    alt = max(dom['lo'], base - 1)
        else:
            alt = str(base) + 'x'
        vals[rng.choice(idx)] = alt
    return cols


def _ensure_unmatched_join(schema, spec, inst: dict, rng) -> None:
    """At least one parent row without children and at least one child row with NULL FK."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or pt not in inst:
            continue
        child = inst[ct].get(cc)
        parent = inst[pt].get(pc)
        if not child or not parent:
            continue
        if any(v is None for v in child):
            pass
        else:
            child[rng.randrange(len(child))] = None
        used = {v for v in child if v is not None}
        free = [v for v in parent if v not in used]
        if not free:
            ints = [v for v in parent if isinstance(v, int)]
            extra = (max(ints) + 1) if ints else 1
            parent.append(extra)


def _check_ok(schema, spec, table: str, row: dict) -> bool:
    """Evaluate CHECK constraints and specification formulas in Python."""
    for (t, c), exprs in schema.checks.items():
        if t != table or c not in row:
            continue
        v = row[c]
        if v is None:
            continue
        for expr in exprs:
            m = re.search(r'%s\s*(>=|<=|>|<|=|!=|<>)\s*(-?[\d.]+)' % re.escape(c), expr, re.I)
            if m:
                op, rhs = m.group(1), float(m.group(2))
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                ok = {'>=': x >= rhs, '<=': x <= rhs, '>': x > rhs, '<': x < rhs,
                      '=': x == rhs, '!=': x != rhs, '<>': x != rhs}[op]
                if not ok:
                    return False
            m = re.search(r'%s\s+IN\s*\(([^)]*)\)' % re.escape(c), expr, re.I)
            if m:
                allowed = {x.strip().strip("'\"") for x in m.group(1).split(',')}
                if str(v) not in allowed:
                    return False
    for rule in spec.get('semantic_rules_and_formulas', []):
        if rule.get('table') != table or rule.get('column') not in row:
            continue
        v = row[rule['column']]
        if v is None:
            continue
        f = rule.get('formula', '')
        m = re.search(r'BETWEEN\s+(-?[\d.]+)\s+AND\s+(-?[\d.]+)', f, re.I)
        if m:
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if not (float(m.group(1)) <= x <= float(m.group(2))):
                return False
        m = re.search(r'>=\s*(-?[\d.]+)', f)
        if m:
            try:
                if float(v) < float(m.group(1)):
                    return False
            except (TypeError, ValueError):
                pass
        m = re.search(r'<=\s*(-?[\d.]+)', f)
        if m:
            try:
                if float(v) > float(m.group(1)):
                    return False
            except (TypeError, ValueError):
                pass
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m:
            allowed = {x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()}
            if allowed and str(v) not in allowed:
                return False
    return True


def _filter_checks(schema, spec, table: str, cols: dict) -> dict:
    """Drop rows failing a CHECK constraint or specification formula (counted by the writer)."""
    n = _nrows(cols)
    if n == 0:
        return cols
    keep = []
    for i in range(n):
        row = {c: cols[c][i] for c in cols}
        if _check_ok(schema, spec, table, row):
            keep.append(i)
    return _filter(cols, keep)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    if spec is None:
        spec = getattr(schema, 'spec', {}) or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = _build_columns(schema, spec, t, n, rng, literal_pool)
        inst[t] = cols
        fk = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk)
        cols = _plant_nulls(schema, spec, t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols, [u for (ut, u) in schema.unique_tuples if ut == t])
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _filter_checks(schema, spec, t, cols)
        cols = _enforce_null_mix(schema, spec, t, cols, rng)
        cols = _enforce_distinct(schema, spec, t, cols, rng)
        inst[t] = cols
    _ensure_unmatched_join(schema, spec, inst, rng)
    return {t: inst[t] for t in schema.tables if t in inst}
