"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt

from .spec import spec_get
from .values import make_spec_sampler


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


def _parent_pool(instance: dict, pt: str, pc: str, region: str = None) -> list:
    """Parent rows (index list) usable for a composite FK draw."""
    parent = instance.get(pt, {})
    pvals = parent.get(pc) or []
    preg = parent.get('Region') or []
    idx = []
    for i, v in enumerate(pvals):
        if v is None:
            continue
        if region is not None:
            if i >= len(preg) or preg[i] != region:
                continue
        idx.append(i)
    if len(idx) > 1:
        idx = idx[:-1]
    return idx


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng, spec=None) -> dict:
    """FK child columns draw whole composite tuples from the parent (fuzz.py:31-35)."""
    region = spec_get(spec, 'superstore_region', {}).get(table) if spec else None
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pool = _parent_pool(instance, pt, pc, region)
        pvals = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [pvals[rng.choice(pool)] for _ in range(n)] if pool else [None] * n
    return out


def choose_table_sizes(schema, rng, spec=None) -> dict:
    """Specification sizes when given, else the generic rand_lin / level sizes (fuzz.py:83-110)."""
    sizes = {}
    spec_sizes = spec_get(spec, 'tables', {}) if spec else {}
    if spec_sizes:
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(spec_sizes.get(t, 0))
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


def _null_share(schema, table: str, column: str, spec) -> float:
    """NULL share: the compact database's share for the column, floored by the spec's null_share."""
    ov = schema.original_values.get((table, column), [])
    if ov:
        share = sum(1 for v in ov if v is None) / float(len(ov))
    else:
        share = 0.0
    floor = float(spec_get(spec, 'null_share', 0.02))
    return max(share, floor)


def _apply_null_rule(cols: dict, table: str, schema, spec, rng, protected: set) -> None:
    """NULL is a value to generate: at least one NULL row per nullable column."""
    targets = set(spec_get(spec, 'null_targets', []))
    for cm in schema.tables[table].columns:
        if cm.notnull or cm.pk_pos > 0 or cm.name not in cols:
            continue
        key = '%s.%s' % (table, cm.name)
        if key not in targets:
            continue
        n = len(cols[cm.name])
        if n == 0:
            continue
        share = _null_share(schema, table, cm.name, spec)
        k = max(1, int(round(share * n)))
        candidates = [i for i in range(n) if i not in protected]
        if not candidates:
            continue
        idx = rng.sample(candidates, min(k, len(candidates)))
        for i in idx:
            cols[cm.name][i] = None


def _enforce_semantics(cols: dict, table: str, spec, rng, protected: set) -> None:
    """Semantic rules by construction (Python only)."""
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return
    region = spec_get(spec, 'superstore_region', {}).get(table)
    if region and 'Region' in cols:
        for i in range(n):
            if cols['Region'][i] is not None:
                cols['Region'][i] = region
    if 'Ship Date' in cols and 'Order Date' in cols:
        for i in range(n):
            od, sd = cols['Order Date'][i], cols['Ship Date'][i]
            if od is None or sd is None:
                continue
            try:
                d0 = dt.date.fromisoformat(str(od))
                d1 = dt.date.fromisoformat(str(sd))
            except ValueError:
                continue
            if d1 < d0:
                cols['Ship Date'][i] = (d0 + dt.timedelta(days=rng.randint(0, 7))).isoformat()
    if 'Quantity' in cols:
        for i in range(n):
            v = cols['Quantity'][i]
            if v is None:
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                iv = 1
            cols['Quantity'][i] = min(14, max(1, iv))
    if 'Discount' in cols:
        for i in range(n):
            v = cols['Discount'][i]
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                fv = 0.0
            cols['Discount'][i] = min(1.0, max(0.0, fv))
    if 'Sales' in cols:
        for i in range(n):
            v = cols['Sales'][i]
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                fv = 0.0
            cols['Sales'][i] = max(0.0, fv)


def _plant_expression_boundary(cols: dict, table: str, spec, rng) -> set:
    """sales / (1 - discount) * quantity around the listed expression values."""
    eb = spec_get(spec, 'expr_boundary', {})
    if table not in eb:
        return set()
    if not all(c in cols for c in ('Sales', 'Discount', 'Quantity')):
        return set()
    n = len(cols['Sales'])
    targets = list(eb[table])
    planted = set()
    for j, target in enumerate(targets):
        if j >= n:
            break
        q = rng.randint(1, 14)
        d = rng.choice([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        s = float(target) * (1.0 - d) / q
        cols['Sales'][j] = round(max(0.0, s), 3)
        cols['Discount'][j] = d
        cols['Quantity'][j] = q
        planted.add(j)
    return planted


def _fresh_key_values(table: str, column: str, n: int, rng, spec, taken: set) -> list:
    """Fresh unique identifiers matching the observed format (never reused)."""
    fmt = spec_get(spec, 'key_formats', {}).get(table)
    out = []
    if fmt and fmt[0] == column:
        pattern = fmt[1]
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        while len(out) < n:
            if pattern == 'XX-NNNNN':
                v = '%s%s-%05d' % (rng.choice(letters), rng.choice(letters), rng.randint(0, 99999))
            elif pattern == 'XXX-XX-NNNNNNNN':
                v = '%s%s%s-%s%s-%08d' % (rng.choice(letters), rng.choice(letters), rng.choice(letters),
                                          rng.choice(letters), rng.choice(letters), rng.randint(0, 99999999))
            else:
                v = '%s-%d' % (column[:2].upper(), rng.randint(0, 99999))
            if v not in taken:
                taken.add(v)
                out.append(v)
        return out
    while len(out) < n:
        v = rng.randint(1, 100000)
        if v not in taken:
            taken.add(v)
            out.append(v)
    return out


def _plant_boundary(cols: dict, table: str, spec, rng) -> set:
    """comparison_boundary: plant each listed literal and one step on each side."""
    boundary = spec_get(spec, 'boundary', {})
    planted = set()
    for key, vals in boundary.items():
        t, c = key.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        seq = []
        for v in vals:
            seq.append(v)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                seq.extend([v - 1, v + 1])
        for j, v in enumerate(seq):
            if j >= n:
                break
            cols[c][j] = v
            planted.add(j)
    return planted


def _plant_ties(cols: dict, table: str, spec, rng) -> set:
    """ties_for_order_limit: plant at least two rows sharing the actual rank-k value."""
    ties = spec_get(spec, 'ties', {})
    planted = set()
    for k, (ranks, direction) in ties.items():
        t, c = k.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        try:
            ordered = sorted(vals, reverse=(direction.upper() == 'DESC'))
        except TypeError:
            continue
        for rank in ranks:
            if rank < 1 or rank > len(ordered):
                continue
            shared = ordered[rank - 1]
            holders = [i for i in range(n) if cols[c][i] == shared]
            need = 2 - len(holders)
            if need > 0:
                free = [i for i in range(n) if i not in holders]
                rng.shuffle(free)
                for i in free[:need]:
                    cols[c][i] = shared
                    holders.append(i)
            planted.update(holders)
    return planted


def _plant_duplicates(cols: dict, table: str, spec, rng) -> set:
    """duplicates_for_distinct: control the duplicate share explicitly."""
    dups = spec_get(spec, 'dup_share', {})
    planted = set()
    for key, (lo, hi) in dups.items():
        t, c = key.split('.', 1)
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        share = rng.uniform(float(lo), float(hi))
        k = max(2, int(round(share * n)))
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        dup = rng.choice(vals)
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[c][i] = dup
            planted.add(i)
    return planted


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one random instance (fuzz.py:111-196) following the specification."""
    spec = spec or {}
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                taken = set()
                for v in schema.original_values.get((t, cm.name), []):
                    if v is not None:
                        taken.add(v)
                cols[cm.name] = _fresh_key_values(t, cm.name, n, rng, spec, taken)
                continue
            s = make_spec_sampler(t, cm, spec, literal_pool.get((t, cm.name), []),
                                  schema.original_values.get((t, cm.name), []), rng, n)
            cols[cm.name] = [s.sample() for _ in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, spec))
        for dep in spec_get(spec, 'dependencies', []):
            ct, cc, pt, pc, copied = dep[0], dep[1], dep[2], dep[3], dep[4]
            if ct != t or cc not in cols:
                continue
            parent = inst.get(pt, {})
            pvals = parent.get(pc) or []
            index = {}
            for i, v in enumerate(pvals):
                if v is not None and v not in index:
                    index[v] = i
            for cp in copied:
                pcol = parent.get(cp) or []
                out = []
                for v in cols[cc]:
                    j = index.get(v)
                    out.append(pcol[j] if j is not None and j < len(pcol) else None)
                cols[cp] = out
        protected = _plant_expression_boundary(cols, t, spec, rng)
        protected |= _plant_boundary(cols, t, spec, rng)
        protected |= _plant_ties(cols, t, spec, rng)
        protected |= _plant_duplicates(cols, t, spec, rng)
        _enforce_semantics(cols, t, spec, rng, protected)
        _apply_null_rule(cols, t, schema, spec, rng, protected)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
