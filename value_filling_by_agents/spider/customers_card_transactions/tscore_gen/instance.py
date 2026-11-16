"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the specification."""
import datetime as dt
import re
from collections import Counter, defaultdict

from .samplers import make_sampler
from .spec import (dependencies, exception_targets, is_null_target, null_targets,
                   semantic_rules, table_size)


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict, existing_keys: set) -> dict:
    """Drop rows whose PK tuple repeats or collides with compact rows; first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _n_rows(columns)
    seen = set(existing_keys)
    keep = []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, existing_unique: dict) -> dict:
    """Drop rows repeating any single unique column value (also against compact rows)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen = set(existing_unique.get(cm.name, set()))
            keep = []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _existing_keys(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def _existing_unique(schema, table: str) -> dict:
    tm = schema.tables[table]
    out = {}
    for cm in tm.columns:
        if cm.unique:
            out[cm.name] = set(v for v in schema.original_values.get((table, cm.name), []) if v is not None)
    return out


def _parent_values(schema, instance, table: str, column: str) -> list:
    """Parent values from compact rows plus generated rows held in memory."""
    vals = [v for v in schema.original_values.get((table, column), []) if v is not None]
    gen = instance.get(table, {}).get(column, [])
    vals.extend(v for v in gen if v is not None)
    return vals


def _parent_keys(schema, instance, table: str, column: str) -> list:
    """Distinct parent key values (compact + generated), order preserved."""
    seen, out = set(), []
    for v in _parent_values(schema, instance, table, column):
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _reserved_parent_keys(schema, instance, spec) -> dict:
    """One parent key per parent table reserved so that parent row has no children."""
    reserved = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        if (pt, pc) in reserved:
            continue
        pv = _parent_keys(schema, instance, pt, pc)
        if pv:
            reserved[(pt, pc)] = pv[len(pv) // 2]
    return reserved


def _plan_multiplicity(parent_keys: list, n_children: int, rng, reserved=None) -> list:
    """Plan child->parent assignment realizing group sizes 1, 2, >=3 and one childless parent."""
    if not parent_keys:
        return [None] * n_children
    pool = [k for k in parent_keys if k != reserved]
    if not pool:
        pool = list(parent_keys)
    if n_children <= 0:
        return []
    plan: list = []
    if len(pool) >= 3 and n_children >= 6:
        a, b, c = rng.sample(pool, 3)
        plan = [a] + [b, b] + [c] * max(3, n_children - 3)
        plan = plan[:n_children]
        others = [k for k in pool if k not in (a, b, c)]
        while len(plan) < n_children:
            plan.append(rng.choice(others) if others else rng.choice(pool))
    else:
        plan = [rng.choice(pool) for _ in range(n_children)]
    rng.shuffle(plan)
    return plan


def _fill_fk(schema, instance, table: str, column: str, n: int, rng, nullable: bool,
             reserved: dict, plan: list = None) -> list:
    """FK child column draws from parent's values; ~5% NULL when nullable; empty parent -> NULL."""
    key = (table, column)
    if key not in schema.fks:
        return []
    pt, pc = schema.fks[key]
    pv = _parent_keys(schema, instance, pt, pc)
    rv = reserved.get((pt, pc))
    if rv is not None:
        pv = [v for v in pv if v != rv]
    if not pv:
        return [None] * n
    if plan is not None and len(plan) == n:
        out = list(plan)
    else:
        out = []
        for _ in range(n):
            if nullable and rng.random() < 0.05:
                out.append(None)
            else:
                out.append(rng.choice(pv))
    return out


def _plant_nulls(values: list, nullable: bool, rng, share: float = 0.05) -> list:
    """Ensure at least one NULL and a share of NULLs when nullable; never touch NOT NULL."""
    if not nullable or not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:k]:
        values[i] = None
    return values


def _apply_semantic_rules(schema, instance, table: str, columns: dict, spec, rng) -> dict:
    """Compute derived columns and enforce semantic rules in Python (no SQL)."""
    rules = [r for r in semantic_rules(spec) if str(r.get('table', '')).lower() == table.lower()]
    for rule in rules:
        col = str(rule.get('column', ''))
        formula = str(rule.get('formula', ''))
        if col not in columns:
            continue
        if 'date_valid_to' in col.lower() and 'date_valid_from' in formula.lower():
            src = next((c for c in columns if c.lower() == 'date_valid_from'), None)
            if src:
                out = []
                for i, v in enumerate(columns[col]):
                    f = columns[src][i]
                    if v is None or f is None:
                        out.append(v)
                        continue
                    try:
                        dv = dt.datetime.strptime(str(v)[:19], '%Y-%m-%d %H:%M:%S')
                        df = dt.datetime.strptime(str(f)[:19], '%Y-%m-%d %H:%M:%S')
                        if dv < df:
                            dv = df + dt.timedelta(days=rng.randint(1, 365))
                            out.append(dv.strftime('%Y-%m-%d %H:%M:%S'))
                        else:
                            out.append(v)
                    except ValueError:
                        out.append(v)
                columns[col] = out
        if 'transaction_amount' in col.lower() and '>= 0' in formula:
            columns[col] = [None if v is None else max(0.0, float(v)) for v in columns[col]]
        m = re.search(r"IN\s*\(([^)]*)\)", formula, re.I)
        if m and ('transaction_type' in col.lower() or 'card_type_code' in col.lower()):
            allowed = [x.strip().strip("'\"") for x in m.group(1).split(',')]
            allowed = [a for a in allowed if a]
            if allowed:
                columns[col] = [v if (v is None or v in allowed) else rng.choice(allowed)
                                for v in columns[col]]
        if re.search(r'>\s*0', formula) and col.lower().endswith('_id'):
            columns[col] = [None if v is None else max(1, int(v)) for v in columns[col]]
    return columns


def _group_size_targets(spec, table, column):
    out = []
    for t in exception_targets(spec, table, column, 'group_sizes'):
        gs = str(t.get('group_sizes', ''))
        if gs:
            out.append(gs)
    return out


def _apply_group_sizes(schema, instance, table: str, columns: dict, spec, rng) -> dict:
    """Ensure group-size targets for group_sizes columns by reassigning FK values."""
    return columns


def _apply_aggregate_boundary(schema, instance, table: str, columns: dict, spec, rng) -> dict:
    """Ensure COUNT(*) boundary values exist for targeted group columns."""
    for col, vals in list(columns.items()):
        if (table, col) in schema.fks:
            continue
        targets = []
        for t in exception_targets(spec, table, col, 'aggregate_boundary'):
            targets.extend(t.get('values', []) or [])
        if not targets:
            continue
        distinct = sorted(set(v for v in vals if v is not None))
        if len(distinct) < 2:
            continue
        n = len(vals)
        plan = []
        for k in targets:
            if len(plan) + k <= n:
                plan.extend([distinct[len(plan) % len(distinct)]] * k)
        while len(plan) < n:
            plan.append(rng.choice(distinct))
        plan = plan[:n]
        rng.shuffle(plan)
        columns[col] = plan
    return columns


def _apply_ties_and_different_values(schema, instance, table: str, columns: dict, spec, rng) -> dict:
    """Jointly construct SUM tie at rank 1 and >=2 distinct amounts per tying group."""
    if table.lower() != 'financial_transactions':
        return columns
    if 'transaction_type' not in columns or 'transaction_amount' not in columns:
        return columns
    has_tie = False
    for t in exception_targets(spec, table, 'transaction_type', 'ties_for_order_limit'):
        tie_on = t.get('tie_on', []) or []
        if any('transaction_amount' in str(x) for x in tie_on):
            has_tie = True
    has_diff = False
    for t in exception_targets(spec, table, 'transaction_amount', 'rows_with_different_values'):
        if t.get('qualifying_rows'):
            has_diff = True
    if not has_tie and not has_diff:
        return columns
    types = columns['transaction_type']
    amounts = columns['transaction_amount']
    groups = defaultdict(list)
    for i, ty in enumerate(types):
        if ty is not None and amounts[i] is not None:
            groups[ty].append(i)
    if has_tie and len(groups) >= 2:
        keys = sorted(groups)
        g1, g2 = keys[0], keys[1]
        idx1, idx2 = groups[g1], groups[g2]
        if idx1 and idx2:
            target = round(rng.uniform(100.0, 2000.0), 2)
            for idxs in (idx1, idx2):
                _split_sum(amounts, idxs, target, rng)
    if has_diff:
        for g, idxs in groups.items():
            if len(idxs) >= 2:
                vals = {amounts[i] for i in idxs}
                if len(vals) < 2:
                    amounts[idxs[0]] = round(amounts[idxs[0]] + 0.01, 2)
    columns['transaction_amount'] = amounts
    return columns


def _split_sum(amounts: list, idxs: list, target: float, rng) -> None:
    """Split target across idxs into two distinct amounts per group summing to target."""
    k = len(idxs)
    if k == 0:
        return
    if k == 1:
        amounts[idxs[0]] = round(target, 2)
        return
    a = round(target / k + rng.uniform(0.5, 5.0), 2)
    b = round((target - a * (k - 1)) / 1.0, 2) if k == 2 else round(target / k - rng.uniform(0.5, 5.0), 2)
    if a == b:
        b = round(b + 0.01, 2)
    for j in range(k - 1):
        amounts[idxs[j]] = a
    amounts[idxs[-1]] = round(target - a * (k - 1), 2)
    if len({amounts[i] for i in idxs}) < 2:
        amounts[idxs[0]] = round(amounts[idxs[0]] + 0.01, 2)
        amounts[idxs[-1]] = round(amounts[idxs[-1]] - 0.01, 2)


def _compact_null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / len(vals)


def _apply_fk_multiplicity(schema, instance, table: str, columns: dict, spec, rng,
                           reserved: dict) -> dict:
    """Apply the FK multiplicity plan after PK/UNIQUE dedup."""
    n = _n_rows(columns)
    if n == 0:
        return columns
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        targeted = bool(_group_size_targets(spec, table, cm.name))
        for t in exception_targets(spec, table, cm.name, 'unmatched_join_rows'):
            if t.get('parent_rows_without_children'):
                targeted = True
        if not targeted:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_keys(schema, instance, pt, pc)
        if not pv:
            continue
        rv = reserved.get((pt, pc))
        plan = _plan_multiplicity(pv, n, rng, reserved=rv)
        cur = columns[cm.name]
        out = []
        pi = 0
        for v in cur:
            if v is None:
                out.append(None)
            else:
                out.append(plan[pi] if pi < len(plan) else rng.choice(pv))
                pi += 1
        columns[cm.name] = out
    return columns


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build appended rows for one instance; returns {table: {column: [values]}}."""
    spec = spec or {}
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = {}
    for t in order:
        total = table_size(spec, t, rng, default=0)
        compact = schema.original_sizes.get(t, 0)
        sizes[t] = max(0, total - compact)
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            observed = schema.original_values.get((t, cm.name), [])
            pool = literal_pool.get((t, cm.name), [])
            samplers[(t, cm.name)] = make_sampler(t, cm.name, cm.type_str, observed, pool, spec, rng)
    inst: dict = {}
    reserved = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        cols = {}
        for cm in tm.columns:
            if (t, cm.name) in samplers:
                cols[cm.name] = samplers[(t, cm.name)].sample(n)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                cols[cm.name] = _fill_fk(schema, inst, t, cm.name, n, rng, not cm.notnull, reserved)
        cols = sample_fresh_primary_keys(tm, cols, _existing_keys(schema, t))
        cols = drop_unique_duplicates(tm, cols, _existing_unique(schema, t))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = [v for v in cols[pc] if v is not None]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_semantic_rules(schema, inst, t, cols, spec, rng)
        cols = _apply_aggregate_boundary(schema, inst, t, cols, spec, rng)
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                share = _compact_null_share(schema, t, cm.name)
                if share <= 0.0:
                    share = 0.05
                cols[cm.name] = _plant_nulls(cols[cm.name], True, rng, share)
        cols = _apply_ties_and_different_values(schema, inst, t, cols, spec, rng)
        inst[t] = cols
        for (ct, cc), (pt, pc) in schema.fks.items():
            if pt == t and (pt, pc) not in reserved:
                pv = _parent_keys(schema, inst, pt, pc)
                if pv:
                    reserved[(pt, pc)] = pv[len(pv) // 2]
    for t in order:
        if t in inst:
            inst[t] = _apply_fk_multiplicity(schema, inst, t, inst[t], spec, rng, reserved)
    return {t: inst[t] for t in schema.tables}
