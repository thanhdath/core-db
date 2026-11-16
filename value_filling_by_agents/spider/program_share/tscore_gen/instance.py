"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
from .values import _init_sampler, EnumSampler, DateTextSampler, NumberSampler


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


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes (spec.TABLE_SIZES) with small per-instance jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        jitter = rng.choice([-1, 0, 0, 1])
        sizes[t] = max(0, base + jitter)
    return sizes


def _max_int(schema, table, col):
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, (int, float))]
    return int(max(vals)) if vals else 0


def _apply_duplicate_share(values: list, rng, share_range=spec.DUPLICATE_SHARE) -> list:
    """Force a 20-50 % duplicate share by copying earlier values into later slots."""
    n = len(values)
    if n < 2:
        return values
    target = int(round(n * rng.uniform(*share_range)))
    target = max(1, min(n - 1, target))
    out = list(values)
    for i in range(n - target, n):
        out[i] = out[rng.randrange(0, i)]
    return out


def _apply_group_sizes(values: list, rng) -> list:
    """Make group sizes hit 1, 2 and >= 3 (for program.Owner -- non-key column only)."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    out[0] = 'g_single'
    out[1] = out[2] = 'g_pair'
    out[3] = out[4] = out[5] = 'g_triple'
    for i in range(6, n):
        out[i] = rng.choice(['g_single', 'g_pair', 'g_triple'])
    return out


def _apply_ties(channel_cols: dict, rng) -> None:
    """Plant a tie at rank 1 on rating_in_percent * share_in_percent after clamping."""
    rating = channel_cols.get('Rating_in_percent')
    share = channel_cols.get('Share_in_percent')
    if not rating or not share or len(rating) < 2:
        return
    lo, hi = spec.PERCENT_RANGE
    idx = [i for i in range(len(rating)) if rating[i] is not None and share[i] is not None]
    if len(idx) < 2:
        return
    prods = {i: round(float(rating[i]) * float(share[i]), 6) for i in idx}
    best_i = max(idx, key=lambda i: prods[i])
    target = prods[best_i]
    if target <= 0:
        target = round(max(0.01, target + 0.01), 6)
        if rating[best_i]:
            share[best_i] = max(lo, min(hi, round(target / float(rating[best_i]), 4)))
    for j in idx:
        if j == best_i:
            continue
        r = float(rating[j])
        if r <= 0:
            continue
        cand = round(target / r, 4)
        if lo <= cand <= hi:
            if round(r * cand, 6) == target:
                share[j] = cand
                break
    prods = {i: round(float(rating[i]) * float(share[i]), 6) for i in idx}
    mx = max(prods.values())
    if prods.get(best_i) != mx:
        for i in idx:
            if i in (best_i,) or prods[i] == target:
                continue
            r = float(rating[i])
            if r <= 0:
                continue
            share[i] = max(lo, min(hi, round((target * 0.5) / r, 4)))


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _plant_nulls(cols: dict, table: str, rng) -> None:
    """Ensure >=1 NULL in every nullable column that is targeted (share ~ compact share)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    for (t, cname) in spec.NULL_TARGETS:
        if t != table or cname not in cols:
            continue
        if any(v is None for v in cols[cname]):
            continue
        cols[cname][rng.randrange(n)] = None


def _repair_fk(col_values: list, parent_values: list, rng) -> list:
    """FK values must reference an existing final parent value (or be NULL)."""
    parent_set = set(parent_values)
    if not parent_set:
        return [None] * len(col_values)
    out = []
    for v in col_values:
        if v is None:
            out.append(None)
        elif v in parent_set:
            out.append(v)
        else:
            out.append(rng.choice(parent_values))
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification."""
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
        inst[t] = cols

    if 'program' in inst and 'Program_ID' in inst['program']:
        base = _max_int(schema, 'program', 'Program_ID')
        n = len(inst['program']['Program_ID'])
        inst['program']['Program_ID'] = [base + 1 + i for i in range(n)]
    if 'channel' in inst and 'Channel_ID' in inst['channel']:
        base = _max_int(schema, 'channel', 'Channel_ID')
        n = len(inst['channel']['Channel_ID'])
        inst['channel']['Channel_ID'] = [base + 1 + i for i in range(n)]

    parent_pool = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.pk_pos > 0:
                comp = [v for v in schema.original_values.get((t, cm.name), []) if v is not None]
                parent_pool[(t, cm.name)] = comp + list(inst.get(t, {}).get(cm.name, []))

    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = inst[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = parent_pool.get((pt, pc), [])
            if pv:
                vals = [rng.choice(pv) for _ in range(n)]
            else:
                vals = [None] * n
            cols[cm.name] = _repair_fk(vals, pv, rng)

    for t in order:
        tm = schema.tables[t]
        if tm.primary_key and inst[t]:
            inst[t] = sample_fresh_primary_keys(tm, inst[t])

    for t in order:
        _plant_nulls(inst[t], t, rng)

    _apply_spec(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}


def _apply_spec(schema, inst: dict, rng) -> None:
    """Apply per-column exceptions and semantic rules on the in-memory values."""

    for col in ('Name', 'Origin'):
        if 'program' in inst and col in inst['program']:
            inst['program'][col] = _apply_duplicate_share(inst['program'][col], rng)
    if 'program' in inst and 'Owner' in inst['program']:
        vals = _apply_duplicate_share(inst['program']['Owner'], rng)
        inst['program']['Owner'] = _apply_group_sizes(vals, rng)

    if 'program' in inst and 'Launch' in inst['program']:
        lo, hi = spec.LAUNCH_RANGE
        vals = []
        for v in inst['program']['Launch']:
            if v is None:
                vals.append(None)
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = rng.uniform(lo, hi)
            vals.append(round(_clamp(f, lo, hi), 2))
        nonnull = [i for i, v in enumerate(vals) if v is not None]
        if len(nonnull) >= 2 and len({vals[i] for i in nonnull}) < 2:
            vals[nonnull[1]] = round(_clamp(vals[nonnull[0]] + 1.0, lo, hi), 2)
        inst['program']['Launch'] = vals

    for col in ('Name', 'Owner'):
        if 'channel' in inst and col in inst['channel']:
            inst['channel'][col] = _apply_duplicate_share(inst['channel'][col], rng)
    for col in ('Share_in_percent', 'Rating_in_percent'):
        if 'channel' in inst and col in inst['channel']:
            lo, hi = spec.PERCENT_RANGE
            inst['channel'][col] = [
                None if v is None else round(_clamp(float(v), lo, hi), 2)
                for v in inst['channel'][col]]
    _apply_ties(inst.get('channel', {}), rng)

    if 'broadcast' in inst and 'Time_of_day' in inst['broadcast']:
        n = len(inst['broadcast']['Time_of_day'])
        cur = inst['broadcast']['Time_of_day']
        inst['broadcast']['Time_of_day'] = [
            None if cur[i] is None else rng.choice(spec.TIME_OF_DAY_VALUES) for i in range(n)]

    if 'broadcast_share' in inst and 'Date' in inst['broadcast_share']:
        n = len(inst['broadcast_share']['Date'])
        cur = inst['broadcast_share']['Date']
        inst['broadcast_share']['Date'] = [
            None if cur[i] is None else rng.choice(spec.DATE_POOL) for i in range(n)]
    if 'broadcast_share' in inst and 'Share_in_percent' in inst['broadcast_share']:
        lo, hi = spec.PERCENT_RANGE
        inst['broadcast_share']['Share_in_percent'] = [
            None if v is None else round(_clamp(float(v), lo, hi), 2)
            for v in inst['broadcast_share']['Share_in_percent']]
