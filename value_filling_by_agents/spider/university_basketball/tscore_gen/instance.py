"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append-only generation."""
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Sizes from specification table_sizes_per_instance, jittered 0..2x, capped at 250."""
    sizes = {}
    tsi = (spec or {}).get('table_sizes_per_instance', {}) or {}
    for t in schema.tables:
        base = int(tsi.get(t, 8))
        n = rng.randint(max(1, base // 2), base + 2)
        n = min(n, 250)
        sizes[t] = n
    return sizes


def _sample_percent(rng) -> str:
    return '.%03d' % rng.randint(0, 999)


def _sample_score(rng) -> str:
    """W-L score with an ASCII hyphen (satisfies LIKE '%-%')."""
    w, l = rng.randint(0, 16), rng.randint(0, 16)
    return '%d-%d' % (w, l)


def _fresh_from_domain(col_spec, sampler, rng) -> object:
    """Draw one value for a column, honouring the semantic domain by construction."""
    tag = col_spec['tags']
    if col_spec.get('enum') and rng.random() < 0.7:
        return rng.choice(col_spec['enum'])
    if col_spec.get('boundary') and rng.random() < 0.5:
        b = rng.choice(col_spec['boundary'])
        if 'founded' in tag:
            v = float(b) + rng.choice([-1, 0, 1])
            return min(2100.0, max(1600.0, v))
        if 'enrollment' in tag:
            return max(0.0, float(b) + rng.choice([-1, 0, 1]))
        if col_spec['is_int']:
            return int(b)
        return float(b)
    if col_spec.get('form') == 'percent':
        return _sample_percent(rng)
    if col_spec.get('form') == 'score':
        return _sample_score(rng)
    if col_spec.get('like_literals') and col_spec.get('variants') and rng.random() < 0.5:
        v = rng.choice(col_spec['variants'])
        k = rng.random()
        if k < 0.25:
            return v
        if k < 0.5:
            return v + ' x'
        if k < 0.75:
            return v.lower()
        return v + ', ZZ'
    return sampler.sample()


def _pool_value(col_spec, sampler, rng) -> object:
    """Draw from the observed/literal pool (the ~70 % non-fresh share)."""
    if sampler.elements:
        return sampler.sample()
    return _fresh_from_domain(col_spec, sampler, rng)


def sample_fresh_primary_keys(table_meta, columns: dict, compact_keys: set) -> dict:
    """Drop rows whose PK tuple repeats (or equals a compact key), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(compact_keys), []
    for i in range(n):
        try:
            k = tuple(columns[c][i] for c in table_meta.primary_key)
        except KeyError:
            continue
        if k not in seen and all(x is not None for x in k):
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_uniq: dict) -> dict:
    """Drop rows repeating any single unique column value (compact values preloaded)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(compact_uniq.get(cm.name, ()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def plan_nulls(table_meta, n: int, rng, null_tags: set, col_specs: dict) -> dict:
    """Return {column: set(indices that get NULL)} following the NULL rule (>=1 NULL, per-column share)."""
    plan = {}
    nullable = [cm for cm in table_meta.columns if not (cm.notnull or cm.pk_pos > 0)]
    if not nullable or n == 0:
        return plan
    for cm in nullable:
        key = '%s.%s' % (table_meta.name, cm.name)
        if null_tags and key not in null_tags:
            continue
        share = col_specs.get((table_meta.name, cm.name), {}).get('null_share', 0.1)
        k = max(1, int(round(share * n)))
        idx = set(rng.sample(range(n), min(k, n)))
        plan[cm.name] = idx
    return plan


def _build_compact_index(schema) -> dict:
    """In-memory compact rows per table + key/unique sets (never written to)."""
    idx = {'rows': {}, 'pk': {}, 'uniq': {}}
    for t, tm in schema.tables.items():
        cols = {cm.name: list(schema.original_values.get((t, cm.name), [])) for cm in tm.columns}
        n = len(next(iter(cols.values()))) if cols else 0
        idx['rows'][t] = cols
        pk = set()
        for i in range(n):
            pk.add(tuple(cols[c][i] for c in tm.primary_key))
        idx['pk'][t] = pk
        uq = {}
        for cm in tm.columns:
            if cm.unique:
                uq[cm.name] = {cols[cm.name][i] for i in range(n)}
        idx['uniq'][t] = uq
        for (tt, cc) in getattr(schema, 'unique_from_index', []) or []:
            if tt == t:
                uq.setdefault(cc, set()).update(cols.get(cc, []))
    return idx


def _apply_dup_share(cols: dict, cname: str, n: int, rng) -> None:
    """Force a 20-50 % duplicate share on a DISTINCT-target column."""
    if cname not in cols or n < 2:
        return
    vals = cols[cname]
    k = max(1, int(round(rng.uniform(0.2, 0.5) * n)))
    k = min(k, n - 1)
    if k <= 0:
        return
    src = rng.randrange(n)
    for i in rng.sample(range(n), k):
        if i != src:
            vals[i] = vals[src]


def _apply_tie(cols: dict, cname: str, cs: dict, n: int, rng) -> None:
    """Force at least two rows to share the rank-1 value, unique from the next rank."""
    if cname not in cols or n < 2:
        return
    if cs.get('form') == 'percent':
        v = _sample_percent(rng)
    elif cs.get('form') == 'score':
        v = _sample_score(rng)
    elif cs.get('boundary'):
        v = cs['boundary'][0]
    else:
        v = cols[cname][0]
    cols[cname][0] = v
    cols[cname][1] = v
    for i in range(2, n):
        if cols[cname][i] == v:
            if cs.get('form') == 'percent':
                cols[cname][i] = _sample_percent(rng)
            elif cs.get('form') == 'score':
                cols[cname][i] = _sample_score(rng)
            elif isinstance(v, (int, float)):
                cols[cname][i] = v + 1
            else:
                cols[cname][i] = str(v) + ' x'
            break


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None,
                          col_specs: dict = None, mild: dict = None) -> dict:
    """Build the *additive* part of one random instance."""
    spec = spec or {}
    col_specs = col_specs or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = size if size is not None else choose_table_sizes(schema, rng, spec)
    ci = _build_compact_index(schema)
    null_tags = set((spec or {}).get('null_targets', []) or [])
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                ov = schema.original_values.get((t, cm.name), [])
                els = (rng.choices(ov, k=min(5, len(ov))) if ov else [])
                els = [e for e in els if e is not None] + sorted({str(v) for v in literal_pool.get((t, cm.name), [])})
                samplers[(t, cm.name)] = _init_sampler(cm, els, ov, p, rng, len(tm.primary_key))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        if n <= 0:
            inst[t] = {}
            continue
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            cs = col_specs.get((t, cm.name), {})
            sampler = samplers[(t, cm.name)]
            vals = []
            for _ in range(n):
                if rng.random() < cs.get('fresh', 0.3):
                    vals.append(_fresh_from_domain(cs, sampler, rng))
                else:
                    vals.append(_pool_value(cs, sampler, rng))
            cols[cm.name] = vals
        for cm in tm.columns:
            cs = col_specs.get((t, cm.name), {})
            if cs.get('dup_share'):
                _apply_dup_share(cols, cm.name, n, rng)
        for cm in tm.columns:
            cs = col_specs.get((t, cm.name), {})
            if cs.get('tie'):
                _apply_tie(cols, cm.name, cs, n, rng)
        inst[t] = cols
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = list(ci['rows'].get(pt, {}).get(pc, [])) + list(inst.get(pt, {}).get(pc, []))
            pv = [x for x in pv if x is not None]
            if len(pv) > 1:
                orphan = rng.choice(pv)
                pv = [x for x in pv if x != orphan]
            inst[t][cm.name] = [rng.choice(pv) if pv else None for _ in range(n)]
        plan = plan_nulls(tm, n, rng, null_tags, col_specs)
        for cname, idxs in plan.items():
            if cname in inst[t]:
                for i in idxs:
                    if i < len(inst[t][cname]):
                        inst[t][cname][i] = None
        inst[t] = sample_fresh_primary_keys(tm, inst[t], ci['pk'].get(t, set()))
        inst[t] = drop_unique_duplicates(tm, inst[t], ci['uniq'].get(t, {}))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in inst[t]:
                final = [v for v in inst[t][pc] if v is not None]
                fs = set(final)
                inst[t][cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                    for v in inst[t][cm.name]]
    return {t: inst.get(t, {}) for t in schema.tables}
