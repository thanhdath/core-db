"""Random instance construction (fuzz/fuzz.py:83-196) implemented against spec.py by construction."""
import datetime as dt

from .spec import minute_key
from .values import _init_sampler


def _filter(columns, keep):
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns):
    return len(next(iter(columns.values()))) if columns else 0


def _dedup_tuples(table_meta, columns, keys):
    if not keys or not columns:
        return columns
    n = _n_rows(columns)
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in keys)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def sample_fresh_primary_keys(table_meta, columns):
    return _dedup_tuples(table_meta, columns, table_meta.primary_key)


def drop_unique_duplicates(table_meta, columns):
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance, schema, table, column):
    if (table, column) not in schema.fks:
        return []
    ptab, pcol = schema.fks[(table, column)]
    pool = list(instance.get(ptab, {}).get(pcol, [])) or list(schema.original_values.get((ptab, pcol), []))
    return [v for v in pool if v is not None]


def fill_foreign_keys_consistently(instance, schema, table, n, rng):
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pv = _parent_pool(instance, schema, table, cm.name)
        if not pv:
            out[cm.name] = [None] * n
            continue
        out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng, spec=None):
    if spec is not None:
        sizes = {}
        for t in schema.tables:
            base = int(spec.table_sizes.get(t, max(1, len(
                schema.original_values.get((t, schema.tables[t].columns[0].name), [])))))
            if t == 'Products':
                base = spec.products_size
            u = rng.random()
            if t == 'Products':
                sizes[t] = base
            elif t == 'Addresses':
                v = u
                if v < 0.10:
                    sizes[t] = max(spec.min_addresses_size, base)
                elif v < 0.80:
                    sizes[t] = max(spec.min_addresses_size, base)
                elif v < 0.95:
                    sizes[t] = max(spec.min_addresses_size,
                                   base + rng.randint(-max(1, base // 3), max(1, base // 3)))
                else:
                    sizes[t] = min(230, max(spec.min_addresses_size, base + rng.randint(1, 10)))
            elif u < 0.10:
                sizes[t] = 0
            elif u < 0.80:
                sizes[t] = base
            elif u < 0.95:
                sizes[t] = max(1, base + rng.randint(-max(1, base // 3), max(1, base // 3)))
            else:
                sizes[t] = min(230, base + rng.randint(1, 10))
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


def _plant_nulls(cols, share, force_one, rng):
    n = len(cols)
    if n == 0:
        return cols
    target = int(round(share * n))
    if force_one:
        target = max(1, target)
    target = min(target, n)
    positions = list(range(n))
    rng.shuffle(positions)
    for i in positions[:target]:
        cols[i] = None
    return cols


def _ensure_distinct(cols, keyfn, rng):
    """Make every non-NULL value distinct under ``keyfn``."""
    seen, out = set(), []
    for v in cols:
        if v is None:
            out.append(v)
            continue
        k = keyfn(v)
        if k in seen:
            for step in range(1, 200):
                try:
                    d = dt.datetime.strptime(str(v), '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    d = None
                if d is not None:
                    d2 = d + dt.timedelta(minutes=step)
                    vv = d2.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    vv = '%s-%d' % (k, step)
                kk = keyfn(vv)
                if kk not in seen:
                    v, k = vv, kk
                    break
        seen.add(k)
        out.append(v)
    return out


def _plant_duplicates(cols, rng, n_dup_target=0.35):
    n = len(cols)
    if n < 4:
        return cols
    k = max(2, min(n - 1, int(round(n_dup_target * n))))
    positions = list(range(n))
    rng.shuffle(positions)
    src = positions[0]
    for i in positions[1:k + 1]:
        cols[i] = cols[src]
    return cols


def _plant_ties(cols, rng):
    n = len(cols)
    if n < 2:
        return cols
    a = rng.randrange(n)
    b = rng.randrange(n)
    if a == b:
        return cols
    cols[b] = cols[a]
    return cols


def _force_boundaries(table, column, cols, spec, rng):
    """Post-process replacement of (up to N) values with each required literal."""
    required = spec.required_boundary_for(table, column)
    if not required or not cols:
        return cols
    n = len(cols)
    positions = list(range(n))
    rng.shuffle(positions)
    for lit in required:
        if lit in cols:
            continue
        if not positions:
            break
        cols[positions.pop()] = lit
    return cols


def _plant_aggregate_boundaries(instance, schema, spec, rng):
    """Addresses count > 4 is guaranteed by min size; Products distinct count = 2."""
    pcols = instance.get('Products')
    if pcols and 'product_details' in pcols:
        vals = pcols['product_details']
        non_null = [v for v in vals if v is not None]
        if len(non_null) >= 2:
            distinct = list(dict.fromkeys(non_null))
            if len(distinct) >= 2:
                a, b = distinct[0], distinct[1]
                out = []
                for v in vals:
                    if v is None:
                        out.append(None)
                    elif v in (a, b):
                        out.append(v)
                    else:
                        out.append(a if rng.random() < 0.5 else b)
                pcols['product_details'] = out


def _compute_date_pairs(instance, spec, rng):
    for tab, to_col, from_col, op in spec.date_pairs:
        cols = instance.get(tab)
        if not cols or to_col not in cols or from_col not in cols:
            continue
        cur_to = cols[to_col]
        cur_from = cols[from_col]
        for i, f in enumerate(cur_from):
            if cur_to[i] is None or f is None:
                continue
            if str(cur_to[i]) < str(f):
                cols[to_col][i] = f


def _compute_positive_quantities(instance, spec, rng):
    for tab, col in spec.positive_quantities:
        cols = instance.get(tab)
        if not cols or col not in cols:
            continue
        out = []
        for v in cols[col]:
            if v is None:
                out.append(None)
                continue
            try:
                iv = int(str(v))
            except (TypeError, ValueError):
                iv = rng.randint(1, 9)
            out.append(str(max(1, iv)))
        cols[col] = out


def _external_tie_plants(instance, spec, rng):
    """Repeat an FK value in up to K rows so a rank-1 tie on the FK grouping column exists."""
    for tab, col, parent in spec.tie_plants_external:
        cols = instance.get(tab)
        if not cols or col not in cols:
            continue
        vals = cols[col]
        if len(vals) < 2:
            continue
        nz = [i for i, v in enumerate(vals) if v is not None]
        if len(nz) < 2:
            continue
        src = rng.choice(nz)
        reps = 0
        for j in nz:
            if j == src:
                continue
            if reps >= 2:
                break
            vals[j] = vals[src]
            reps += 1


def build_random_instance(schema, literal_pool, size, rng, spec=None):
    """Build one random instance (fuzz.py:111-196) extended by the specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            key = '%s.%s' % (t, cm.name)
            boundary = spec.boundary_for(t, cm.name) if spec else []
            required = spec.required_boundary_for(t, cm.name) if spec else []
            enum = spec.enums.get(key) if spec else None
            positive = (key in spec.positive_int) if spec else False
            window = spec.date_windows.get(key) if spec else None
            pool = literal_pool.get((t, cm.name), [])
            observed = spec.observed_for(t, cm.name) if spec else []
            n_pk = len(tm.primary_key)
            max_l0 = float('inf')
            start = spec.pk_start_for(t) if (spec and cm.pk_pos > 0) else None
            s = _init_sampler(cm, pool,
                              observed or schema.original_values.get((t, cm.name), []),
                              p, rng, n_pk, max_l0, boundary=boundary, required=required,
                              enum=enum, positive=positive, window=window, start=start)
            samplers[(t, cm.name)] = s
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                s = samplers[(t, cm.name)]
                is_nullable = spec.is_nullable(t, cm.name) if spec else not cm.notnull and not cm.pk_pos
                vals = [s.sample() for _ in range(n)]
                if is_nullable:
                    vals = _plant_nulls(vals, spec.null_share_for(t, cm.name), True, rng)
                cols[cm.name] = vals
        inst[t] = cols
        fk = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        for cm in tm.columns:
            if cm.name in fk:
                vals = fk[cm.name]
                is_nullable = spec.is_nullable(t, cm.name) if spec else not cm.notnull and not cm.pk_pos
                if is_nullable and n > 0:
                    vals = _plant_nulls(vals, spec.null_share_for(t, cm.name), True, rng)
                cols[cm.name] = vals
        if spec is not None:
            for cm in tm.columns:
                key = '%s.%s' % (t, cm.name)
                if key in spec.duplicates and not cm.pk_pos and (t, cm.name) not in schema.fks:
                    cols[cm.name] = _plant_duplicates(list(cols.get(cm.name, [])), rng)
                if key in spec.ties and not cm.pk_pos and (t, cm.name) not in schema.fks:
                    cols[cm.name] = _plant_ties(list(cols.get(cm.name, [])), rng)
            if '%s.active_to_date' % t == 'Customer_Contact_Channels.active_to_date':
                cols['active_to_date'] = _ensure_distinct(list(cols.get('active_to_date', [])), minute_key, rng)
        cols = sample_fresh_primary_keys(tm, {c.name: cols[c.name] for c in tm.columns if c.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    if spec is not None:
        _compute_date_pairs(inst, spec, rng)
        _compute_positive_quantities(inst, spec, rng)
        _plant_aggregate_boundaries(inst, schema, spec, rng)
        for t, tm in ((t, schema.tables[t]) for t in order):
            for cm in tm.columns:
                if (t, cm.name) in schema.fks:
                    continue
                if cm.name not in inst.get(t, {}):
                    continue
                inst[t][cm.name] = _force_boundaries(t, cm.name, inst[t][cm.name], spec, rng)
        if 'Customer_Contact_Channels' in inst and 'active_to_date' in inst['Customer_Contact_Channels']:
            inst['Customer_Contact_Channels']['active_to_date'] = _ensure_distinct(
                list(inst['Customer_Contact_Channels']['active_to_date']), minute_key, rng)
            _compute_date_pairs(inst, spec, rng)
    for t in order:
        inst[t] = sample_fresh_primary_keys(schema.tables[t], inst[t])
    if spec is not None:
        _plant_unmatched(inst, schema, spec.unmatched_parents, rng)
        _external_tie_plants(inst, spec, rng)
        for t in order:
            inst[t] = sample_fresh_primary_keys(schema.tables[t], inst[t])
    return {t: inst[t] for t in schema.tables}, size


def _plant_unmatched(instance, schema, parents, rng):
    for ptab, child_tabs in parents.items():
        if ptab not in instance:
            continue
        for cm in schema.tables[ptab].columns:
            if not cm.pk_pos:
                continue
            pvals = [v for v in instance[ptab].get(cm.name, []) if v is not None]
            if len(pvals) < 2:
                continue
            victim = rng.choice(pvals)
            for t in schema.tables:
                tcols = instance.get(t) or {}
                for cc, ccvals in tcols.items():
                    if schema.fks.get((t, cc)) != (ptab, cm.name):
                        continue
                    nv = [v for v in ccvals if v != victim]
                    if nv:
                        instance[t][cc] = nv + [rng.choice(nv) for _ in range(len(ccvals) - len(nv))]
                        rng.shuffle(instance[t][cc])
