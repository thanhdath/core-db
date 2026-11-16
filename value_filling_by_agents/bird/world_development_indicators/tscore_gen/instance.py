"""Random instance construction (fuzz/fuzz.py:83-196), adapted to append to a compact database."""
import re

from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen and all(v is not None for v in k):
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


def _domain_for(spec: dict, key: tuple) -> dict:
    """Per-column specification domain (enum / range / like / boundary / like_prefix)."""
    d = {}
    if key in spec['enums']:
        d['enum'] = spec['enums'][key]
    if key in spec['ranges']:
        d['range'] = spec['ranges'][key]
    if key in spec['like']:
        d['like'] = [v for v in spec['enums'].get(key, [])]
    if key in spec['boundary']:
        d['boundary'] = [v for v in spec['enums'].get(key, [])]
    lp = spec['ranges'].get(('__like__',) + key)
    if lp:
        d['like_prefix'] = lp
    return d


def _plant_nulls(values: list, share: float, rng) -> list:
    """NULL rule: at least one NULL and a share following the compact database's share."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _apply_duplicates(values: list, rng, share: float = 0.3) -> list:
    """Repeat 20-50% of values across rows (duplicates_for_distinct)."""
    n = len(values)
    if n < 2:
        return values
    k = max(1, int(round(share * n)))
    k = min(k, n - 1)
    out = list(values)
    for i in rng.sample(range(n), k):
        j = rng.randrange(n)
        if j != i:
            out[i] = out[j]
    return out


def _apply_ties(values: list, rng) -> list:
    """Ensure at least two rows share the same value (ties_for_order_limit)."""
    n = len(values)
    if n < 2:
        return values
    out = list(values)
    i = rng.randrange(n - 1)
    out[i + 1] = out[i]
    return out


def choose_table_sizes(schema, spec: dict, rng) -> dict:
    """Specification sizes, varied per instance (0-230 rows, or level x4 capped at 2500)."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                base = spec['sizes'].get(t, 40)
                sizes[t] = max(0, min(230, int(base * (0.5 + rng.random()))))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent key values: compact rows first, then generated rows (in memory, already finalized)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _compact_key_set(schema, pt: str, pc: str) -> set:
    return {v for v in schema.original_values.get((pt, pc), []) if v is not None}


def _fresh_pk(schema, table: str, col: str, base, used: set, rng, max_len=None):
    """Make a generated primary-key value fresh against compact rows and already generated ones."""
    if base is None:
        base = ''
    base = str(base)
    if max_len:
        base = base[:max_len]
    cand = base
    k = 0
    while cand in used:
        k += 1
        if max_len:
            alpha = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            cand = ''.join(rng.choice(alpha if i < 2 else alpha + '0123456789')
                           for i in range(max_len))
        else:
            cand = base + '_' + str(k)
        if k > 100000:
            cand = (base[:2] if len(base) >= 2 else 'ZZ') + ('%06d' % rng.randrange(10 ** 6))
            if max_len:
                cand = cand[:max_len]
            break
    used.add(cand)
    return cand


def _copied_value(instance: dict, schema, pt: str, pc: str, copied_col: str, key):
    """Look up a copied column value for a parent key (compact rows then generated rows)."""
    if key is None:
        return None
    ov = schema.original_values.get((pt, pc), [])
    oc = schema.original_values.get((pt, copied_col), [])
    for i, v in enumerate(ov):
        if v == key and i < len(oc):
            return oc[i]
    gcols = instance.get(pt, {})
    gv = gcols.get(pc, [])
    gc = gcols.get(copied_col, [])
    for i, v in enumerate(gv):
        if v == key and i < len(gc):
            return gc[i]
    return None


def _ensure_group_variety(inst: dict, schema, rng) -> None:
    """Indicators: per (CountryCode, IndicatorCode) at least two rows with distinct Year and Value."""
    t = 'Indicators'
    if t not in schema.tables or t not in inst:
        return
    cols = inst[t]
    if not {'CountryCode', 'IndicatorCode', 'Year', 'Value'} <= set(cols):
        return
    n = _nrows(cols)
    groups: dict = {}
    for i in range(n):
        groups.setdefault((cols['CountryCode'][i], cols['IndicatorCode'][i]), []).append(i)
    years = schema.original_values.get((t, 'Year'), [])
    ylo = min(years) if years else 1960
    yhi = max(years) if years else 2015
    ylo, yhi = min(ylo, 1960), max(yhi, 2015)
    for g, idxs in groups.items():
        if len(idxs) < 2:
            continue
        yrs = {cols['Year'][i] for i in idxs}
        vals = {cols['Value'][i] for i in idxs if cols['Value'][i] is not None}
        if len(yrs) >= 2 and len(vals) >= 2:
            continue
        i0, i1 = idxs[0], idxs[1]
        y0 = cols['Year'][i0] if cols['Year'][i0] is not None else rng.randint(max(1960, ylo), min(2015, yhi))
        y1 = y0 + 1 if y0 < yhi else y0 - 1
        y1 = max(ylo, min(yhi, y1))
        if y1 in yrs and y1 != y0:
            for cand in range(ylo, yhi + 1):
                if cand not in yrs:
                    y1 = cand
                    break
        cols['Year'][i0] = y0
        cols['Year'][i1] = y1
        v0 = cols['Value'][i0]
        if v0 is None:
            v0 = rng.randint(0, 1000)
        cols['Value'][i0] = max(0, v0)
        v1 = cols['Value'][i1]
        if v1 is None:
            v1 = v0 + 1 + rng.randrange(100)
        if v1 == v0:
            v1 = v0 + 1
        cols['Value'][i1] = max(0, v1)


def _seed_boundary_literals(cols: dict, key: tuple, spec: dict, rng) -> None:
    """Guarantee listed boundary literals appear at least once per instance (first rows)."""
    vals = spec['enums'].get(key)
    if not vals or key not in spec['boundary']:
        return
    col = key[1]
    if col not in cols:
        return
    n = len(cols[col])
    if n == 0:
        return
    for j, v in enumerate(vals):
        if j < n:
            cols[col][j] = v


def _seed_year_boundaries(cols: dict, key: tuple, spec: dict) -> None:
    """Seed Indicators.Year boundary literals (1979-1982) into the first rows."""
    if key != ('Indicators', 'Year') or 'Year' not in cols:
        return
    n = len(cols['Year'])
    for j, v in enumerate([1979, 1980, 1981, 1982]):
        if j < n:
            cols['Year'][j] = v


def _finalize_table(t: str, tm, cols: dict, inst: dict, schema, spec: dict, rng) -> dict:
    """Apply the specification to one table's columns and return the FINAL (post-dedup) columns."""
    if t == 'Indicators':
        inst[t] = cols
        _ensure_group_variety(inst, schema, rng)
        cols = inst[t]
    for cm in tm.columns:
        key = (t, cm.name)
        if key in spec['duplicate'] and cm.name in cols and cm.name not in tm.primary_key:
            cols[cm.name] = _apply_duplicates(cols[cm.name], rng)
        if key in spec['ties'] and cm.name in cols:
            if t == 'Indicators' and cm.name in ('Year', 'Value'):
                continue
            cols[cm.name] = _apply_ties(cols[cm.name], rng)
        if key in spec['always_null'] and cm.name in cols:
            cols[cm.name] = [None] * len(cols[cm.name])
    if t == 'Indicators' and 'Value' in cols:
        cols['Value'] = [None if v is None else max(0, int(v)) for v in cols['Value']]
    copied_cols = spec.get('copied_cols', set())
    for cm in tm.columns:
        key = (t, cm.name)
        if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
            continue
        if key in copied_cols:
            continue
        if key in spec['always_null']:
            continue
        share = spec['null_share'].get(key, 0.02)
        cols[cm.name] = _plant_nulls(cols[cm.name], share, rng)
    for cm in tm.columns:
        _seed_boundary_literals(cols, (t, cm.name), spec, rng)
        _seed_year_boundaries(cols, (t, cm.name), spec)
    if tm.primary_key:
        cols = sample_fresh_primary_keys(tm, cols)
    return cols


def build_random_instance(schema, literal_pool: dict, spec: dict, size, rng) -> dict:
    """Build one random instance of *generated* rows (fuzz.py:111-196) with specification domains."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []), schema.original_values.get((t, cm.name), []),
                    p, rng, len(tm.primary_key), domain=_domain_for(spec, (t, cm.name)))
    if size is None:
        size = choose_table_sizes(schema, spec, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        fk_cols = [(cm, schema.fks[(t, cm.name)]) for cm in tm.columns if (t, cm.name) in schema.fks]
        for cm, (pt, pc) in fk_cols:
            pv = _parent_pool(inst, schema, pt, pc)
            if not pv:
                cols[cm.name] = []
                continue
            vals = [rng.choice(pv) for _ in range(n)]
            cols[cm.name] = vals
        for d in spec.get('deps', []):
            if d['child'][0] != t:
                continue
            fk_col = d['child'][1]
            pt, pc = d['parent']
            fkvals = cols.get(fk_col, [])
            for cc in d['copied']:
                if cc[0] != t:
                    continue
                cols[cc[1]] = [_copied_value(inst, schema, pt, pc, cc[1], k) for k in fkvals]
        if tm.primary_key:
            if len(tm.primary_key) == 1:
                c0 = tm.primary_key[0]
                used = _compact_key_set(schema, t, c0)
                max_len = None
                cm0 = next((c for c in tm.columns if c.name == c0), None)
                if cm0 and re.search(r'\((\d+)\)', cm0.type_str or ''):
                    max_len = int(re.search(r'\((\d+)\)', cm0.type_str).group(1))
                vals0 = cols.get(c0, [])
                for i in range(len(vals0)):
                    vals0[i] = _fresh_pk(schema, t, c0, vals0[i], used, rng, max_len)
            else:
                for c0 in tm.primary_key:
                    if c0 in cols:
                        used = _compact_key_set(schema, t, c0)
                        vals0 = cols[c0]
                        for i in range(len(vals0)):
                            vals0[i] = _fresh_pk(schema, t, c0, vals0[i], used, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols and cm.name in cols:
                final = cols[pc]
                fs = set(v for v in final if v is not None)
                if fs:
                    cols[cm.name] = [v if v in fs else rng.choice(sorted(fs)) for v in cols[cm.name]]
        cols = _finalize_table(t, tm, cols, inst, schema, spec, rng)
        inst[t] = cols
    return {t: inst.get(t, {}) for t in schema.tables}
