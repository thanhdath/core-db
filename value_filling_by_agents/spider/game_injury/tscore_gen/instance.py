"""Random instance construction (fuzz/fuzz.py:83-196)."""
from .values import _init_sampler, ENUM_POOLS, PLAYER_BOUNDARY

SPEC_SIZES = {'stadium': 13, 'game': 20, 'injury_accident': 15}

_TYPE_DEFAULTS = {
    'int': 0, 'integer': 0, 'real': 0.0, 'float': 0.0, 'double': 0.0, 'numeric': 0.0,
    'text': '', 'varchar': '', 'char': '', 'blob': b'',
}


def _default_for(cm):
    t = (cm.type_str or '').lower()
    for k, v in _TYPE_DEFAULTS.items():
        if k in t:
            return v
    return None


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _equal_lengths(columns: dict) -> dict:
    """Guarantee every column of a table has the same length (never append/truncate silently)."""
    if not columns:
        return columns
    n = min(len(v) for v in columns.values())
    return {c: v[:n] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set = None) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact key), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    existing_keys = existing_keys or set()
    n = min(len(v) for v in columns.values()) if columns else 0
    seen, keep = set(existing_keys), []
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
                                   null_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's compact + generated values with replacement."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        for row in schema.original_rows.get(pt, []):
            try:
                idx = [c.name for c in schema.tables[pt].columns].index(pc)
            except ValueError:
                idx = None
            if idx is not None and row[idx] is not None:
                pv.append(row[idx])
        pv = [v for v in pv if v is not None]
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = []
        for _ in range(n):
            if null_share > 0 and rng.random() < null_share:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with a small random variation (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = SPEC_SIZES.get(t)
        if base is None:
            base = int(30 * rng.random() + int(rng.random() * 200))
        delta = rng.randint(-2, 2)
        sizes[t] = max(0, min(230, base + delta))
    return sizes


def _compact_keys(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    names = [c.name for c in tm.columns]
    idxs = [names.index(c) for c in tm.primary_key]
    return {tuple(row[i] for i in idxs) for row in schema.original_rows.get(table, [])}


def _next_pk_start(schema, table: str) -> int:
    """Fresh integer PK start: max compact PK + 1 (or 1)."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return 1
    names = [c.name for c in tm.columns]
    idx = names.index(tm.primary_key[0])
    vals = [row[idx] for row in schema.original_rows.get(table, []) if isinstance(row[idx], int)]
    return (max(vals) + 1) if vals else 1


def _shape_groups_and_dups(values: list, rng) -> list:
    """Single-pass shaping that satisfies group_sizes {1,2,>=3} AND a 20-50% duplicate share."""
    if not values:
        return values
    n = len(values)
    pool = list(values)
    rng.shuffle(pool)
    seeds = []
    for v in pool:
        if v not in seeds:
            seeds.append(v)
        if len(seeds) >= 5:
            break
    if not seeds:
        seeds = [pool[0]]
    groups = []
    gs = [1, 2, 3]
    i = 0
    while sum(len(g) for g in groups) < n and i < 1000:
        size = gs[i % len(gs)]
        seed = seeds[i % len(seeds)]
        groups.append([seed] * size)
        i += 1
    out = [v for g in groups for v in g]
    out = out[:n]
    all_base = [v for g in groups for v in g]
    while len(out) < n:
        out.append(rng.choice(all_base) if all_base else rng.choice(pool))
    n_dup = sum(1 for _ in range(n)) - len({id(v) for v in out})
    target = rng.uniform(0.2, 0.5)
    want_dup = int(round(n * target))
    distinct_vals = list(dict.fromkeys(out))
    if distinct_vals:
        if want_dup < 1:
            want_dup = 1
        for k in range(want_dup):
            pos = n - 1 - k
            if pos < 0:
                break
            out[pos] = rng.choice(distinct_vals)
    rng.shuffle(out)
    return out


def _apply_group_sizes(values: list, rng, sizes=(1, 2, 3)) -> list:
    """Reshape a value list so that group sizes 1, 2 and >=3 all occur (spec group_sizes)."""
    if not values:
        return values
    out = []
    pool = list(values)
    rng.shuffle(pool)
    i = 0
    for gs in sizes:
        if i >= len(pool):
            break
        v = pool[i]
        out.extend([v] * gs)
        i += 1
    while i < len(pool):
        out.append(pool[i])
        i += 1
    return out


def _apply_duplicate_share(values: list, rng, share=(0.2, 0.5)) -> list:
    """Ensure duplicate share in [20 %, 50 %] for DISTINCT-target columns."""
    if len(values) < 2:
        return values
    target = rng.uniform(*share)
    n_dup = max(1, int(round(len(values) * target)))
    n_dup = min(n_dup, len(values) - 1)
    distinct = list(dict.fromkeys(values))
    if not distinct:
        return values
    out = list(values)
    for k in range(n_dup):
        pos = len(out) - 1 - k
        if pos < 0:
            break
        out[pos] = rng.choice(distinct)
    rng.shuffle(out)
    return out


def _apply_aggregate_boundary(values: list, rng) -> list:
    """Ensure groups with counts 1, 2 and >=3 (spec aggregate_boundary)."""
    return _apply_group_sizes(values, rng, sizes=(1, 2, 3))


def _set_positions(values: list, lits: list) -> list:
    """Overwrite the first positions with the given literals; never changes length."""
    out = list(values)
    for k, lit in enumerate(lits):
        if k < len(out):
            out[k] = lit
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows over the compact DB."""
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
        names = [cm.name for cm in tm.columns]
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = [samplers[(t, cm.name)].sample() for _ in range(n)]
            else:
                cols[cm.name] = [_default_for(cm)] * n
        cols = {cname: (cols.get(cname) if len(cols.get(cname, [])) == n
                        else (list(cols.get(cname, [])) + [None] * n)[:n]) for cname in names}
        fk_null = {}
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks and not cm.notnull and cm.pk_pos == 0:
                share = schema.null_share.get(key, 0.0)
                share = min(0.30, max(0.05, share if share > 0 else 0.10))
                fk_null[cm.name] = share
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng,
                                                 null_share=max(fk_null.values()) if fk_null else 0.0)
        for cname, vals in fk_cols.items():
            if cname in cols and len(vals) == n:
                cols[cname] = vals
        for cm in tm.columns:
            key = (t, cm.name)
            if cm.name in fk_cols and cm.name in fk_null:
                vals = cols[cm.name]
                share = fk_null[cm.name]
                for i in range(len(vals)):
                    if vals[i] is not None and rng.random() < share:
                        vals[i] = None
        cols = _equal_lengths(cols)
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            if pk in cols and all(isinstance(v, int) for v in cols[pk] if v is not None):
                start = _next_pk_start(schema, t)
                cols[pk] = list(range(start, start + len(cols[pk])))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols and cm.name in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = sample_fresh_primary_keys(tm, cols, _compact_keys(schema, t))
        cols = drop_unique_duplicates(tm, cols)
        cols = _equal_lengths(cols)
        inst[t] = {}
        inst[t].update(cols)
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            if cm.name not in inst[t] or pc not in inst.get(pt, {}):
                continue
            parent_vals = [v for v in inst[pt].get(pc, []) if v is not None]
            if not parent_vals:
                continue
            ps = set(parent_vals)
            vals = inst[t][cm.name]
            for i, v in enumerate(vals):
                if v is not None and v not in ps:
                    vals[i] = rng.choice(parent_vals)
    _apply_spec_rules(schema, inst, rng)
    inst = {t: _equal_lengths(v) for t, v in inst.items()}
    return {t: inst.get(t, {}) for t in schema.tables}


def _apply_spec_rules(schema, inst: dict, rng) -> None:
    """Apply the specification's semantic rules and group/duplicate targets in memory."""
    st = inst.get('stadium')
    if st and 'Home_Games' in st:
        hg = st['Home_Games']
        n = len(hg)
        if n:
            base_hg = 8
            for i in range(n):
                if i < 2:
                    hg[i] = rng.randint(1, 12)
                elif hg[i] is None or hg[i] <= 0:
                    hg[i] = rng.randint(1, 12)
                elif rng.random() < 0.5:
                    hg[i] = rng.randint(1, 12)
        if 'Average_Attendance' in st and 'Total_Attendance' in st:
            avg, tot = st['Average_Attendance'], st['Total_Attendance']
            for i in range(min(len(avg), len(tot), len(hg))):
                if avg[i] is not None and hg[i] is not None:
                    tot[i] = float(avg[i]) * float(hg[i]) + rng.randint(-4, 4)
        for c in ('Average_Attendance', 'Total_Attendance', 'Capacity_Percentage'):
            if c in st:
                st[c] = [abs(v) if v is not None else v for v in st[c]]
        if 'name' in st:
            st['name'] = _shape_groups_and_dups(st['name'], rng)
        if 'id' in st:
            st['id'] = _apply_group_sizes(st['id'], rng)

    gm = inst.get('game')
    if gm:
        if 'Season' in gm:
            gm['Season'] = [min(2030, max(2000, v)) if v is not None else v for v in gm['Season']]
            gm['Season'] = _apply_duplicate_share(gm['Season'], rng)
        for c, pool in (('Competition', ENUM_POOLS['competition']),
                        ('Home_team', ENUM_POOLS['home_team']),
                        ('Away_team', ENUM_POOLS['away_team'])):
            if c in gm:
                gm[c] = [rng.choice(pool) if v is None or v not in pool else v for v in gm[c]]
        if 'Date' in gm:
            gm['Date'] = _shape_groups_and_dups(gm['Date'], rng)
        if 'Score' in gm:
            gm['Score'] = _shape_groups_and_dups(gm['Score'], rng)

    ia = inst.get('injury_accident')
    if ia:
        if 'Source' in ia:
            ia['Source'] = [rng.choice(ENUM_POOLS['source']) for _ in ia['Source']]
            ia['Source'] = _apply_duplicate_share(ia['Source'], rng)
        if 'Injury' in ia:
            ia['Injury'] = _apply_duplicate_share(ia['Injury'], rng)
        if 'Player' in ia:
            ia['Player'] = _set_positions(ia['Player'], PLAYER_BOUNDARY)
            ia['Player'] = _apply_aggregate_boundary(ia['Player'], rng)
        if 'id' in ia:
            pass
