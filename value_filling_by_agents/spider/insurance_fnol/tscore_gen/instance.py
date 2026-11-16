"""Specification-driven instance construction (round 1 revision)."""
import datetime as dt
import string

_WORD_POOL = ['Diana', 'Dianb', 'Diana x', 'diana', 'sian', 'siao', 'sian x', 'SIAN',
              'America Jaskolski', 'Ellsworth Paucek', 'Hanna Willms', 'Selena Gerhold',
              'Dayana Robel', 'Edwardo Blanda', 'Randal Lynch', 'Marge Kutch', 'Leeanne Marvin',
              'Cody Spencer', 'Joaquin Fadel', 'Terrance Hahn']
_PHONE_FORMATS = ['+{cc}({d}){n}', '{a}.{b}.{c}', '1-{a}-{b}-{c}x{e}', '({a}){b}-{c}',
                  '1-{a}-{b}-{c}x{e}', '({a}){b}-{c}x{e}', '+{cc}({d}){n}']
_ENUM_DEFAULT = ['Life Insurance', 'Property Insurance', 'Mortgage Insurance', 'Travel Insurance']
_DATE_LO = dt.date(2015, 1, 1)
_DATE_HI = dt.date(2019, 12, 31)


def _di(rng, lo, hi):
    return rng.randint(int(lo), int(hi))


def _rand_str(rng, n=8):
    return ''.join(rng.choice(string.ascii_letters + ' ') for _ in range(n))


def _type_of(col) -> str:
    t = (col.type_str or '').lower()
    if 'date' in t or 'timestamp' in t:
        return 'date'
    if 'char' in t or 'text' in t or t == '':
        return 'str'
    if 'real' in t or 'float' in t or 'double' in t or 'decimal' in t or 'numeric' in t:
        return 'real'
    if 'int' in t:
        return 'int'
    return 'str'


def _rand_date(rng):
    span = (_DATE_HI - _DATE_LO).days
    return (_DATE_LO + dt.timedelta(days=rng.randint(0, span))).isoformat()


def _rand_phone(rng):
    f = rng.choice(_PHONE_FORMATS)
    return f.format(cc=rng.randint(1, 99), a=rng.randint(100, 999), b=rng.randint(100, 999),
                    c=rng.randint(1000, 9999), e=rng.randint(1, 99999), d=rng.randint(0, 99),
                    n=rng.randint(1000000000, 9999999999))


def _rand_real(rng):
    return round(rng.uniform(0.01, 10000.0), 2)


def _near_variants(lit: str) -> list:
    """Base literal plus case / suffix / one-character variants (LIKE-safe)."""
    bare = lit.strip('%')
    out = [lit]
    if bare:
        out += [bare, bare.upper(), bare.lower(), bare.title(), bare + 'x', bare[:-1], bare[1:],
                bare.replace(bare[0], 'x', 1) if bare else bare]
    return out


def _distinct_pool(rng, n_values, base_pool, key: str, dup_share, typ: str = 'str'):
    """Return n_values items with the requested duplicate share."""
    if n_values <= 0:
        return []
    uniq = list(dict.fromkeys(base_pool)) if base_pool else []
    if dup_share is None:
        dup_share = (0.0, 0.0)
    lo, hi = dup_share
    share = rng.uniform(lo, hi)
    n_dup = int(round(share * n_values))
    n_dup = max(0, min(n_dup, n_values - 1)) if n_values > 1 else 0
    n_fresh = n_values - n_dup
    out = []
    for i in range(n_fresh):
        if i < len(uniq):
            v = uniq[i]
        elif typ == 'int':
            v = rng.randint(1, 100000)
        else:
            v = key + ' ' + _rand_str(rng, 6)
        out.append(v)
    pool = list(dict.fromkeys(out)) or uniq
    for _ in range(n_dup):
        out.append(rng.choice(pool))
    rng.shuffle(out)
    return out


def _date_ge(parent_date, rng) -> str:
    try:
        d = dt.date.fromisoformat(str(parent_date)[:10])
    except Exception:
        d = dt.date(2018, 1, 1)
    extra = rng.randint(0, 700)
    d2 = d + dt.timedelta(days=extra)
    if d2 < _DATE_LO:
        d2 = _DATE_LO
    return d2.isoformat()


def _map_enum_rule(rules_by_table, t):
    out = {}
    for r in rules_by_table.get(t, []):
        if r.get('kind') == 'enum':
            out[r['col']] = list(r['values'])
    return out


def _ge_rules(rules_by_table, t):
    return [r for r in rules_by_table.get(t, []) if r.get('kind') in ('ge_cols', 'ge_lit')]


def _not_null_rule_cols(rules_by_table, t):
    return {r['col'] for r in rules_by_table.get(t, []) if r.get('kind') == 'not_null'}


def _apply_ge_rules(rules_by_table, t, ncols, rng):
    """Enforce Date_Closed >= Date_Opened and Settlement_Amount >= 0 in Python."""
    for r in _ge_rules(rules_by_table, t):
        col = r['col']
        if col not in ncols:
            continue
        if r['kind'] == 'ge_cols' and r.get('ref') in ncols:
            vals = list(ncols[col])
            ref = ncols[r['ref']]
            for i in range(len(vals)):
                a, b = vals[i], ref[i]
                if a is None or b is None:
                    continue
                try:
                    da = dt.date.fromisoformat(str(a)[:10])
                    db = dt.date.fromisoformat(str(b)[:10])
                except Exception:
                    continue
                if da < db:
                    vals[i] = _date_ge(b, rng)
            ncols[col] = vals
        elif r['kind'] == 'ge_lit':
            mn = r['min']
            vals = []
            for v in ncols[col]:
                if v is None:
                    vals.append(None)
                else:
                    try:
                        vals.append(max(float(v), mn))
                    except (TypeError, ValueError):
                        vals.append(v)
            ncols[col] = vals


def _composite_fk_groups(schema):
    """Map child table -> list of (child_cols, parent_table, parent_cols) for composite FKs."""
    groups: dict = {}
    by_parent: dict = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        by_parent.setdefault((ct, pt), []).append((cc, pc))
    for (ct, pt), pairs in by_parent.items():
        if len(pairs) >= 2:
            groups.setdefault(ct, []).append(([p[0] for p in pairs], pt, [p[1] for p in pairs]))
    return groups


def _parent_tuples(schema, parent_table, parent_cols, generated_rows):
    """Existing (compact + generated) key tuples of the parent, in memory."""
    lists = []
    for c in parent_cols:
        vals = list(schema.original_values.get((parent_table, c), []))
        gen = generated_rows.get(parent_table, {}).get(c, [])
        lists.append(vals + list(gen))
    if not lists:
        return []
    m = min(len(x) for x in lists)
    return [tuple(lists[j][i] for j in range(len(lists))) for i in range(m)]


def _distribute_children(rng, n_children, n_parents, want_sizes=(1, 2, 3)):
    """Assign each child to a parent index so some parents get 1, some 2, some >=3."""
    if n_parents <= 0:
        return []
    counts = [0] * n_parents
    order = list(range(n_parents))
    rng.shuffle(order)
    k = 0
    for s in want_sizes:
        if k < n_parents and sum(counts) + s <= n_children:
            counts[order[k]] = s
            k += 1
    rest = n_children - sum(counts)
    j = 0
    while rest > 0:
        p = order[j % n_parents]
        counts[p] += 1
        rest -= 1
        j += 1
    out = []
    for p, c in enumerate(counts):
        out.extend([p] * c)
    rng.shuffle(out)
    return out


def build_spec_instance(schema, literal_pool: dict, plan: dict, rng):
    """Return (rows, stats) where rows is per-table columns -> list of values."""
    order = [t for lvl in schema.table_order for t in lvl]
    for t in schema.tables:
        if t not in order:
            order.append(t)
    sizes = plan.get('sizes', {})
    out_rows: dict = {t: {} for t in schema.tables}
    stats = {'added': {}, 'skipped': {}}

    generated_ids: dict = {}
    all_pk_values: dict = {}
    for t, tm in schema.tables.items():
        if tm.primary_key and len(tm.primary_key) == 1:
            pk = tm.primary_key[0]
            vals = [v for v in schema.original_values.get((t, pk), []) if isinstance(v, int)]
            all_pk_values[(t, pk)] = list(vals)
            generated_ids[(t, pk)] = []

    existing_unique: dict = {}
    for t, tm in schema.tables.items():
        for ug in tm.unique_groups:
            keys = set()
            lists = [schema.original_values.get((t, c), []) for c in ug]
            if lists and all(lists):
                m = min(len(x) for x in lists)
                for i in range(m):
                    keys.add(tuple(lists[j][i] for j in range(len(ug))))
            existing_unique[(t, tuple(ug))] = keys

    rules_by_table: dict = {}
    for r in plan.get('rules', []):
        rules_by_table.setdefault(r.get('table'), []).append(r)

    composite_fks = _composite_fk_groups(schema)

    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, rng.randint(0, 30)))
        if n == 0:
            out_rows[t] = {}
            stats['added'][t] = 0
            stats['skipped'][t] = 0
            continue
        enum_map = _map_enum_rule(rules_by_table, t)
        not_null_rule = _not_null_rule_cols(rules_by_table, t)
        ncols = {}
        composite_cols = set()
        for child_cols, pt, pcols in composite_fks.get(t, []):
            composite_cols.update(child_cols)

        for cm in tm.columns:
            key = (t, cm.name)
            col_plan = plan['cols'].get(key, {})
            is_fk = key in schema.fks
            is_pk = cm.name in tm.primary_key
            typ = _type_of(cm)
            base = list(literal_pool.get(key, []))
            observed = [v for v in schema.original_values.get(key, []) if v is not None]
            if cm.name in composite_cols:
                ncols[cm.name] = [None] * n
                continue
            if is_fk and not is_pk:
                pt, pc = schema.fks[key]
                parent_pool = [v for v in all_pk_values.get((pt, pc), []) if v is not None]
                want_null = (not cm.notnull) or col_plan.get('null_target')
                if want_null and n > 1:
                    null_rate = rng.uniform(0.05, 0.30)
                    n_null = max(1, int(round(null_rate * n)))
                else:
                    n_null = 0
                vals = []
                for _ in range(n - n_null):
                    if parent_pool:
                        vals.append(rng.choice(parent_pool))
                    else:
                        vals.append(rng.randint(1, 99999))
                vals += [None] * n_null
                rng.shuffle(vals)
                ncols[cm.name] = vals
                continue
            if is_pk and len(tm.primary_key) == 1 and typ == 'int':
                max_existing = schema.max_ids.get(key, 0)
                max_gen = generated_ids.get(key, [])
                start = max([max_existing] + (max_gen or [0])) + 1
                vals = list(range(start, start + n))
                generated_ids[key] = vals
                all_pk_values[key] = all_pk_values.get(key, []) + vals
                ncols[cm.name] = vals
                continue
            if is_pk:
                ncols[cm.name] = [None] * n
                continue
            if cm.name in enum_map:
                pool = enum_map[cm.name]
                variants = list(pool) + [p.lower() for p in pool if p.lower() != p]
                vals = [rng.choice(variants) for _ in range(n)]
                if col_plan.get('cmp_values'):
                    cv = list(col_plan['cmp_values'])
                    for i, v in enumerate(cv):
                        if i < n:
                            vals[i] = v
                ncols[cm.name] = vals
                continue
            if col_plan.get('cmp_values'):
                cv = list(col_plan['cmp_values'])
                vals = (cv * ((n // max(1, len(cv))) + 1))[:n]
                rng.shuffle(vals)
                ncols[cm.name] = vals
                continue
            if col_plan.get('like_variants') or col_plan.get('like_literals'):
                planted = []
                for lit in col_plan.get('like_literals', []):
                    planted.append(lit.strip('%'))
                for v in col_plan.get('like_variants', []):
                    planted.append(v)
                planted = list(dict.fromkeys(planted))
                vals = list(planted[:n])
                while len(vals) < n:
                    vals.append(rng.choice(planted) if planted else _rand_str(rng, 6))
                rng.shuffle(vals)
                ncols[cm.name] = vals
                continue
            if col_plan.get('dup_share') or col_plan.get('distinct'):
                share = col_plan.get('dup_share') or (rng.uniform(0.2, 0.4), rng.uniform(0.2, 0.4))
                if typ == 'str':
                    base_pool = observed + _WORD_POOL
                elif typ == 'int':
                    base_pool = [v for v in observed if isinstance(v, int)]
                else:
                    base_pool = [str(v) for v in observed]
                vals = _distinct_pool(rng, n, base_pool, cm.name, share, typ)
                ncols[cm.name] = vals
                continue
            if typ == 'date':
                if col_plan.get('dup_share'):
                    share = col_plan['dup_share']
                    uniq = [_rand_date(rng) for _ in range(max(1, n // 2))]
                    vals = _distinct_pool(rng, n, uniq, 'd', share, 'str')
                else:
                    vals = [_rand_date(rng) for _ in range(n)]
                ncols[cm.name] = vals
                continue
            if typ == 'real':
                vals = [_rand_real(rng) for _ in range(n)]
                ncols[cm.name] = vals
                continue
            if typ == 'int':
                vals = [_di(rng, 1, 1000) for _ in range(n)]
                ncols[cm.name] = vals
                continue
            if 'phone' in cm.name.lower():
                vals = []
                for _ in range(n):
                    if observed and rng.random() < 0.3:
                        vals.append(rng.choice(observed))
                    else:
                        vals.append(_rand_phone(rng))
                ncols[cm.name] = vals
            elif 'name' in cm.name.lower():
                vals = []
                for _ in range(n):
                    if observed and rng.random() < 0.35:
                        vals.append(rng.choice(observed))
                    else:
                        vals.append(rng.choice(_WORD_POOL))
                ncols[cm.name] = vals
            else:
                ncols[cm.name] = [_rand_str(rng, rng.randint(3, 12)) for _ in range(n)]

        for child_cols, pt, pcols in composite_fks.get(t, []):
            tuples = _parent_tuples(schema, pt, pcols, out_rows)
            if not tuples:
                tuples = [(None,) * len(pcols)]
            chosen = [rng.choice(tuples) for _ in range(n)]
            for j, cc in enumerate(child_cols):
                ncols[cc] = [chosen[i][j] for i in range(n)]

        for cm in tm.columns:
            cp = plan['cols'].get((t, cm.name), {})
            if cp.get('group_sizes') and cm.name in ncols and n >= 6:
                vals = list(ncols[cm.name])
                vals[0] = vals[1] = vals[2] = vals[0]
                vals[3] = vals[4]
                ncols[cm.name] = vals
            if cp.get('tie_at_rank') and cm.name in ncols and n >= 2:
                vals = list(ncols[cm.name])
                vals[0] = vals[1]
                ncols[cm.name] = vals

        for cm in tm.columns:
            if cm.name not in ncols or cm.name in tm.primary_key:
                continue
            if cm.notnull:
                continue
            cp = plan['cols'].get((t, cm.name), {})
            if cp.get('null_share') or cp.get('null_target'):
                share = cp.get('null_share') or (0.05, 0.30)
                lo, hi = share
                rate = rng.uniform(lo, hi)
                k = max(1, int(round(rate * n)))
                idxs = list(range(n))
                rng.shuffle(idxs)
                vals = list(ncols[cm.name])
                for i in idxs[:k]:
                    vals[i] = None
                ncols[cm.name] = vals

        _apply_ge_rules(rules_by_table, t, ncols, rng)

        safe_cols = list(ncols.keys())
        keep = []
        seen_pk = set(existing_unique.get((t, tuple(tm.primary_key)), set()))
        seen_unique = {}
        for ug in tm.unique_groups:
            seen_unique[tuple(ug)] = set(existing_unique.get((t, tuple(ug)), set()))
        for i in range(n):
            pk = tuple(ncols[c][i] for c in tm.primary_key) if tm.primary_key else ()
            ok = True
            if tm.primary_key and pk in seen_pk:
                ok = False
            if ok:
                for ug in tm.unique_groups:
                    u = tuple(ncols[c][i] for c in ug)
                    if u in seen_unique[tuple(ug)]:
                        ok = False
                        break
            if ok:
                if tm.primary_key:
                    seen_pk.add(pk)
                for ug in tm.unique_groups:
                    seen_unique[tuple(ug)].add(tuple(ncols[c][i] for c in ug))
                keep.append(i)
        out_rows[t] = {c: [ncols[c][i] for i in keep] for c in safe_cols}
        stats['added'][t] = len(keep)
        stats['skipped'][t] = n - len(keep)
        for c in list(generated_ids):
            if c[0] == t and c[1] in ncols:
                generated_ids[c] = [ncols[c[1]][i] for i in keep]
                all_pk_values[c] = all_pk_values.get(c, []) + generated_ids[c]
    return out_rows, stats
