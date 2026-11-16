"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt
import random

from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set = None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    seen = set(existing or ())
    n = len(next(iter(columns.values())))
    keep = []
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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact_ids: dict = None) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement."""
    compact_ids = compact_ids or {}
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or []) + list(compact_ids.get((pt, pc), []))
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng, spec: dict = None) -> dict:
    """Spec sizes when given; else uniform rand_lin sizes w.p."""
    spec = spec or {}
    fixed = spec.get('table_sizes') or {}
    if fixed:
        return {t: int(fixed.get(t, 0)) for lvl in schema.table_order for t in lvl}
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


def _apply_null_rule(cols: dict, table: str, tm, spec: dict, rng) -> None:
    """NULL is a value: at least one NULL row per nullable column, share from the compact DB."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for cm in tm.columns:
        if cm.name not in cols or cm.pk_pos > 0 or cm.notnull:
            continue
        share = spec.get('null_share', {}).get((table, cm.name))
        if share is None:
            share = 0.05
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None


def _fix_ohlc(cols: dict, rng) -> None:
    """high >= max(open, close, low); low <= min(open, close); all non-negative (SQL 3VL: NULLs skipped)."""
    n = len(cols.get('price', [])) if cols else 0
    for i in range(n):
        o, h, l, c = cols['open'][i], cols['high'][i], cols['low'][i], cols['close'][i]
        vals = [v for v in (o, h, l, c) if v is not None]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        if h is not None and h < hi:
            cols['high'][i] = hi
        if l is not None and l > lo:
            cols['low'][i] = lo
        for k in ('open', 'high', 'low', 'close', 'price'):
            if cols.get(k) and cols[k][i] is not None and cols[k][i] < 0:
                cols[k][i] = abs(cols[k][i])


def _fix_date_launched(cols: dict) -> None:
    """date_launched >= date_added when both non-NULL."""
    da, dl = cols.get('date_added'), cols.get('date_launched')
    if not da or not dl:
        return
    for i in range(len(da)):
        if da[i] is not None and dl[i] is not None and str(dl[i]) < str(da[i]):
            cols['date_launched'][i] = da[i]


def _fix_percent(cols: dict) -> None:
    for k in ('percent_change_1h', 'percent_change_24h', 'percent_change_7d'):
        if k in cols:
            cols[k] = [None if v is None else max(-100.0, min(1000.0, v)) for v in cols[k]]


def _fix_rank(cols: dict) -> None:
    if 'cmc_rank' in cols:
        cols['cmc_rank'] = [None if v is None else max(1, int(v)) for v in cols['cmc_rank']]


def _fix_volume(cols: dict, rng) -> None:
    """rows_with_different_values: at least two distinct volume_24h values per group."""
    v = cols.get('volume_24h')
    if not v:
        return
    nonnull = [i for i, x in enumerate(v) if x is not None]
    if len(nonnull) >= 2 and len({v[i] for i in nonnull}) < 2:
        v[nonnull[1]] = (v[nonnull[0]] or 0.0) + 1.0


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) with spec-driven construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec=spec)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    compact_ids = {}
    for (t, c), vals in schema.original_values.items():
        compact_ids[(t, c)] = [v for v in vals if v is not None]
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact_ids))
        existing = set()
        if tm.primary_key:
            pkvals = [compact_ids.get((t, c), []) for c in tm.primary_key]
            if all(pkvals):
                existing = set(zip(*pkvals))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _apply_null_rule(cols, t, tm, spec, rng)
        if t == 'historical':
            _fix_ohlc(cols, rng)
            _fix_percent(cols)
            _fix_rank(cols)
            _fix_volume(cols, rng)
        if t == 'coins':
            _fix_date_launched(cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
