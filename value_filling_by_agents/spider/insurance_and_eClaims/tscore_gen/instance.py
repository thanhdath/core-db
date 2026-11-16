"""Random instance construction + spec-driven post-processing."""
import datetime as dt

from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
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
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Union of compact parent values and generated parent values actually present."""
    pool = list(schema.original_values.get((pt, pc)) or [])
    gen = instance.get(pt, {}).get(pc) or []
    pool.extend(gen)
    out, seen = [], set()
    for v in pool:
        if v is None:
            continue
        key = (type(v).__name__, v)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   exclude: dict = None) -> dict:
    """FK child columns draw from parent values actually present (compact + generated)."""
    out = {}
    exclude = exclude or {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        ex = exclude.get((table, cm.name))
        if ex:
            pv = [v for v in pv if v not in ex]
        if not pv:
            pv = list(schema.original_values.get((pt, pc)) or [])
            pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _spec_sizes(schema, rng) -> dict:
    """Per-instance *total* table sizes around the specification's table_sizes_per_instance."""
    sizes = {}
    for t in schema.tables:
        base = spec.BASE_SIZES.get(t, 15)
        lo = max(0, base - 5)
        hi = min(230, base + 5)
        sizes[t] = rng.randint(lo, hi)
    return sizes


def _apply_duplicate_share(values: list, rng) -> list:
    """Force a duplicate share in [DUP_SHARE_LO, DUP_SHARE_HI] by repeating existing values."""
    n = len(values)
    if n < 2:
        return values
    target = int(n * rng.uniform(spec.DUP_SHARE_LO, spec.DUP_SHARE_HI))
    target = max(1, min(n - 1, target))
    out = list(values)
    for i in range(target):
        j = rng.randrange(n)
        k = rng.randrange(n)
        out[j] = out[k]
    return out


def _apply_group_sizes(values: list, rng) -> list:
    """Ensure at least one group of size 1, one of size 2 and one of size >= 3."""
    n = len(values)
    if n < 6:
        return values
    out = list(values)
    distinct = list(dict.fromkeys(out))
    if len(distinct) < 3:
        return out
    g1, g2, g3 = rng.sample(distinct, 3)
    idx = [i for i, v in enumerate(out) if v == g1]
    for i in idx[1:]:
        out[i] = rng.choice(distinct)
    idx = [i for i, v in enumerate(out) if v == g2]
    if len(idx) < 2:
        cand = [i for i, v in enumerate(out) if v != g2 and v != g1]
        if cand:
            out[rng.choice(cand)] = g2
    elif len(idx) > 2:
        for i in idx[2:]:
            out[i] = rng.choice(distinct)
    idx = [i for i, v in enumerate(out) if v == g3]
    need = 3 - len(idx)
    if need > 0:
        cand = [i for i, v in enumerate(out) if v != g3 and v != g1]
        rng.shuffle(cand)
        for i in cand[:need]:
            out[i] = g3
    return out


def _plant_nulls(columns: dict, table: str, n: int, rng, null_shares: dict) -> None:
    """NULL rule: at least one NULL per nullable column, share follows the compact DB."""
    for cm_name in list(columns.keys()):
        key = (table, cm_name)
        if key not in spec.NULL_TARGETS:
            continue
        vals = columns[cm_name]
        if not vals:
            continue
        share = null_shares.get(key)
        if share is None or share <= 0.0:
            share = rng.uniform(spec.NULL_SHARE_FALLBACK_LO, spec.NULL_SHARE_FALLBACK_HI)
        k = max(1, int(round(len(vals) * share)))
        k = min(k, len(vals))
        idx = rng.sample(range(len(vals)), k)
        for i in idx:
            vals[i] = None


def _enforce_date_order(columns: dict, start_col: str, end_col: str) -> None:
    """Start_Date <= End_Date (NULL operands are not constrained)."""
    if start_col not in columns or end_col not in columns:
        return
    s, e = columns[start_col], columns[end_col]
    for i in range(len(s)):
        if s[i] is None or e[i] is None:
            continue
        try:
            ds = dt.datetime.strptime(str(s[i]), spec.DATE_FMT)
            de = dt.datetime.strptime(str(e[i]), spec.DATE_FMT)
        except ValueError:
            continue
        if ds > de:
            s[i], e[i] = e[i], s[i]


def _enforce_non_negative(columns: dict, col: str) -> None:
    """Amount >= 0 (NULL operands are not constrained)."""
    if col not in columns:
        return
    vals = columns[col]
    for i, v in enumerate(vals):
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f < 0:
            vals[i] = abs(f)


def _ensure_distinct_values(columns: dict, table: str, col: str, rng) -> None:
    """>= 2 distinct non-NULL values (rows_with_different_values); NULL-aware, date-aware."""
    if col not in columns:
        return
    vals = columns[col]
    non_null = [v for v in vals if v is not None]
    if len(non_null) < 2:
        return
    if len(set(non_null)) >= 2:
        return
    v = non_null[0]
    if isinstance(v, str) and table == 'Policies' and col == 'Start_Date':
        try:
            d = dt.datetime.strptime(v, spec.DATE_FMT)
            d2 = d + dt.timedelta(seconds=rng.randint(1, 3600))
            if d2 > spec.DATE_HI:
                d2 = d - dt.timedelta(seconds=rng.randint(1, 3600))
            new_v = d2.strftime(spec.DATE_FMT)
        except ValueError:
            new_v = v + 'x'
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        new_v = v + 1
    elif isinstance(v, str):
        new_v = v + 'x'
    else:
        new_v = str(v) + 'x'
    for i, x in enumerate(vals):
        if x is None:
            continue
        vals[i] = new_v
        break


def _reserve_childless_pk_values(instance: dict, schema, rng) -> dict:
    """Reserve at least one parent PK value per spec pair and return exclusion sets for child FKs."""
    exclude: dict = {}
    for pt, pc, ct, cc in spec.PARENT_WITHOUT_CHILDREN:
        if pt not in instance or ct not in instance:
            continue
        pvals = [v for v in (instance.get(pt, {}).get(pc) or []) if v is not None]
        compact = [v for v in (schema.original_values.get((pt, pc)) or []) if v is not None]
        all_parents = list(dict.fromkeys(compact + pvals))
        if not all_parents:
            continue
        reserved = rng.choice(all_parents)
        exclude.setdefault((ct, cc), set()).add(reserved)
    return exclude


def _compact_null_shares(schema) -> dict:
    """Observed NULL share per nullable column in the compact database."""
    shares = {}
    for key in spec.NULL_TARGETS:
        vals = schema.original_values.get(key) or []
        if not vals:
            continue
        shares[key] = sum(1 for v in vals if v is None) / float(len(vals))
    return shares


def _pk_start(schema, table: str, pk_cols: list) -> int:
    """First generated PK value: MAX(existing PK)+1 (single-column integer PKs only)."""
    if len(pk_cols) != 1:
        return 1
    vals = schema.original_values.get((table, pk_cols[0])) or []
    ints = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
    return (max(ints) + 1) if ints else 1


def _is_pk(table_meta, col: str) -> bool:
    return col in (table_meta.primary_key or [])


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance with spec-driven post-processing (Python by construction)."""
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
        size = _spec_sizes(schema, rng)
    null_shares = _compact_null_shares(schema)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        target = int(size.get(t, 0))
        compact_n = schema.original_sizes.get(t, 0)
        n = max(0, target - compact_n)
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        if tm.primary_key and len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            start = _pk_start(schema, t, tm.primary_key)
            cols[tm.primary_key[0]] = [start + i for i in range(n)]

        for (tt, cc) in spec.DISTINCT_COLUMNS:
            if tt == t and cc in cols and not _is_pk(tm, cc):
                cols[cc] = _apply_duplicate_share(cols[cc], rng)
        for (tt, cc) in spec.GROUP_SIZE_COLUMNS:
            if tt == t and cc in cols and not _is_pk(tm, cc):
                cols[cc] = _apply_group_sizes(cols[cc], rng)

        inst[t] = cols
        exclude = _reserve_childless_pk_values(inst, schema, rng) if any(
            pt == t for pt, _, ct, _ in spec.PARENT_WITHOUT_CHILDREN) else {}
        child_exclude = {k: v for k, v in exclude.items() if k[0] == t}
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng, exclude=child_exclude)
        cols.update(fk_cols)
        cols = {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols}
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and cm.name in cols and pc in cols:
                final = [v for v in cols[pc] if v is not None]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols

    for t in order:
        cols = inst[t]
        n = len(next(iter(cols.values()))) if cols else 0
        if t == 'Policies':
            _enforce_date_order(cols, 'Start_Date', 'End_Date')
        if t == 'Claim_Headers':
            _enforce_date_order(cols, 'Date_of_Claim', 'Date_of_Settlement')
            _enforce_non_negative(cols, 'Amount_Claimed')
            _enforce_non_negative(cols, 'Amount_Piad')
        _plant_nulls(cols, t, n, rng, null_shares)
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            if pt == t:
                continue
            pool = _parent_pool(inst, schema, pt, pc)
            if not pool:
                continue
            pset = set(pool)
            vals = cols.get(cm.name)
            if vals is None:
                continue
            fixed = []
            for v in vals:
                if v is None or v in pset:
                    fixed.append(v)
                else:
                    fixed.append(rng.choice(pool))
            cols[cm.name] = fixed
        for (tt, cc) in spec.DIFFERENT_VALUE_COLUMNS:
            if tt == t and cc in cols:
                _ensure_distinct_values(cols, t, cc, rng)
        if t == 'Policies':
            _enforce_date_order(cols, 'Start_Date', 'End_Date')
        if t == 'Claim_Headers':
            _enforce_date_order(cols, 'Date_of_Claim', 'Date_of_Settlement')

    return {t: inst[t] for t in schema.tables}
