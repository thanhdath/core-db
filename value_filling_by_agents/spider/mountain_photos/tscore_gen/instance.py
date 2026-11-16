"""Random instance construction (fuzz/fuzz.py:83-196)."""
import re
from collections import Counter

from .spec import is_null_target, table_size
from .values import _init_sampler, planted_values


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


def _parent_keys(schema, instance: dict, pt: str, pc: str) -> list:
    """Compact parent values (from original_values) + generated parent values, in memory."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _reserved_parent_keys(schema, instance: dict, pt: str, pc: str) -> set:
    """One parent key reserved so it is never referenced by a generated child row (guaranteed unmatched parent)."""
    gen = [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    if gen:
        return {gen[-1]}
    comp = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    if comp:
        return {comp[-1]}
    return set()


def _shape_fk_counts(n: int, rng) -> list:
    """A multiset of group sizes (summing to n) containing 1, 2 and >= 3 when possible."""
    if n <= 0:
        return []
    plan = []
    if n >= 6:
        plan = [1, 2, 3]
        rest = n - 6
        while rest > 0:
            k = min(rest, rng.choice((1, 1, 2, 3)))
            plan.append(k)
            rest -= k
    elif n >= 3:
        plan = [1, 2]
        rest = n - 3
        while rest > 0:
            plan.append(1)
            rest -= 1
    else:
        plan = [1] * n
    rng.shuffle(plan)
    return plan


def _fk_column_with_shape(parent_keys: list, n: int, rng, reserved: set) -> list:
    """Draw n FK values from parent_keys (excluding reserved) so that the group-size multiset contains 1, 2 and >= 3
    (when enough distinct parents exist)."""
    pool = [v for v in parent_keys if v not in reserved]
    if not pool:
        return [None] * n
    sizes = _shape_fk_counts(n, rng)
    out = []
    for k in sizes:
        v = rng.choice(pool)
        out.extend([v] * k)
    rng.shuffle(out)
    return out[:n]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec=None) -> dict:
    """FK child columns draw from the parent's compact+generated values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_keys(schema, instance, pt, pc)
        reserved = _reserved_parent_keys(schema, instance, pt, pc)
        if pv:
            col = _fk_column_with_shape(pv, n, rng, reserved)
        else:
            col = [None] * n
        if spec is not None and is_null_target(spec, table, cm.name) and n > 0:
            col[rng.randrange(n)] = None
        out[cm.name] = col
    return out


def _fresh_pk_values(schema, table: str, column: str, n: int, rng, is_int: bool) -> list:
    """Fresh primary-key values that do not collide with the compact rows."""
    used = {v for v in schema.original_values.get((table, column), []) if v is not None}
    if is_int:
        start = (max(used) + 1) if used else 1
        return [start + i for i in range(n)]
    out, k = [], 0
    while len(out) < n:
        v = 'k%d_%d' % (rng.randrange(10 ** 6), k)
        k += 1
        if v not in used:
            out.append(v)
    return out


def _apply_formula(spec, table: str, column: str, values: list) -> list:
    """Enforce a simple formula by construction (Python, never SQL)."""
    if spec is None:
        return values
    f = spec.get('formulas', {}).get('%s.%s' % (table, column))
    if not f:
        return values
    m = re.fullmatch(r'\s*\w+\s*(>=|>)\s*(-?\d+(?:\.\d+)?)\s*', f)
    if m:
        op, c = m.group(1), float(m.group(2))
        out = []
        for v in values:
            if v is None:
                out.append(v)
                continue
            x = float(v)
            if op == '>' and not x > c:
                x = c + 1.0
            elif op == '>=' and not x >= c:
                x = c
            out.append(int(x) if isinstance(v, int) else x)
        return out
    m = re.fullmatch(r"\s*\w+\s+IN\s*\((.*)\)\s*", f, re.I)
    if m:
        allowed = [s.strip().strip("'\"") for s in m.group(1).split(',')]
        return [v if (v is None or v in allowed) else allowed[0] for v in values]
    return values


def _plant_values(spec, table: str, column: str, values: list) -> list:
    """Write each planted value (boundary variant / literal-pool value) into the first generated rows of the column,
    so it is guaranteed to appear (round-1 review)."""
    pv = planted_values(spec, table, column)
    if not pv or not values:
        return values
    out = list(values)
    for i, v in enumerate(pv):
        if i >= len(out):
            break
        out[i] = v
    return out


def _group_size_mix(spec, table: str, column: str, values: list, rng) -> list:
    """Ensure groups of size 1, 2 and >= 3 exist for a grouped column (by construction)."""
    if spec is None or not spec.get('group_size_mix') or not values:
        return values
    n = len(values)
    if n < 6:
        return values
    pool = list(dict.fromkeys(values))
    if len(pool) < 3:
        return values
    a, b, c = rng.sample(pool, 3)
    plan = [a, b, b, c, c, c]
    out = list(values)
    for i, v in enumerate(plan):
        out[i] = v
    return out


def _tie_order(spec, table: str, column: str, values: list, rng) -> list:
    """Ensure at least two rows share a value at rank 1 for ORDER BY (ties)."""
    if spec is None or not spec.get('tie_order') or len(values) < 2:
        return values
    out = list(values)
    out[1] = out[0]
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specified table sizes (jittered) when the specification names the table, else the upstream uniform/level
    choice (fuzz.py:83-110)."""
    sizes = {}
    named = set((spec or {}).get('table_sizes', {}))
    if named:
        for lvl in schema.table_order:
            for t in lvl:
                if t in named:
                    sizes[t] = table_size(spec, t, rng)
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
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _combined_counts(schema, instance: dict, pt: str, pc: str, child: str, child_col: str) -> Counter:
    """COUNT(*) per parent key over compact+generated rows, computed in Python."""
    cnt: Counter = Counter()
    for v in schema.original_values.get((pt, pc), []):
        if v is not None:
            cnt[v] += 0
    for v in schema.original_values.get((child, child_col), []):
        if v is not None:
            cnt[v] += 1
    for v in instance.get(child, {}).get(child_col, []):
        if v is not None:
            cnt[v] += 1
    return cnt


def _verify_and_fix(schema, instance: dict, spec, rng) -> None:
    """Verify the combined instance meets group-size / tie / unmatched targets; adjust generated FK values in Python
    if a target is missing (round-1 review)."""
    if spec is None:
        return
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in instance or cc not in instance[ct]:
            continue
        col = instance[ct][cc]
        if not col:
            continue
        cnt = _combined_counts(schema, instance, pt, pc, ct, cc)
        sizes = set(cnt.values())
        if spec.get('group_size_mix'):
            need = []
            if 1 not in sizes:
                need.append(1)
            if 2 not in sizes:
                need.append(2)
            if not any(s >= 3 for s in sizes):
                need.append(3)
            if need:
                parents = [v for v in _parent_keys(schema, instance, pt, pc)
                           if v not in _reserved_parent_keys(schema, instance, pt, pc)]
                if parents:
                    idx = 0
                    for want in need:
                        v = rng.choice(parents)
                        for _ in range(want):
                            if idx < len(col):
                                col[idx] = v
                                idx += 1
        if spec.get('tie_order'):
            cnt = _combined_counts(schema, instance, pt, pc, ct, cc)
            vals = list(cnt.values())
            if len(vals) >= 2 and len(set(vals)) == len(vals):
                parents = [v for v in _parent_keys(schema, instance, pt, pc)
                           if v not in _reserved_parent_keys(schema, instance, pt, pc)]
                if len(parents) >= 2:
                    a, b = rng.sample(parents, 2)
                    for i, v in enumerate(col):
                        if v == a:
                            col[i] = b
                            break
        instance[ct][cc] = col


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) = the rows to append to the compact copy."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec=spec, table=t)
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for cm in tm.columns:
            if cm.pk_pos > 0 and cm.name in cols:
                is_int = 'int' in (cm.type_str or '').lower()
                cols[cm.name] = _fresh_pk_values(schema, t, cm.name, n, rng, is_int)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        for cm in tm.columns:
            if cm.name in cols:
                cols[cm.name] = _apply_formula(spec, t, cm.name, cols[cm.name])
                cols[cm.name] = _plant_values(spec, t, cm.name, cols[cm.name])
                cols[cm.name] = _group_size_mix(spec, t, cm.name, cols[cm.name], rng)
                cols[cm.name] = _tie_order(spec, t, cm.name, cols[cm.name], rng)
        inst[t] = cols
    _verify_and_fix(schema, inst, spec, rng)
    return {t: inst[t] for t in schema.tables}
