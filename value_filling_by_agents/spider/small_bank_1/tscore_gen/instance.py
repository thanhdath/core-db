"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
from . import spec
from .values import _init_sampler


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 30 + rng.randrange(0, 200)
        jitter = rng.randrange(-2, 3)
        sizes[t] = max(0, min(230, base + jitter))
    return sizes


def _fresh_pk_values(schema, table: str, n: int, rng) -> list:
    """Sequential integers starting after the compact maximum (BIGINT_pk)."""
    tm = schema.tables[table]
    if not tm.primary_key or len(tm.primary_key) != 1:
        return [rng.randrange(1, 10 ** 6) for _ in range(n)]
    pk = tm.primary_key[0]
    existing = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 1
    return list(range(start, start + n))


def _plant_name_values(n: int, rng) -> list:
    """Forced ACCOUNTS.name values: boundary, LIKE variants, duplicates."""
    forced = []
    forced += spec.NAME_BOUNDARY[:]
    forced += spec.LIKE_VARIANTS[:]
    share = rng.uniform(*spec.DUP_SHARE)
    n_dup = max(1, int(round(share * n)))
    pool = spec.SURNAMES[:]
    rng.shuffle(pool)
    for k in range(n_dup):
        forced.append(pool[k % len(pool)])
    return forced


def _plant_balance_values(n: int, rng, tie_value=None) -> list:
    """Forced balance values: at least two rows tie at MIN and at rank 1."""
    forced = []
    if tie_value is None:
        tie_value = 0.0
    forced += [tie_value, tie_value]
    return forced


def _apply_forced_by_index(cols: dict, forced: list) -> None:
    """Write forced values into the first slots of a column (deterministic)."""
    if not forced:
        return
    for i, v in enumerate(forced):
        if i < len(cols):
            cols[i] = v


def _plant_custid_boundary(inst: dict, schema, rng) -> None:
    """Ensure generated rows contain accounts.custid = k, checking.custid = k+1 and an equality pair accounts.custid
    = checking.custid = k+2, for a fresh k."""
    if 'ACCOUNTS' not in inst or 'CHECKING' not in inst:
        return
    acc = inst['ACCOUNTS'].get('custid')
    chk = inst['CHECKING'].get('custid')
    if not acc or not chk:
        return
    k = acc[0]
    if not isinstance(k, int):
        return
    for i, v in enumerate((k, k + 1, k + 2)):
        if i < len(acc):
            acc[i] = v
    for i, v in enumerate((k + 1, k + 2)):
        if i < len(chk):
            chk[i] = v


def _plant_joined_sum_tie(inst: dict, schema, rng) -> None:
    """Force at least two shared custids to carry planted tie_check/tie_save."""
    if 'CHECKING' not in inst or 'SAVINGS' not in inst:
        return
    chk = inst['CHECKING']
    sav = inst['SAVINGS']
    if 'custid' not in chk or 'custid' not in sav:
        return
    chk_ids = chk['custid']
    sav_ids = sav['custid']
    shared = [c for c in chk_ids if c in set(sav_ids)]
    if len(shared) < 2:
        return
    tie_check = 0.0
    tie_save = 0.0
    for cid in shared[:2]:
        for i, c in enumerate(chk_ids):
            if c == cid:
                chk['balance'][i] = tie_check
                break
        for i, c in enumerate(sav_ids):
            if c == cid:
                sav['balance'][i] = tie_save
                break


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    forced: dict = {}
    n_accounts = int(size.get('ACCOUNTS', 0))
    n_checking = int(size.get('CHECKING', 0))
    n_savings = int(size.get('SAVINGS', 0))
    if 'ACCOUNTS' in schema.tables:
        forced[('ACCOUNTS', 'name')] = _plant_name_values(n_accounts, rng)
    tie_check = 0.0
    tie_save = 0.0
    if 'CHECKING' in schema.tables:
        forced[('CHECKING', 'balance')] = _plant_balance_values(n_checking, rng, tie_check)
    if 'SAVINGS' in schema.tables:
        forced[('SAVINGS', 'balance')] = _plant_balance_values(n_savings, rng, tie_save)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), forced=forced.get((t, cm.name)))

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols:
                cols[pk] = _fresh_pk_values(schema, t, n, rng)
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols

    for (t, c), fv in forced.items():
        if t in inst and c in inst[t]:
            _apply_forced_by_index(inst[t][c], fv)

    _plant_custid_boundary(inst, schema, rng)
    _plant_joined_sum_tie(inst, schema, rng)

    return {t: inst[t] for t in schema.tables}
