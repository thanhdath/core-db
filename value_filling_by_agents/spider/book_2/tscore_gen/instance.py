"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt
import random

from . import spec
from .values import _init_sampler

SPEC_SIZES = dict(spec.TABLE_SIZES)

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
           'October', 'November', 'December']


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats or collides with compact keys, first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict = None) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    taken = taken or {}
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated parent values for a FK target."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: float = None) -> dict:
    """FK child columns draw only from the parent's compact+generated values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = []
        share = null_share if null_share is not None else _compact_null_share(schema, table, cm.name)
        n_null = int(round(n * share))
        if cm.notnull:
            n_null = 0
        elif spec.NULL_AT_LEAST_ONE and n > 0:
            n_null = max(1, n_null)
        n_null = min(n_null, n)
        for _ in range(n):
            vals.append(rng.choice(pv))
        for j in range(n_null):
            pos = int((j + 0.5) * n / n_null) if n_null else 0
            pos = min(max(pos, 0), n - 1)
            vals[pos] = None
        out[cm.name] = vals
    return out


def _compact_null_share(schema, table: str, column: str) -> float:
    """NULL share of a column in the compact database (0.0 if no values)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / len(vals)


def _plant_nulls(columns: dict, table_meta, rng, schema=None, table: str = None) -> None:
    """Plant NULLs to follow the compact share per nullable column."""
    for cm in table_meta.columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in columns:
            continue
        col = columns[cm.name]
        n = len(col)
        if n == 0:
            continue
        share = _compact_null_share(schema, table, cm.name) if schema is not None else 0.0
        if share > 0.0:
            n_null = int(round(n * share))
        else:
            n_null = 1 if spec.NULL_AT_LEAST_ONE else 0
        n_null = min(n_null, n)
        already = sum(1 for v in col if v is None)
        need = n_null - already
        if need <= 0:
            continue
        free = [i for i, v in enumerate(col) if v is not None]
        if not free:
            continue
        rng.shuffle(free)
        for i in free[:need]:
            col[i] = None


def _enforce_duplicate_share(columns: dict, table: str, rng) -> None:
    """Force a 20-50 % duplicate share on DISTINCT columns (spec.DUPLICATE_SHARE_COLUMNS)."""
    for (t, c), (lo, hi) in spec.DUPLICATE_SHARE_COLUMNS.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n < 2:
            continue
        target = max(1, int(round(n * rng.uniform(lo, hi))))
        seen = []
        for i in range(n):
            if col[i] is not None and i < n - target:
                seen.append(col[i])
            elif col[i] is not None:
                col[i] = rng.choice(seen) if seen else col[i]


def _enforce_text_literals(columns: dict, table: str, rng) -> None:
    """Guarantee all specification TEXT_LITERALS appear in the column (deterministic)."""
    for (t, c), lits in spec.TEXT_LITERALS.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n == 0:
            continue
        for j, lit in enumerate(lits):
            pos = j % n
            col[pos] = lit


def _enforce_aggregate_boundary(columns: dict, table: str, rng) -> None:
    """Publisher must have groups with COUNT(*) = 1 and 2; the absent value is never written."""
    for (t, c), cfg in spec.AGGREGATE_BOUNDARY.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n < 2:
            continue
        absent = cfg.get('absent_value')
        base_lits = spec.TEXT_LITERALS.get((t, c), [])
        start = min(len(base_lits), n)
        if not hasattr(_enforce_aggregate_boundary, '_placeholder'):
            pass
        two_val = 'Wiley' if 'Wiley' in base_lits else (base_lits[0] if base_lits else col[0])
        if start + 1 < n:
            col[start] = two_val
            col[start + 1] = two_val
        elif n >= 2:
            col[0] = two_val
            col[1] = two_val
        one_val = None
        for lit in base_lits:
            if lit != two_val:
                one_val = lit
                break
        if one_val is not None:
            free = [i for i in range(n) if col[i] != two_val]
            if free:
                col[free[0]] = one_val
        if absent is not None:
            for i in range(n):
                if col[i] == absent:
                    col[i] = one_val if one_val is not None else two_val


def _enforce_text_literals_final(columns: dict, table: str) -> None:
    """Re-plant all TEXT_LITERALS after every other text mutation (they must all be present)."""
    for (t, c), lits in spec.TEXT_LITERALS.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n == 0:
            continue
        for j, lit in enumerate(lits):
            if j < n:
                col[j] = lit


def _month_year(i: int) -> str:
    """'Month YYYY' string from spec.DATE_TEMPLATE, cycling months and years."""
    m = _MONTHS[i % 12]
    y = 2004 + (i // 12)
    return dt.datetime(y, (i % 12) + 1, 1).strftime(spec.DATE_TEMPLATE)


def _enforce_group_sizes(columns: dict, table: str, rng) -> None:
    """Publication_Date must have groups of size 1, 2 and >= 3, plus a tie at rank 1 for COUNT(*) DESC."""
    for (t, c), cfg in spec.GROUP_SIZE_TARGETS.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n < 6:
            continue
        dates = [_month_year(k) for k in range(8)]
        m = max(3, (n - 3) // 2)
        while 1 + 2 + 2 * m > n and m > 2:
            m -= 1
        idx = 0
        plan = [1, 2]
        plan += [m, m]
        fill_pos = 0
        for gi, size in enumerate(plan):
            for _ in range(size):
                if idx < n:
                    col[idx] = dates[gi]
                    idx += 1
        for i in range(idx, n):
            col[i] = dates[3]
        from collections import Counter
        cnt = Counter(col)
        if not cnt:
            continue
        mx = max(cnt.values())
        if sum(1 for v in cnt.values() if v == mx) < 2:
            top = [v for v, k in cnt.items() if k == mx]
            target = top[0]
            other = next((v for v in cnt if v != target), dates[0])
            for i in range(n):
                if col[i] == target:
                    col[i] = other
                    break


def _enforce_price_ties(columns: dict, table: str, n_min: int, n_max: int) -> None:
    """Ensure min and max Price each appear >= n_min / n_max times (ties at rank 1 ASC + DESC)."""
    for (t, c), vals in spec.BOUNDARY_VALUES.items():
        if t != table or c != 'Price' or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n < 2:
            continue
        min_v = min(vals)
        max_v = max(vals)
        from collections import Counter
        cnt = Counter(col)
        pos = 0
        want = 0
        while cnt.get(min_v, 0) < n_min and pos < n // 2:
            if col[pos] != min_v:
                col[pos] = min_v
                cnt = Counter(col)
            pos += 1
        pos = n - 1
        while cnt.get(max_v, 0) < n_max and pos >= n // 2:
            if col[pos] != max_v:
                col[pos] = max_v
                cnt = Counter(col)
            pos -= 1


def _enforce_price_diff_groups(columns: dict, table: str, group_col: str = 'Book_ID') -> None:
    """At least one group (by group_col) has >= 2 rows with different Price values."""
    if 'Price' not in columns or group_col not in columns:
        return
    price = columns['Price']
    groups: dict = {}
    n = len(price)
    for i in range(n):
        groups.setdefault(columns[group_col][i], []).append(i)
    for g, idxs in groups.items():
        if len(idxs) < 2:
            continue
        if len({price[i] for i in idxs}) >= 2:
            return
    for g, idxs in groups.items():
        if len(idxs) >= 2:
            a, b = idxs[0], idxs[1]
            if price[a] == price[b]:
                price[b] = price[a] + 1.0 if price[a] < 1e9 else price[a] - 1.0
            return
    if len({price[i] for i in range(n)}) >= 2:
        return
    if n >= 2:
        price[1] = price[0] + 1.0


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance; fallback to upstream rand_lin/level sizes."""
    sizes = {}
    for t in schema.tables:
        if t in SPEC_SIZES:
            sizes[t] = SPEC_SIZES[t]
        else:
            sizes[t] = int(30 * rng.random() + rng.random() * 200)
    return sizes


def _boundaries_for(table: str, column: str) -> list:
    return spec.BOUNDARY_VALUES.get((table, column), [])


def _template_for(table: str, column: str):
    if (table, column) in spec.GROUP_SIZE_TARGETS:
        return spec.DATE_TEMPLATE
    if 'date' in column.lower():
        return spec.DATE_TEMPLATE
    return None


def _plant_boundary_values(columns: dict, table: str, rng) -> None:
    """Deterministic planting of boundary literals: each listed value and one step on each side."""
    for (t, c), vals in spec.BOUNDARY_VALUES.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        n = len(col)
        if n == 0:
            continue
        nonneg = (t, c) in spec.NON_NEGATIVE
        step = 1.0
        seq = []
        for v in vals:
            seq.extend([v, v - step, v + step])
        if nonneg:
            seq = [max(0.0, x) for x in seq]
        for j, v in enumerate(seq):
            pos = j % n
            col[pos] = v


def _clamp_nonneg(columns: dict, table: str) -> None:
    """Final safety clamp: any negative value in a NON_NEGATIVE column is replaced with 0/1."""
    for (t, c), flag in spec.NON_NEGATIVE.items():
        if t != table or c not in columns:
            continue
        col = columns[c]
        floor = 1 if (t, c) in spec.POSITIVE else 0
        for i, v in enumerate(col):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v < floor:
                col[i] = floor


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) appended to compact rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                pool = list(literal_pool.get((t, cm.name), []))
                pool += [str(v) for v in spec.TEXT_LITERALS.get((t, cm.name), [])]
                samplers[(t, cm.name)] = _init_sampler(
                    cm, pool, schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), boundaries=_boundaries_for(t, cm.name),
                    template=_template_for(t, cm.name), table=t)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for cname, vals in fk_cols.items():
            cm = next(c for c in tm.columns if c.name == cname)
            share = _compact_null_share(schema, t, cname)
            if cm.notnull:
                n_null = 0
            elif share > 0.0:
                n_null = min(n, int(round(n * share)))
            else:
                n_null = 1 if (spec.NULL_AT_LEAST_ONE and n > 0) else 0
            n_null = min(n_null, n)
            already = sum(1 for v in vals if v is None)
            need = n_null - already
            if need > 0:
                free = [i for i, v in enumerate(vals) if v is not None]
                rng.shuffle(free)
                for i in free[:need]:
                    vals[i] = None
        cols.update(fk_cols)
        taken = set()
        if tm.primary_key:
            taken = {tuple(r) for r in zip(*[schema.original_values.get((t, c), []) for c in tm.primary_key])}
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _enforce_duplicate_share(cols, t, rng)
        _enforce_aggregate_boundary(cols, t, rng)
        _enforce_group_sizes(cols, t, rng)
        _plant_boundary_values(cols, t, rng)
        _enforce_price_ties(cols, t, spec.PRICE_TIE_MIN, spec.PRICE_TIE_MAX)
        _enforce_price_diff_groups(cols, t)
        _clamp_nonneg(cols, t)
        _enforce_text_literals_final(cols, t)
        _plant_nulls(cols, tm, rng, schema=schema, table=t)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
