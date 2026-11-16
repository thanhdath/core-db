"""Random instance construction (fuzz/fuzz.py:83-196) with the specification's rules by construction:"""
from .schema import column_bounds
from .values import _init_sampler, variants_of, hexify

_DEFAULT_NULL_SHARE = 0.10


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190); no NULL primary keys."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if any(x is None for x in k) or k in seen:
            continue
        seen.add(k)
        keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v is None or v not in seen:
                    if v is not None:
                        seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_values(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated parent keys (no NULLs)."""
    compact = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    gen = [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return gen if gen else compact


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict,
                                   null_shares: dict, child_null_share: float = 0.15) -> dict:
    """FK child columns draw from the parent's rows with replacement; unmatched/parent-less share -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(instance, schema, pt, pc)
        share = null_shares.get(key)
        null_frac = share if share is not None else child_null_share
        n_null = max(1, int(round(n * null_frac)))
        vals = [rng.choice(pv) for _ in range(n - n_null)] if pv else []
        vals += [None] * (n - len(vals))
        rng.shuffle(vals)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Sizes per instance: spec table_sizes_per_instance with +-25% variation, else rand_lin / level x4."""
    tgt = ((spec or {}).get('table_sizes_per_instance') or {}) if spec else {}
    sizes = {}
    generic = rng.random() < 0.5
    s_lvl = 1 + 30 * rng.random()
    for lvl in schema.table_order:
        for t in lvl:
            if t in tgt:
                base = int(tgt[t])
                base = max(0, int(base * rng.uniform(0.75, 1.25)))
                sizes[t] = min(base, 2500)
            elif generic:
                sizes[t] = int(30 * rng.random() + int(rng.random() * 200))
            else:
                sizes[t] = int(min(s_lvl, 2500))
        s_lvl *= 4
    return sizes


def _null_shares(schema, spec: dict, rng) -> dict:
    """Compact NULL share per nullable column, clamped to [5%, 30%] for COUNT targets, at least one NULL row."""
    shares: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            if cm.notnull or cm.pk_pos > 0:
                continue
            ov = schema.original_values.get(key) or []
            obs = (sum(1 for v in ov if v is None) / len(ov)) if ov else _DEFAULT_NULL_SHARE
            lo, hi = _null_window(spec, t, cm.name)
            shares[key] = min(hi, max(lo, obs))
    return shares


def _null_window(spec: dict, table: str, column: str) -> tuple:
    """NULL share window for a column from the spec (5-30% for COUNT columns, default 10-20%)."""
    for e in ((spec or {}).get('per_column_exceptions') or []):
        parts = str(e.get('column', '')).split('.')
        if len(parts) == 2 and parts[0].lower() == table.lower() and parts[1].lower() == column.lower():
            if e.get('pattern') == 'null_in_count_column':
                s = str((e.get('targets') or {}).get('null_share', '5-30%'))
                nums = [int(x) for x in s.replace('%', ' ').replace('-', ' ').split() if x.isdigit()]
                if len(nums) >= 2:
                    return nums[0] / 100.0, nums[1] / 100.0
                return 0.05, 0.30
    return 0.05, 0.20


def _spec_kw(spec: dict, schema, table: str, column: str, rng) -> dict:
    """Sampler keyword arguments from per-column exceptions: boundary/tag values, duplicate share, bounds."""
    kw: dict = {'boundary': (), 'dup_share': 0.0}
    exp = [e for e in ((spec or {}).get('per_column_exceptions') or [])
           if len(str(e.get('column', '')).split('.')) == 2
           and str(e.get('column')).split('.')[0].lower() == table.lower()
           and str(e.get('column')).split('.')[1].lower() == column.lower()]
    bnd: list = []
    for e in exp:
        tg = e.get('targets') or {}
        pat = e.get('pattern')
        if pat in ('like_near_variant', 'comparison_boundary'):
            for v in tg.get('literals') or []:
                if isinstance(v, str):
                    bnd.append(v)
                    bnd.append(v.replace('%', ''))
            for v in tg.get('values') or []:
                if isinstance(v, str):
                    bnd.append(v)
            for v in tg.get('variants') or []:
                if isinstance(v, str):
                    bnd.append(v)
        if pat == 'duplicates_for_distinct':
            s = str(tg.get('duplicate_share', '20-50%')).replace('%', ' ').replace('-', ' ').split()
            nums = [int(x) for x in s if x.isdigit()]
            kw['dup_share'] = rng.uniform(nums[0] / 100.0, nums[1] / 100.0) if len(nums) >= 2 else rng.uniform(0.2, 0.5)
    kw['boundary'] = tuple(dict.fromkeys(bnd))
    b = column_bounds(schema, table, column, spec)
    if b['lo'] is not None and 'int' in (schema.tables[table].columns[[c.name for c in schema.tables[table].columns].index(column)].type_str or '').lower():
        kw['lo'], kw['hi'] = b['lo'], b['hi']
    return kw


def _fresh_pk(schema, table: str, column: str, used: set, rng) -> object:
    """A key value fresh against compact and generated PK keys (integers) or a synthetic text key."""
    cm = next(c for c in schema.tables[table].columns if c.name == column)
    ov = [v for v in (schema.original_values.get((table, column)) or []) if isinstance(v, int)]
    t = (cm.type_str or '').lower()
    if not ov or 'char' in t or 'text' in t:
        while True:
            v = hexify(table, column, str(rng.random()), str(len(used)))
            if v not in used:
                return v
    top = max(ov) + 1
    while top in used:
        top += 1
    used.add(top)
    return top


def _plan_ties(schema, table: str, artist_col: str, sizes: dict, rng) -> dict:
    """Group sizes for the ORDER/LIMIT ties: repeat a size across >= 2 groups at rank 1 and rank ~100."""
    return {'tie_size': int(sizes.get(table, 0) // 3) + 1}


def build_random_instance(schema, literal_pool: dict, spec, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification by construction."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    null_shares = _null_shares(schema, spec, rng)
    sizes = choose_table_sizes(schema, spec, rng) if False else choose_table_sizes(schema, rng, spec)
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                kw = _spec_kw(spec, schema, t, cm.name, rng)
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec_kw=kw)
    inst: dict = {}
    tie_info = None
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        if tie_info is None and any(c.name.lower() == 'artist' for c in tm.columns):
            tie_info = _plan_ties(schema, t, 'artist', sizes, rng)
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        if tie_info and any(c.name.lower() == 'artist' for c in tm.columns):
            _plant_ties(tm, cols, tie_info, rng)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec, null_shares))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        _apply_null_rule(tm, cols, null_shares, (t,), rng)
        _refresh_fresh_pks(schema, t, tm, cols, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}


def _plant_ties(tm, cols: dict, tie_info: dict, rng) -> None:
    """Repeat the artist value of the first row across rows so group sizes tie at ranks 1 and ~100."""
    ac = next((c.name for c in tm.columns if c.name.lower() == 'artist'), None)
    if not ac or not cols.get(ac):
        return
    vals = cols[ac]
    n = len(vals)
    tie = tie_info['tie_size']
    if n >= 2 * tie + 2:
        top = vals[0]
        for i in range(tie, 2 * tie):
            vals[i] = top
        second = vals[2 * tie]
        for i in range(3 * tie, min(n, 4 * tie)):
            vals[i] = second


def _apply_null_rule(tm, cols: dict, null_shares: dict, tables: tuple, rng) -> None:
    """Each nullable non-FK column gets its NULL share (>= 1 NULL row) unless already NULL-bearing."""
    for cm in tm.columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
            continue
        share = null_shares.get((tm.name, cm.name), _DEFAULT_NULL_SHARE)
        vals = cols[cm.name]
        n = len(vals)
        if n == 0:
            continue
        n_null = max(1, int(round(n * share)))
        have = sum(1 for v in vals if v is None)
        need = max(0, n_null - have)
        if need:
            idxs = rng.sample(range(n), need)
            for i in idxs:
                vals[i] = None


def _refresh_fresh_pks(schema, table: str, tm, cols: dict, rng) -> None:
    """Generated PK values fresh against compact rows (and the collected generated rows so far)."""
    fk_cols = {c for (t, c) in schema.fks if t == table}
    for cm in tm.columns:
        if cm.pk_pos <= 0 or cm.name in fk_cols or cm.name not in cols:
            continue
        compact = {v for v in (schema.original_values.get((table, cm.name)) or []) if v is not None}
        used = set(compact)
        vals = cols[cm.name]
        for i, v in enumerate(vals):
            if v is None or v in used:
                vals[i] = _fresh_pk(schema, table, cm.name, used, rng)
            else:
                used.add(v)
