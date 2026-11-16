"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt
import re

from .spec import load_spec
from .values import _init_sampler

_DATE_RE = re.compile(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})')


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


def _parent_pool(schema, instance, parent, parent_col):
    """The parent's key values: compact rows plus generated rows, in memory."""
    vals = []
    for v in schema.original_values.get((parent, parent_col), []):
        if v is not None:
            vals.append(v)
    for v in instance.get(parent, {}).get(parent_col, []):
        if v is not None:
            vals.append(v)
    return vals


def _spec_dependencies(spec: dict) -> dict:
    """Map (child_table, child_col) -> (parent_table, parent_col) from the spec."""
    out = {}
    for d in spec.get('dependencies') or []:
        child = str(d.get('child', ''))
        parent = str(d.get('parent', ''))
        if '.' not in child or '.' not in parent:
            continue
        ct, cc = child.split('.', 1)
        pt, pc = parent.split('.', 1)
        out[(ct.upper(), cc.upper())] = (pt.upper(), pc.upper())
    return out


def _fk_map(schema, spec: dict) -> dict:
    """Declared FKs plus spec dependencies, keyed by (TABLE, COL) upper-case."""
    out = {}
    for (ct, cc), (pt, pc) in schema.fks.items():
        out[(ct.upper(), cc.upper())] = (pt, pc)
    for k, v in _spec_dependencies(spec).items():
        out.setdefault(k, v)
    return out


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec: dict,
                                   literal_pool: dict, fk_map: dict) -> dict:
    """FK child columns draw from the parent's key pool (compact + generated) with NULL by the NULL rule."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table.upper(), cm.name.upper())
        if key not in fk_map:
            continue
        pt, pc = fk_map[key]
        pv = _parent_pool(schema, instance, pt, pc)
        if pv:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
        else:
            out[cm.name] = [None] * n
    return out


def _choose_enum_sizes(schema, spec, rng) -> dict:
    """Sizes from the specification (table_sizes_per_instance) with a random variation."""
    base = spec.get('table_sizes', {})
    sizes = {}
    for t in schema.tables:
        n = int(base.get(t.upper(), 0))
        if n > 0:
            n = max(1, n + rng.randint(-max(1, n // 5), max(1, n // 5)))
        sizes[t] = n
    return sizes


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Uniform rand_lin sizes w.p."""
    spec = spec or load_spec()
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


def _observed_null_share(schema, table, col) -> float:
    """NULL share of the observed compact values (0.0 when the column is empty)."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _apply_null_rule(schema, values: dict, spec: dict, rng, fk_map: dict) -> dict:
    """Apply the NULL rule: every nullable non-PK column gets at least one NULL row and generated rows with non-NULL
    values; the share follows the compact database's observed share (or the specification's share, when a target
    is given)."""
    null_targets = set(spec.get('null_targets', []))
    null_shares = spec.get('null_shares', {})
    default_share = spec.get('null_share', 0.15)
    for table, t in schema.tables.items():
        cols = values.get(table, {})
        n = len(next(iter(cols.values()))) if cols else 0
        if n == 0:
            continue
        for cm in t.columns:
            if cm.name not in cols:
                continue
            if cm.notnull or cm.pk_pos > 0:
                continue
            key = '%s.%s' % (table.upper(), cm.name.upper())
            is_fk = (table.upper(), cm.name.upper()) in fk_map
            if is_fk and key not in null_targets and key not in null_shares:
                continue
            if key in null_shares:
                share = null_shares[key]
            else:
                obs = _observed_null_share(schema, table, cm.name)
                share = obs if obs > 0 else default_share
            if key in null_targets:
                share = max(share, null_shares.get(key, default_share))
            k = max(1, int(round(share * n)))
            k = min(k, n)
            idxs = rng.sample(range(n), k)
            for idx in idxs:
                cols[cm.name][idx] = None
    return values


def _parse_date(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        m = _DATE_RE.match(v)
        if m:
            try:
                return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


def _enforce_formulas(schema, values: dict, spec: dict, rng) -> dict:
    """Enforce simple column-vs-column formulas (e.g. EMP_HIREDATE > EMP_DOB) by resampling the dependent column in
    Python; NULL operands are left alone."""
    for f in spec.get('formulas', []):
        formula = (f.get('formula') or '').upper()
        m = re.match(r'\s*([A-Z_]\w*)\s*>\s*([A-Z_]\w*)\s*$', formula)
        if not m:
            continue
        left, right = m.group(1), m.group(2)
        table = f.get('table', '').upper()
        cols = values.get(table)
        if not cols or left not in cols or right not in cols:
            continue
        lv, rv = cols[left], cols[right]
        for i in range(len(lv)):
            a, b = _parse_date(lv[i]), _parse_date(rv[i])
            if a is None or b is None:
                continue
            if not (a > b):
                new = b + dt.timedelta(days=rng.randint(365 * 18, 365 * 40))
                lv[i] = new.strftime('%Y-%m-%d')
    return values


def _enforce_ranges(schema, values: dict, spec: dict, rng) -> dict:
    """Clamp numeric columns to the specification's ranges (e.g. STU_HRS >= 0)."""
    for key, rng_spec in spec.get('ranges', {}).items():
        table, col = key.split('.', 1)
        cols = values.get(table)
        if not cols or col not in cols:
            continue
        lo, hi = (list(rng_spec) + [None, None])[:2]
        vals = cols[col]
        for i, v in enumerate(vals):
            if v is None:
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if lo is not None and x < lo:
                x = lo
            if hi is not None and x > hi:
                x = hi
            vals[i] = int(x) if isinstance(v, int) else x
    return values


def _apply_group_sizes(schema, values: dict, spec: dict, rng, fk_map: dict) -> dict:
    """Make the group-size distribution of a column follow the specification (1, 2 and >= 3) by duplicating values
    from the observed pool."""
    for key, sizes in spec.get('group_sizes', {}).items():
        table, col = key.split('.', 1)
        cols = values.get(table)
        if not cols or col not in cols:
            continue
        tm = schema.tables.get(table)
        if tm is None:
            continue
        cm = next((c for c in tm.columns if c.name.upper() == col), None)
        if cm is None:
            continue
        if cm.pk_pos > 0 or (table.upper(), col) in fk_map:
            continue
        vals = cols[cm.name]
        n = len(vals)
        if n == 0:
            continue
        pool = [v for v in schema.original_values.get((table, cm.name), []) if v is not None]
        if not pool:
            pool = [v for v in vals if v is not None]
        if not pool:
            continue
        target = []
        i = 0
        while len(target) < n:
            target.append(sizes[i % len(sizes)])
            i += 1
        out = []
        for g in target:
            v = rng.choice(pool)
            out.extend([v] * g)
        cols[cm.name] = out[:n]
    return values


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196)."""
    spec = spec or load_spec()
    fk_map = _fk_map(schema, spec)
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t.upper(), cm.name.upper()) not in fk_map:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key), spec=spec)
    if size is None:
        size = _choose_enum_sizes(schema, spec, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec, literal_pool, fk_map))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = fk_map.get((t.upper(), cm.name.upper()), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    inst = _apply_null_rule(schema, inst, spec, rng, fk_map)
    inst = _apply_group_sizes(schema, inst, spec, rng, fk_map)
    inst = _enforce_ranges(schema, inst, spec, rng)
    inst = _enforce_formulas(schema, inst, spec, rng)
    return {t: inst[t] for t in schema.tables}
