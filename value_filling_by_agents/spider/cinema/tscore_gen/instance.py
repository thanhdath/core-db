"""Random instance construction (fuzz/fuzz.py:83-196) implementing the generation specification."""
from .values import (NullSampler, make_column_sampler, like_variant_set, satisfies_rule)


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


def drop_unique_duplicates(table_meta, columns: dict, uniques=None) -> dict:
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
    if uniques:
        for tu in uniques:
            if not all(c in columns for c in tu):
                continue
            seen, keep = set(), []
            n = len(next(iter(columns.values())))
            for i in range(n):
                k = tuple(columns[c][i] for c in tu)
                if any(x is None for x in k) or k not in seen:
                    if not any(x is None for x in k):
                        seen.add(k)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_set=None, null_share=0.0) -> dict:
    """FK child columns draw from the parent's values (compact + generated) with replacement."""
    null_set = null_set or set()
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        if not pv:
            out[cm.name] = [None] * n
            continue
        col = [rng.choice(pv) for _ in range(n)]
        nullable = (table.lower(), cm.name.lower()) in null_set
        if nullable and n > 0:
            k = max(1, int(round(null_share * n)))
            idxs = rng.sample(range(n), min(k, n))
            for i in idxs:
                col[i] = None
        out[cm.name] = col
    return out


def choose_table_sizes(spec: dict, schema, rng) -> dict:
    """Spec sizes take precedence; otherwise fall back to upstream RandLins/levels (fuzz.py:83-110)."""
    sizes = {}
    if spec.get('table_size'):
        for t in schema.tables:
            sizes[t] = int(spec['table_size'].get(t.lower(), max(5, 8)))
        return sizes
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(s)
                s *= 4
    return sizes


def _pick_null_share(spec: dict, t: str, c: str, n: int) -> float:
    """Compact DB says 0.0; the interface says plant >=1 NULL, rare."""
    if n <= 0:
        return 0.0
    return max(1.0 / n, 0.0)


def _sampler_for_column(schema, spec, t: str, c: str, rng, null_target: bool, n: int = 1):
    """Build a per-instance column sampler from observed values, pool literals and spec rules."""
    cm = next((x for x in schema.tables[t].columns if x.name == c), None)
    if cm is None:
        return None
    key = (t.lower(), c.lower())
    original = schema.original_values.get((t, c), [])
    pool_vals = list(spec.get('boundary', {}).get(key, []))
    like_prefix = like_variant_set(spec, key) if key in spec.get('like', {}) else None

    enum_vals = spec.get('enum', {}).get(key)
    if enum_vals:
        base = list(dict.fromkeys(list(original) + list(enum_vals) + list(pool_vals)))
    else:
        base = list(dict.fromkeys(list(original) + list(pool_vals)))

    int_range = spec.get('int_range', {}).get(key)
    float_range = spec.get('float_range', {}).get(key)

    if key in spec.get('duplicate_targets', {}):
        dup_share = spec['duplicate_targets'][key]
        p = dup_share
        max_l0 = max(1, int(len(base) * (1 - dup_share)) if base else 1)
    else:
        p = 0.2
        max_l0 = float('inf')

    if not int_range and not float_range and pool_vals:
        numeric_pool = [v for v in pool_vals if isinstance(v, (int, float)) or
                        (isinstance(v, str) and v.replace('.', '', 1).lstrip('-').isdigit())]
        if numeric_pool:
            nums = [float(v) for v in numeric_pool]
            int_range = (int(min(nums)), int(max(nums)))

    s = make_column_sampler(cm, base, p, max_l0, rng,
                            int_range=int_range, float_range=float_range, like_prefix=like_prefix)
    for rule in spec.get('rule_by_key', {}).get(key, []):
        if hasattr(s, 'rules'):
            s.rules.append(rule)
    if null_target and not cm.notnull and cm.pk_pos == 0:
        return NullSampler(s, _pick_null_share(spec, t, c, n), rng)
    if cm.notnull or cm.pk_pos > 0:
        return _NotNullWrapper(s)
    return s


class _NotNullWrapper:
    """Reject NULL from the base sampler for NOT NULL / primary-key columns."""

    def __init__(self, base):
        self.base = base

    def sample(self):
        v = self.base.sample()
        if v is None:
            v = self.base.sample()
            while v is None:
                v = self.base.sample()
        return v


def _plant_null_and_apply_rules(col_values, cm, rule_list, nullable_planted):
    """Ensure rules hold by construction: NULL operands are kept, invalid values nudged to a policy value."""
    out = []
    for v in col_values:
        if v is None:
            out.append(None)
            continue
        if all(satisfies_rule(r, v) for r in rule_list):
            out.append(v)
            continue
        cand = None
        if rule_list:
            for delta in (1, -1, 2, -2, 5, -5, 10, -10, 100, -100):
                try:
                    cv = float(v) + delta
                except (TypeError, ValueError):
                    cand = None
                    break
                if int(cv) == cv:
                    cv = int(cv)
                if all(satisfies_rule(r, cv) for r in rule_list):
                    cand = cv
                    break
        if cand is None:
            for r in rule_list:
                ref = r.get('value')
                if r.get('kind') in ('gt', 'ge') and ref is not None:
                    cand = float(ref) + (1 if r.get('kind') == 'gt' else 0)
                    break
                if r.get('kind') == 'between' and ref:
                    cand = ref[1]
                    break
        out.append(cand if cand is not None else v)
    return out


def _plant_like_variants(vals, spec, key, rng):
    """Ensure the exact LIKE literal bodies and listed variants appear at least once, unmutated."""
    if key not in spec.get('like_columns_set', set()):
        return vals
    variants = like_variant_set(spec, key)
    if not variants or not vals:
        return vals
    positions = rng.sample(range(len(vals)), min(len(variants), len(vals)))
    for pos, v in zip(positions, variants):
        vals[pos] = v
    return vals


def _plant_boundary_values(vals, spec, key, rng):
    """Plant values equal to and one step from the listed boundary literals."""
    targets = spec.get('boundary_targets', {}).get(key)
    if not targets or not vals:
        return vals
    nums = []
    for b in targets:
        try:
            nums.append(int(b))
        except (TypeError, ValueError):
            continue
    if not nums:
        return vals
    planted = []
    for b in nums:
        planted.extend([b - 1, b, b + 1])
    positions = rng.sample(range(len(vals)), min(len(planted), len(vals)))
    for pos, v in zip(positions, planted):
        vals[pos] = v
    return vals


def _plant_group_sizes(vals, spec, key, rng):
    """Partition the generated values into groups of size 1, 2, and >= 3 (repeat values)."""
    if key not in spec.get('group_size_set', set()) or not vals:
        return vals
    n = len(vals)
    pool = [v for v in vals if v is not None]
    if not pool:
        return vals
    sizes = [1, 2, 3]
    total = sum(sizes)
    while total < n:
        sizes.append(3)
        total += 3
    out = []
    idx = 0
    for gs in sizes:
        if len(out) >= n:
            break
        take = min(gs, n - len(out))
        base = pool[idx % len(pool)]
        idx += 1
        out.extend([base] * take)
    if len(out) < n:
        out.extend(vals[len(out):])
    for i, v in enumerate(vals):
        if v is None and i < len(out):
            out[i] = None
    return out[:n]


def _plant_duplicates(vals, spec, key, rng):
    """Repeat values so the duplicate share (distinct / row count) falls in 20-50 %."""
    if key not in spec.get('duplicate_targets', {}) or not vals:
        return vals
    share = spec['duplicate_targets'][key]
    n = len(vals)
    target_distinct = max(1, int(round(share * n)))
    pool = [v for v in vals if v is not None]
    if not pool:
        return vals
    bases = pool[:target_distinct]
    out = []
    for i in range(n):
        out.append(bases[i % len(bases)])
    for i, v in enumerate(vals):
        if v is None and i < len(out):
            out[i] = None
    return out


def _plant_ties(vals, spec, key, rng):
    """Ensure at least two rows share the top value of the ORDER expression (DESC or ASC)."""
    if key not in spec.get('tie_targets', {}) or not vals:
        return vals
    direction = spec['tie_targets'][key].get('direction', 'DESC')
    non_null = [v for v in vals if v is not None]
    if len(non_null) < 2:
        return vals
    try:
        top = max(non_null) if 'DESC' in direction else min(non_null)
    except TypeError:
        return vals
    positions = [i for i, v in enumerate(vals) if v == top]
    if len(positions) >= 2:
        return vals
    candidates = [i for i, v in enumerate(vals) if v is not None and v != top]
    if len(candidates) < 2:
        return vals
    for i in rng.sample(candidates, 2):
        vals[i] = top
    return vals


def _plant_aggregate_boundary(vals, spec, key, rng):
    """For aggregate_boundary targets, ensure group counts take the listed values [1,2,3]."""
    if key not in spec.get('aggregate_boundary_targets', {}) or not vals:
        return vals
    n = len(vals)
    pool = [v for v in vals if v is not None]
    if not pool:
        return vals
    sizes = [1, 2, 3]
    total = sum(sizes)
    while total < n:
        sizes.append(3)
        total += 3
    out = []
    idx = 0
    for gs in sizes:
        if len(out) >= n:
            break
        take = min(gs, n - len(out))
        base = pool[idx % len(pool)]
        idx += 1
        out.extend([base] * take)
    if len(out) < n:
        out.extend(vals[len(out):])
    for i, v in enumerate(vals):
        if v is None and i < len(out):
            out[i] = None
    return out[:n]


def _build_values_for_table(schema, spec, t: str, n: int, rng):
    """Columns for table t, except FK columns (filled in later)."""
    tm = schema.tables[t]
    cols = {}
    null_targets = spec.get('null_set', set())
    for cm in tm.columns:
        if (t, cm.name) in schema.fks:
            continue
        key = (t.lower(), cm.name.lower())
        s = _sampler_for_column(schema, spec, t, cm.name, rng, key in null_targets, n)
        if s is None:
            continue
        vals = [s.sample() for _ in range(n)]
        rules = spec.get('rule_by_key', {}).get(key, [])
        vals = _plant_null_and_apply_rules(vals, cm, rules, True)
        vals = _plant_group_sizes(vals, spec, key, rng)
        vals = _plant_duplicates(vals, spec, key, rng)
        vals = _plant_aggregate_boundary(vals, spec, key, rng)
        vals = _plant_ties(vals, spec, key, rng)
        vals = _plant_boundary_values(vals, spec, key, rng)
        vals = _plant_like_variants(vals, spec, key, rng)
        if n > 0 and key in null_targets and not cm.notnull and cm.pk_pos == 0:
            if None not in vals:
                vals[rng.randrange(n)] = None
        elif not cm.notnull and cm.pk_pos == 0 and key not in null_targets:
            if n > 0 and None not in vals and rng.random() < 0.5:
                vals[rng.randrange(n)] = None
        cols[cm.name] = vals
    return cols


def _fill_primary_keys(schema, spec, t: str, cols: dict, n: int, rng, taken: dict):
    """Composite or single PK: use sequential integers for a single int PK (fresh against compact rows)."""
    tm = schema.tables[t]
    pk = tm.primary_key
    if not pk:
        return cols
    pk_cols = [next(c for c in tm.columns if c.name == name) for name in pk]
    if len(pk) == 1 and 'int' in (pk_cols[0].type_str or '').lower():
        start = 1
        for k in taken.get(t, []):
            if isinstance(k, int) and k >= start:
                start = k + 1
        cols[pk[0]] = list(range(start, start + n))
        return cols
    for cm in pk_cols:
        s = _sampler_for_column(schema, spec, t, cm.name, rng, False, n)
        vals = [s.sample() for _ in range(n)]
        fixed = []
        for v in vals:
            if v is None:
                v = s.sample()
                while v is None:
                    v = s.sample()
            fixed.append(v)
        cols[cm.name] = fixed
    return cols


def _dedupe_composite_pk(schema, t: str, cols: dict, n: int, rng, taken: dict):
    """Ensure the composite PK tuples are unique (dedupe before insert)."""
    tm = schema.tables[t]
    pk = tm.primary_key
    if not pk or len(pk) < 2:
        return cols
    seen = set()
    for k in taken.get(t, []):
        if isinstance(k, tuple):
            seen.add(k)
    keep = []
    for i in range(n):
        k = tuple(cols[c][i] for c in pk)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(cols, keep)


def _sample_composite_pk_jointly(schema, spec, t: str, n: int, rng, taken: dict, parent_pools: dict):
    """Sample distinct composite-PK tuples jointly against the taken set (compact + generated)."""
    tm = schema.tables[t]
    pk = tm.primary_key
    if not pk or len(pk) < 2:
        return None
    pools = []
    for c in pk:
        key = (t.lower(), c.lower())
        if (t, c) in schema.fks:
            pt, pc = schema.fks[(t, c)]
            pv = parent_pools.get(pt, {}).get(pc) or []
            pv = [v for v in pv if v is not None]
            if not pv:
                return None
            pools.append(pv)
        else:
            cm = next(x for x in tm.columns if x.name == c)
            s = _sampler_for_column(schema, spec, t, c, rng, False, n)
            vals = []
            for _ in range(max(n * 4, 20)):
                v = s.sample()
                if v is not None:
                    vals.append(v)
            if not vals:
                return None
            pools.append(vals)
    seen = set()
    for k in taken.get(t, []):
        if isinstance(k, tuple):
            seen.add(k)
    out = {c: [] for c in pk}
    attempts = 0
    max_attempts = max(n * 50, 500)
    while len(out[pk[0]]) < n and attempts < max_attempts:
        attempts += 1
        tup = tuple(rng.choice(p) for p in pools)
        if tup in seen:
            continue
        seen.add(tup)
        for c, v in zip(pk, tup):
            out[c].append(v)
    if len(out[pk[0]]) < n:
        return None
    return out


def _apply_post_fill_boundaries(schema, spec, t: str, cols: dict, rng):
    """Plant comparison_boundary values on PK/FK columns AFTER PK/FK filling (never overwritten)."""
    tm = schema.tables[t]
    for cm in tm.columns:
        key = (t.lower(), cm.name.lower())
        targets = spec.get('post_fill_boundary_targets', {}).get(key)
        if not targets or cm.name not in cols:
            continue
        vals = cols[cm.name]
        if not vals:
            continue
        nums = []
        for b in targets:
            try:
                nums.append(int(b))
            except (TypeError, ValueError):
                continue
        if not nums:
            continue
        planted = []
        for b in nums:
            planted.extend([b - 1, b, b + 1])
        positions = rng.sample(range(len(vals)), min(len(planted), len(vals)))
        for pos, v in zip(positions, planted):
            vals[pos] = v
        cols[cm.name] = vals
    return cols


def _coordinate_aggregate_ties(schema, spec, inst: dict, rng):
    """Coordinate film.Directed_by with schedule rows so at least two Directed_by groups share the top
    SUM(schedule.show_times_per_day) and top COUNT(*)."""
    key = ('film', 'directed_by')
    if key not in spec.get('aggregate_tie_targets', {}):
        return
    if 'film' not in inst or 'schedule' not in inst:
        return
    film_cols = inst['film']
    sched_cols = inst['schedule']
    if 'Directed_by' not in film_cols or 'Film_ID' not in film_cols:
        return
    if 'Film_ID' not in sched_cols or 'Show_times_per_day' not in sched_cols:
        return
    directed = film_cols['Directed_by']
    film_ids = film_cols['Film_ID']
    by_dir = {}
    for d, fid in zip(directed, film_ids):
        if d is None:
            continue
        by_dir.setdefault(d, []).append(fid)
    if len(by_dir) < 2:
        return
    dirs = sorted(by_dir.keys())
    d1, d2 = dirs[0], dirs[1]
    sched_fids = sched_cols['Film_ID']
    sched_times = sched_cols['Show_times_per_day']
    n_sched = len(sched_fids)
    if n_sched == 0:
        return
    def agg(d):
        fids = set(by_dir[d])
        total = 0
        cnt = 0
        for fid, tm in zip(sched_fids, sched_times):
            if fid in fids and tm is not None:
                total += tm
                cnt += 1
        return total, cnt
    target_sum = 10
    target_cnt = 2
    fids1 = by_dir[d1]
    fids2 = by_dir[d2]
    for i in range(min(target_cnt, n_sched)):
        sched_fids[i] = fids1[0]
        sched_times[i] = target_sum // target_cnt
    for i in range(target_cnt, min(2 * target_cnt, n_sched)):
        sched_fids[i] = fids2[0]
        sched_times[i] = target_sum // target_cnt
    sched_cols['Film_ID'] = sched_fids
    sched_cols['Show_times_per_day'] = sched_times


def build_random_instance(schema, literal_pool: dict, spec: dict, size, rng) -> dict:
    """Build one append-only random instance (compact rows preserved; generated rows returned)."""
    spec = spec or {}
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(spec, schema, rng)

    taken = {}
    for t, tm in schema.tables.items():
        if not tm.primary_key:
            continue
        if len(tm.primary_key) == 1:
            taken[t] = [v for v in schema.original_values.get((t, tm.primary_key[0]), []) if v is not None]
        else:
            cols = [schema.original_values.get((t, c), []) for c in tm.primary_key]
            if cols and all(cols):
                taken[t] = list(zip(*cols))

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = _build_values_for_table(schema, spec, t, n, rng)
        all_parent = {}
        for pt, ptm in schema.tables.items():
            all_parent[pt] = {}
            for cm in ptm.columns:
                compact = list(schema.original_values.get((pt, cm.name), []))
                gen = inst.get(pt, {}).get(cm.name, [])
                all_parent[pt][cm.name] = [x for x in compact + gen if x is not None]
        if len(tm.primary_key) >= 2:
            joint = _sample_composite_pk_jointly(schema, spec, t, n, rng, taken, all_parent)
            if joint is not None:
                for c, vals in joint.items():
                    cols[c] = vals
                n_actual = len(next(iter(joint.values())))
                for c in list(cols.keys()):
                    if c not in joint and len(cols[c]) > n_actual:
                        cols[c] = cols[c][:n_actual]
            else:
                fk_cols = fill_foreign_keys_consistently(all_parent, schema, t, n, rng,
                                                         spec.get('null_set', set()),
                                                         spec.get('null_share', 0.05))
                cols.update(fk_cols)
                cols = _dedupe_composite_pk(schema, t, cols, n, rng, taken)
        else:
            fk_cols = fill_foreign_keys_consistently(all_parent, schema, t, n, rng,
                                                     spec.get('null_set', set()),
                                                     spec.get('null_share', 0.05))
            cols.update(fk_cols)
            cols = _fill_primary_keys(schema, spec, t, cols, n, rng, taken)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols, schema.uniques.get(t))
        cols = _apply_post_fill_boundaries(schema, spec, t, cols, rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols.get(cm.name, [])]
        inst[t] = cols
    _coordinate_aggregate_ties(schema, spec, inst, rng)
    return inst
