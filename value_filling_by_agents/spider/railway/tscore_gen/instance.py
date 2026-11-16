"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import re

from .values import make_column_sampler


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


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
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


def _spec_size(spec, table: str, rng) -> int:
    """Specification table size with a small per-instance jitter (0-230 rows cap)."""
    base = spec.table_size(table, 0) if spec is not None else 0
    if base <= 0:
        return 0
    jitter = rng.randint(-1, 2)
    return max(0, min(230, base + jitter))


def _enum_from_formula(formula: str):
    """Extract an IN (...) enum pool from a formula string."""
    m = re.search(r'\bin\s*\(([^)]*)\)', formula, re.I)
    if not m:
        return None
    items = re.findall(r"'((?:[^']|'')*)'", m.group(1))
    return [x.replace("''", "'") for x in items] if items else None


def _range_from_formula(formula: str):
    """Extract BETWEEN lo AND hi bounds (integers) from a formula string."""
    m = re.search(r'between\s+(-?\d+)\s+and\s+(-?\d+)', formula, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _glob_from_formula(formula: str):
    """Extract a GLOB pattern from a formula string."""
    m = re.search(r"glob\s+'([^']*)'", formula, re.I)
    return m.group(1) if m else None


def _like_variants(literals: list, variants: list) -> list:
    """Exact literal (without %) + near variants for LIKE/equality targets."""
    out = []
    for lit in literals:
        body = lit.replace('%', '')
        out.append(body)
    out.extend(variants)
    return out


def _comparison_variants(values: list) -> list:
    """Literal + one-step variants (case, trailing space, truncation)."""
    out = []
    for v in values:
        out.append(v)
        out.append(v.lower())
        out.append(v.upper())
        out.append(v + ' ')
        if len(v) > 1:
            out.append(v[:-1])
    return out


def _plant_group_sizes(n: int, rng) -> list:
    """Return a list of group labels of length n with groups of size 1, 2 and >= 3."""
    if n <= 0:
        return []
    labels = [0]
    if n >= 3:
        labels.extend([1, 1])
    if n >= 6:
        labels.extend([2, 2, 2])
    elif n == 5:
        labels.extend([2, 2])
    elif n == 4:
        labels.append(2)
    while len(labels) < n:
        labels.append(rng.randint(3, max(3, n)))
    rng.shuffle(labels)
    return labels[:n]


def _plant_duplicates(n: int, rng, pool_size: int) -> list:
    """Return indices into a pool of size ~0.6*n (duplicate share 20-50 %)."""
    if n <= 0:
        return []
    k = max(1, int(round(0.6 * n)))
    return [rng.randrange(k) for _ in range(n)]


def _plant_ties(n: int, rng, tie_rank: int) -> list:
    """Return a list of values with a tie at the given rank (1-based)."""
    if n <= 0:
        return []
    vals = list(range(1, n + 1))
    if 1 <= tie_rank <= n:
        vals[tie_rank - 1] = vals[max(0, tie_rank - 2)]
    return vals


def _make_hook(table: str, column: str, spec, rng, n: int, kind: str, is_pk: bool):
    """Build a spec_hook closure for a column, or None."""
    if spec is None:
        return None, {}
    patterns = spec.patterns(table, column)
    if not patterns:
        return None, {}
    planted = {}
    for p in patterns:
        pat = p.get('pattern')
        tgt = p.get('targets') or {}
        if pat in ('group_sizes', 'aggregate_boundary'):
            if is_pk:
                continue
            planted['group_labels'] = _plant_group_sizes(n, rng)
        elif pat == 'duplicates_for_distinct':
            planted['dup_idx'] = _plant_duplicates(n, rng, max(1, int(0.6 * n)))
        elif pat == 'ties_for_order_limit':
            ranks = tgt.get('tie_at_rank')
            if isinstance(ranks, list) and ranks:
                planted['tie_rank'] = int(ranks[0])
            elif isinstance(ranks, int):
                planted['tie_rank'] = ranks
            elif isinstance(ranks, str) and 'any' in ranks.lower():
                planted['tie_rank'] = None
            else:
                planted['tie_rank'] = max(1, n // 2)
        elif pat == 'like_near_variant':
            lits = tgt.get('literals') or []
            vars_ = tgt.get('variants') or []
            planted['like_variants'] = _like_variants(lits, vars_)
        elif pat == 'comparison_boundary':
            vals = tgt.get('values') or []
            planted['comparison_variants'] = _comparison_variants(vals)
    if not planted:
        return None, {}
    counter = {'i': 0}

    def hook(sampler):
        i = counter['i']
        counter['i'] += 1
        if 'dup_idx' in planted and kind == 'string':
            idx = planted['dup_idx'][i % len(planted['dup_idx'])]
            pool = sampler.elements or ['x']
            return pool[idx % len(pool)]
        if 'group_labels' in planted and kind == 'string':
            lab = planted['group_labels'][i % len(planted['group_labels'])]
            pool = sampler.elements or ['g']
            return pool[lab % len(pool)]
        if 'tie_rank' in planted and kind == 'number' and planted['tie_rank'] is not None:
            return planted['tie_rank']
        if 'like_variants' in planted and kind == 'string':
            return rng.choice(planted['like_variants'])
        if 'comparison_variants' in planted and kind == 'string':
            return rng.choice(planted['comparison_variants'])
        return None

    return hook, planted


def _column_kind(column) -> str:
    t = (column.type_str or '').lower()
    if any(k in t for k in ('int', 'float', 'double', 'decimal', 'numeric', 'number', 'real', 'year')):
        return 'number'
    if 'date' in t or 'timestamp' in t:
        return 'date'
    if t == 'time':
        return 'time'
    if 'bool' in t or 'bit' in t:
        return 'bool'
    return 'string'


def _build_sampler(table: str, column, spec, literal_pool, original_values, p, rng, n_pk, n_rows):
    """Build a sampler for one column, wiring specification patterns and formulas."""
    kind = _column_kind(column)
    is_pk = column.pk_pos > 0
    hook, planted = _make_hook(table, column.name, spec, rng, n_rows, kind, is_pk)
    kw = {'spec_hook': hook}
    if spec is not None:
        for formula in spec.column_formulas(table, column.name):
            enum = _enum_from_formula(formula)
            if enum:
                kw['enum_pool'] = enum
            rng_b = _range_from_formula(formula)
            if rng_b:
                kw['range_bounds'] = rng_b
            glob = _glob_from_formula(formula)
            if glob:
                kw['glob_pattern'] = glob
    if spec is not None:
        for ptn in spec.patterns(table, column.name):
            pat = ptn.get('pattern')
            tgt = ptn.get('targets') or {}
            if pat == 'like_near_variant':
                kw['like_variants'] = _like_variants(tgt.get('literals') or [], tgt.get('variants') or [])
            elif pat == 'comparison_boundary':
                kw['comparison_variants'] = _comparison_variants(tgt.get('values') or [])
            elif pat == 'ties_for_order_limit':
                ranks = tgt.get('tie_at_rank')
                if isinstance(ranks, list) and ranks:
                    kw['tie_values'] = [int(ranks[0])]
                elif isinstance(ranks, int):
                    kw['tie_values'] = [ranks]
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    max_l0 = float('inf')
    if rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    return make_column_sampler(column, els, p, max_l0, rng, **kw), planted


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build the *generated* rows for one instance (fuzz.py:111-196 + specification)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        if spec is not None and spec.sizes:
            size = {t: _spec_size(spec, t, rng) for t in order}
        else:
            size = choose_table_sizes(schema, rng)
    combined: dict = {}
    for t, tm in schema.tables.items():
        for c in tm.columns:
            combined[(t, c.name)] = list(schema.original_values.get((t, c.name), []))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            inst[t] = {c.name: [] for c in tm.columns}
            continue
        cols: dict = {}
        planted_by_col: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            sampler, planted = _build_sampler(t, cm, spec, literal_pool.get((t, cm.name), []),
                                              schema.original_values.get((t, cm.name), []), p, rng,
                                              len(tm.primary_key), n)
            vals = [sampler.sample() for _ in range(n)]
            if not cm.notnull and cm.pk_pos == 0:
                share = 0.0
                if spec is not None and spec.has_pattern(t, cm.name, 'null_rows'):
                    share = 0.15
                elif spec is not None and spec.is_null_target(t, cm.name):
                    share = 0.10
                if share > 0:
                    k = max(1, int(round(share * n)))
                    idxs = rng.sample(range(n), min(k, n))
                    for i in idxs:
                        vals[i] = None
            cols[cm.name] = vals
            planted_by_col[cm.name] = planted
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            pv = [v for v in (combined.get((pt, pc)) or []) if v is not None]
            planted = planted_by_col.get(cm.name) or {}
            labels = planted.get('group_labels')
            if pv:
                if labels is not None:
                    fk_vals = [pv[lab % len(pv)] for lab in labels]
                else:
                    fk_vals = [rng.choice(pv) for _ in range(n)]
            else:
                fk_vals = [None] * n
            if not cm.notnull and cm.pk_pos == 0:
                share = 0.10
                if spec is not None and spec.is_null_target(t, cm.name):
                    share = 0.10
                k = max(1, int(round(share * n)))
                idxs = rng.sample(range(n), min(k, n))
                for i in idxs:
                    fk_vals[i] = None
            cols[cm.name] = fk_vals
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols.get(pc, [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
        for cm in tm.columns:
            combined[(t, cm.name)] = combined.get((t, cm.name), []) + list(cols.get(cm.name, []))
    return inst
