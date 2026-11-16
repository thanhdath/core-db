"""Specification-driven row construction, implemented by construction in Python."""
from collections import Counter

from .instance import choose_table_sizes
from .values import _init_sampler

_BLOCK_SIZES = {'people': 7, 'company': 10, 'employment': 8}
_HQ_NEAR = ['usa', 'USB', 'USA x', 'USAx']
_HQ_LIKE = ['USA%', '%USA%']
_HQ_POOL = ['USA', 'Netherlands', 'China', 'UK', 'Brazil', 'Russia', 'Germany', 'France']
_SALES_BOUNDARY = [199.9, 200.0, 200.1, 200.9, 201.0, 201.1]
_INDUSTRY_ENUM = ['Oil and gas', 'Banking', 'Conglomerate', 'Retailing', 'Automotive']


def _jitter(rng, n):
    """Small per-instance variation so instances are not identical in size."""
    return max(0, n + rng.randint(-2, 2))


def _isnum(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _group_sizes_ok(values):
    """True if the non-NULL values contain groups of size 1, 2 and >=3."""
    cnt = Counter(v for v in values if v is not None)
    sizes = set(cnt.values())
    return 1 in sizes and 2 in sizes and any(s >= 3 for s in sizes)


def _force_groups(values, rng, protected=()):
    """Ensure the value list contains groups of size 1, 2 and >=3."""
    n = len(values)
    if n < 6:
        return values
    if _group_sizes_ok(values):
        return values
    out = list(values)
    free = [i for i in range(n) if i not in protected]
    if len(free) < 6:
        return out
    rng.shuffle(free)
    present = sorted({v for v in out if v is not None})
    if len(present) >= 3:
        a, b, c = present[0], present[1], present[2]
    elif present:
        a = present[0]
        b = (a + 1.0) if isinstance(a, (int, float)) else a + '_b'
        c = (a + 2.0) if isinstance(a, (int, float)) else a + '_c'
    else:
        return out
    for i in free:
        out[i] = a
    out[free[0]] = a
    out[free[1]] = b
    out[free[2]] = b
    for j in range(3, min(len(free), 6)):
        out[free[j]] = c
    return out


def _apply_duplicates(values, rng, share=None, protected=()):
    """Make 20-50% of values duplicate values of the first distinct slot."""
    n = len(values)
    if n < 4:
        return values
    if share is None:
        share = rng.uniform(0.20, 0.50)
    k = int(round(n * share))
    k = max(1, min(k, n - 1))
    out = list(values)
    src = out[0]
    cand = [i for i in range(1, n) if i not in protected]
    if not cand:
        return out
    k = min(k, len(cand))
    for i in rng.sample(cand, k):
        out[i] = src
    return out


def _inject_hq(values, rng):
    """Company.Headquarters: group sizes, DISTINCT duplicates, tied rank-1 DESC, LIKE near-variants."""
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    pool = list(_HQ_POOL)
    rng.shuffle(pool)
    for i in range(n):
        out[i] = pool[i % len(pool)]
    k_near = max(1, int(round(n * rng.uniform(0.15, 0.30))))
    near_pool = _HQ_NEAR + _HQ_LIKE
    near_idx = rng.sample(range(n), min(k_near, n))
    for j, i in enumerate(near_idx):
        out[i] = near_pool[j % len(near_pool)]
    protected = set(near_idx)
    dups = [i for i in range(n) if i not in protected]
    if dups:
        k_dup = max(1, int(round(len(dups) * rng.uniform(0.20, 0.50))))
        for i in rng.sample(dups, min(k_dup, len(dups))):
            out[i] = 'USA'
    out = _force_groups(out, rng, protected=protected)
    mx = max(out)
    max_positions = [i for i, v in enumerate(out) if v == mx]
    if len(max_positions) < 2:
        target = next((i for i in range(n) if out[i] != mx and i not in protected), None)
        if target is None:
            target = next((i for i in range(n) if out[i] != mx), None)
        if target is not None:
            out[target] = mx
    if not _group_sizes_ok(out):
        out = _force_groups(out, rng, protected=protected)
        mx = max(out)
        if sum(1 for v in out if v == mx) < 2:
            target = next((i for i in range(n) if out[i] != mx and i not in protected), None)
            if target is not None:
                out[target] = mx
    return out


def _inject_sales(values, rng):
    """Company.Sales_in_Billion: comparison boundary literals and tied maximum at rank 1 (DESC)."""
    n = len(values)
    if n == 0:
        return values
    out = [float(v) if v is not None else None for v in values]
    boundary = list(_SALES_BOUNDARY)
    rng.shuffle(boundary)
    slots = list(range(n))
    rng.shuffle(slots)
    placed = 0
    for v in boundary:
        if placed >= n:
            break
        out[slots[placed]] = v
        placed += 1
    boundary_set = set(_SALES_BOUNDARY)
    mx = max(v for v in out if v is not None)
    max_pos = [i for i, v in enumerate(out) if v == mx]
    if len(max_pos) < 2:
        target = next((i for i in range(n) if i not in max_pos and out[i] not in boundary_set), None)
        if target is None:
            target = next((i for i in range(n) if i not in max_pos), None)
        if target is not None:
            out[target] = mx
    uniq = len(set(v for v in out if v is not None))
    if uniq < 2 and n >= 2:
        out[0] = mx
        out[1] = mx - 0.1
    return out


def _inject_industry(values, rng):
    """Company.Industry: enum values plus the 'oil and gas' near-variant."""
    n = len(values)
    if n == 0:
        return values
    out = [_INDUSTRY_ENUM[i % len(_INDUSTRY_ENUM)] for i in range(n)]
    if n >= 2:
        out[rng.randrange(n)] = 'oil and gas'
    return out


def _apply_null_rule(values, nullable: bool, compact_nulls: int, compact_rows: int, rng):
    """NULL is a value: plant >=1 NULL if the column is nullable; share ~ compact share."""
    n = len(values)
    if not nullable or n == 0:
        return values
    out = list(values)
    share = (compact_nulls / compact_rows) if compact_rows > 0 else 0.0
    k = max(1, int(round(n * share))) if share > 0 else 1
    k = max(1, min(k, n))
    idx = rng.sample(range(n), k)
    for i in idx:
        out[i] = None
    return out


def _parent_keys(inst: dict, table: str, col: str) -> list:
    return list(inst.get(table, {}).get(col) or [])


def _sample_fk(child_row_count: int, parent_keys: list, rng, allow_null: bool,
               reserved_childless: set = None) -> list:
    """FK child values draw from in-memory parent keys, or NULL by the NULL rule."""
    if not parent_keys:
        return [None] * child_row_count
    reserved = reserved_childless or set()
    pool = [k for k in parent_keys if k not in reserved]
    if not pool:
        pool = list(parent_keys)
    vals = [rng.choice(pool) for _ in range(child_row_count)]
    if allow_null:
        vals = _apply_null_rule(vals, True, 0, 0, rng)
    return vals


def _reserve_childless(parent_keys: list, rng, share=(0.20, 0.30)) -> set:
    """Reserve ~20-30% of parent keys (at least one) to remain childless."""
    if not parent_keys:
        return set()
    k = max(1, int(round(len(parent_keys) * rng.uniform(*share))))
    k = min(k, len(parent_keys))
    return set(rng.sample(list(parent_keys), k))


def _next_pk_start(schema, table: str, col: str) -> int:
    """Smallest integer strictly greater than every compact integer-valued key."""
    vals = schema.original_values.get((table, col), [])
    mx = 0
    for v in vals:
        if v is None:
            continue
        try:
            iv = int(float(v))
        except (TypeError, ValueError):
            continue
        if iv > mx:
            mx = iv
    return mx + 1


def _assign_sequential_pk(cols, tm, colname, start, n):
    """Assign sequential distinct integer PK values starting at `start`."""
    cols[colname] = [start + i for i in range(n)]


def build_spec_rows(schema, pool: dict, rng, sizes=None) -> dict:
    """Build one appended block of rows per table (fully in memory; no SQL rule evaluation)."""
    if sizes is None:
        sizes = choose_table_sizes(schema, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    inst: dict = {}
    childless: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = _jitter(rng, _BLOCK_SIZES.get(t, max(0, sizes.get(t, 0) // 4)))
        n = max(0, min(n, 230))
        p = 0.0 if rng.random() < 0.3 else 0.2
        cols: dict = {}
        samplers = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = (t, cm.name)
            lit = pool.get(key, [])
            ov = schema.original_values.get(key, [])
            samplers[cm.name] = _init_sampler(cm, lit, ov, p, rng, len(tm.primary_key))
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            s = samplers[cm.name]
            cols[cm.name] = [s.sample() for _ in range(n)]
        lname = t.lower()
        if lname == 'company':
            _company_patterns(tm, cols, n, rng)
        elif lname == 'people':
            _people_patterns(tm, cols, n, rng)
        _coerce_numeric(tm, cols)
        if len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                start = _next_pk_start(schema, t, pk)
                _assign_sequential_pk(cols, tm, pk, start, n)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_keys = _parent_keys(inst, pt, pc)
            allow_null = not cm.notnull and cm.pk_pos == 0
            if (t == 'employment' and cm.name.lower() == 'company_id'):
                allow_null = False
            if (pt, pc) not in childless:
                childless[(pt, pc)] = _reserve_childless(parent_keys, rng)
            cols[cm.name] = _sample_fk(n, parent_keys, rng, allow_null,
                                       reserved_childless=childless[(pt, pc)])
        cols = _dedup_against_inst(tm, cols, inst, schema)
        if not cols or not tm.columns:
            inst[t] = {}
            continue
        if not cols.get(tm.columns[0].name):
            inst[t] = {}
            continue
        inst[t] = cols
    for t in order:
        tm = schema.tables[t]
        cols = inst.get(t, {})
        if not cols:
            continue
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            if cm.notnull or cm.pk_pos > 0:
                continue
            if (t, cm.name) in schema.fks:
                continue
            compact_vals = schema.original_values.get((t, cm.name), [])
            compact_nulls = sum(1 for v in compact_vals if v is None)
            compact_rows = len(compact_vals)
            cols[cm.name] = _apply_null_rule(cols[cm.name], True, compact_nulls, compact_rows, rng)
    return {t: inst.get(t, {}) for t in schema.tables}


def _company_patterns(tm, cols, n, rng):
    """Apply the company-table specification patterns by construction (in memory)."""
    names = {c.name.lower(): c.name for c in tm.columns}
    hq = names.get('headquarters')
    if hq and hq in cols:
        cols[hq] = _inject_hq(cols[hq], rng)
    nm = names.get('name')
    if nm and nm in cols:
        cols[nm] = _force_groups(cols[nm], rng)
    prof = names.get('profits_in_billion')
    if prof and prof in cols:
        cols[prof] = _num_group(cols[prof], rng)
    assets = names.get('assets_in_billion')
    if assets and assets in cols:
        cols[assets] = _num_group(cols[assets], rng)
    sales = names.get('sales_in_billion')
    if sales and sales in cols:
        cols[sales] = _inject_sales(cols[sales], rng)
    ind = names.get('industry')
    if ind and ind in cols:
        cols[ind] = _inject_industry(cols[ind], rng)


def _people_patterns(tm, cols, n, rng):
    names = {c.name.lower(): c.name for c in tm.columns}
    nm = names.get('name')
    if nm and nm in cols:
        cols[nm] = _apply_duplicates(cols[nm], rng)
    age = names.get('age')
    if age and age in cols:
        cols[age] = [rng.randint(18, 70) for _ in range(n)]


def _num_group(values, rng):
    """Force group sizes 1/2/3+ for a numeric column, keeping non-negative code path."""
    if len(values) < 6:
        return values
    base = [v for v in values if v is not None]
    if not base:
        return values
    a = base[0]
    b = next((v for v in base if v != a), a + 1.0 if isinstance(a, (int, float)) else a)
    c = next((v for v in base if v not in (a, b)), (b + 1.0) if isinstance(b, (int, float)) else b)
    res = list(values)
    idx = list(range(len(res)))
    rng.shuffle(idx)
    for i in idx:
        res[i] = a
    res[idx[0]] = a
    res[idx[1]] = b
    res[idx[2]] = b
    for j in range(3, min(len(res), 6)):
        res[idx[j]] = c
    return [None if v is None else (abs(v) if _isnum(v) else v) for v in res]


def _coerce_numeric(tm, cols):
    """Convert values to float/int if the column declares a numeric type."""
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        t = (cm.type_str or '').lower()
        is_int = ('int' in t) and not any(k in t for k in ('float', 'real', 'double', 'decimal'))
        is_num = any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real'))
        if not is_num:
            continue
        out = []
        for v in cols[cm.name]:
            if v is None:
                out.append(None)
            elif isinstance(v, (int, float)):
                out.append(int(v) if is_int else float(v))
            elif _isnum(v):
                out.append(int(float(v)) if is_int else float(v))
            else:
                out.append(v)
        cols[cm.name] = out


def _dedup_against_inst(tm, cols, inst, schema):
    """Drop rows whose PK tuple repeats compact or previously generated keys (first occurrence kept)."""
    if not tm.primary_key:
        return cols
    names = list(cols.keys())
    if not names:
        return cols
    n = len(next(iter(cols.values())))
    existing = set()
    pk_cols = tm.primary_key
    if all(c in schema.original_values for c in [(tm.name, p) for p in pk_cols]):
        lists = [schema.original_values[(tm.name, p)] for p in pk_cols]
        m = min(len(x) for x in lists)
        for i in range(m):
            existing.add(tuple(lists[j][i] for j in range(len(pk_cols))))
    keep = []
    seen = set()
    for i in range(n):
        kvals = tuple(cols[c][i] if c in cols else None for c in pk_cols)
        if kvals in seen or kvals in existing:
            continue
        if all(v is None for v in kvals):
            continue
        seen.add(kvals)
        keep.append(i)
    if len(keep) == n:
        return cols
    return {c: [v[i] for i in keep] for c, v in cols.items()}
