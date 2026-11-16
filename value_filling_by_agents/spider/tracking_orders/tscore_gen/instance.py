"""Random instance construction (fuzz/fuzz.py:83-196) adapted for round 1."""
import datetime as dt

from .spec import parse_duplicate_share, spec_for_column
from .values import _init_sampler

_DT_FMT = '%Y-%m-%d %H:%M:%S'


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _parse_dt(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v
    try:
        return dt.datetime.strptime(str(v), _DT_FMT)
    except ValueError:
        return None


def _fmt_dt(d):
    return d.strftime(_DT_FMT)


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, taken: dict) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(taken.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_taken(schema, table: str) -> tuple:
    """PK tuples and per-unique-column value sets of the compact rows of `table`."""
    tm = schema.tables[table]
    pk = set()
    if tm.primary_key:
        cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
        for i in range(min([len(c) for c in cols] or [0])):
            pk.add(tuple(c[i] for c in cols))
    uniq = {}
    for cm in tm.columns:
        if cm.unique:
            uniq[cm.name] = set(schema.original_values.get((table, cm.name), []))
    return pk, uniq


def _parent_values(instance: dict, schema, table: str, column: str) -> list:
    """Compact + generated values of a parent column (in memory, never via SQL)."""
    vals = list(schema.original_values.get((table, column), []))
    vals += list(instance.get(table, {}).get(column, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specification sizes when given, else the upstream rand_lin / level x4 choice."""
    spec_sizes = (spec or {}).get('table_sizes_per_instance') or {}
    if spec_sizes:
        sizes = {}
        for lvl in schema.table_order:
            for t in lvl:
                base = int(spec_sizes.get(t, 0))
                if rng.random() < 0.5:
                    sizes[t] = max(0, min(230, base + rng.randint(-3, 3)))
                else:
                    sizes[t] = max(0, min(2500, base * rng.choice([1, 1, 2, 4])))
        return sizes
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


def _apply_duplicate_share(values: list, share, rng) -> list:
    """Cap the number of distinct values so that the duplicate share falls in `share`."""
    if not share or not values:
        return values
    lo, hi = share
    target = rng.uniform(lo, hi)
    n = len(values)
    n_distinct = max(1, int(round(n * (1.0 - target))))
    pool = list(dict.fromkeys(values))[:n_distinct]
    if not pool:
        return values
    return [rng.choice(pool) for _ in range(n)]


def _apply_group_sizes(values: list, rng) -> list:
    """Plant groups of size 1, 2 and >= 3 (values repeated to form the groups)."""
    if not values:
        return values
    n = len(values)
    out = []
    i = 0
    while len(out) < n:
        g = rng.choice([1, 1, 2, 3, 3, 4])
        v = values[i % n]
        out.extend([v] * g)
        i += 1
    return out[:n]


def _apply_null_rule(values: list, column, rng, compact_null_share: float) -> list:
    """NULL is a value: at least one NULL and one non-NULL row per nullable column."""
    if column.notnull or column.pk_pos > 0:
        return values
    n = len(values)
    if n < 2:
        return values
    share = compact_null_share
    if share <= 0.0:
        share = 1.0 / n
    k = max(1, int(round(n * share)))
    k = min(k, n - 1)
    idx = rng.sample(range(n), k)
    out = list(values)
    for j in idx:
        out[j] = None
    return out


def _apply_tie_rank(instance: dict, schema, table: str, column: str, tie: dict, rng) -> None:
    """Plant at least two parent rows sharing the rank-1 aggregate value."""
    if not tie or table not in instance:
        return
    joins = tie.get('tie_on') or []
    child = None
    for (ct, cc), (pt, pc) in schema.fks.items():
        if pt == table and pc == column:
            child = (ct, cc)
            break
    if child is None or child[0] not in instance:
        return
    ct, cc = child
    parent_keys = [v for v in instance[table].get(column, []) if v is not None]
    if len(parent_keys) < 2:
        return
    child_cols = instance[ct]
    if cc not in child_cols:
        return
    from collections import Counter
    counts = Counter(v for v in child_cols[cc] if v is not None)
    a, b = rng.sample(parent_keys, 2)
    target = max(counts.get(a, 0), counts.get(b, 0), 1)
    vals = list(child_cols[cc])
    kept = [v for v in vals if v not in (a, b)]
    kept += [a] * target + [b] * target
    n = len(vals)
    if len(kept) > n:
        kept = kept[:n]
    while len(kept) < n:
        kept.append(rng.choice(parent_keys))
    child_cols[cc] = kept


def _rederive_foreign_keys(instance: dict, schema, rng) -> None:
    """Re-derive every FK column from the FINAL surviving parent key sets."""
    for t in [x for lvl in schema.table_order for x in lvl]:
        tm = schema.tables[t]
        cols = instance.get(t, {})
        if not cols:
            continue
        n = _n_rows(cols)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = _parent_values(instance, schema, pt, pc)
            if not pv:
                if not cm.notnull:
                    cols[cm.name] = [None] * n
                continue
            if cm.notnull:
                cols[cm.name] = [rng.choice(pv) for _ in range(n)]
            else:
                old = cols[cm.name]
                pset = set(pv)
                cols[cm.name] = [None if v is None else (v if v in pset else rng.choice(pv))
                                 for v in old]


def check_instance_integrity(schema, instance: dict) -> list:
    """Post-build self-check: FK references, NOT NULL, PK uniqueness (compact + generated)."""
    problems = []
    for t, tm in schema.tables.items():
        cols = instance.get(t, {})
        if not cols:
            continue
        n = _n_rows(cols)
        for cm in tm.columns:
            if cm.notnull and cm.name in cols:
                if any(v is None for v in cols[cm.name]):
                    problems.append('%s.%s NULL in NOT NULL column' % (t, cm.name))
        if tm.primary_key:
            pk_taken, _ = _compact_taken(schema, t)
            seen = set(pk_taken)
            for i in range(n):
                k = tuple(cols[c][i] for c in tm.primary_key)
                if k in seen:
                    problems.append('%s PK duplicate %r' % (t, k))
                    break
                seen.add(k)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks or cm.name not in cols:
                continue
            pt, pc = schema.fks[key]
            pv = set(_parent_values(instance, schema, pt, pc))
            for v in cols[cm.name]:
                if v is None:
                    if cm.notnull:
                        problems.append('%s.%s NULL FK' % (t, cm.name))
                        break
                elif v not in pv:
                    problems.append('%s.%s FK %r not in parent' % (t, cm.name, v))
                    break
    return problems


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact database."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    spec_cols = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                sc = spec_for_column(spec, t, cm.name)
                spec_cols[(t, cm.name)] = sc
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec_col=sc)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            sc = spec_cols.get((t, cm.name), {})
            share = parse_duplicate_share(sc.get('duplicate_share'))
            if share:
                cols[cm.name] = _apply_duplicate_share(cols[cm.name], share, rng)
            if sc.get('group_sizes'):
                cols[cm.name] = _apply_group_sizes(cols[cm.name], rng)
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.0
            cols[cm.name] = _apply_null_rule(cols[cm.name], cm, rng, share)
        pk_taken, uniq_taken = _compact_taken(schema, t)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, pk_taken)
        cols = drop_unique_duplicates(tm, cols, uniq_taken)
        inst[t] = cols
    _rederive_foreign_keys(inst, schema, rng)
    for (t, c), sc in spec_cols.items():
        if sc.get('tie_rank'):
            _apply_tie_rank(inst, schema, t, c, sc['tie_rank'], rng)
    return {t: inst[t] for t in schema.tables}
