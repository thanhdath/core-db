"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the specification."""
import datetime as dt

from . import spec
from .values import spec_sampler, _iso


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


def _parent_pool(instance: dict, schema, table: str, col: str) -> list:
    """Parent key pool: compact values (from schema.original_values) + generated values."""
    pt, pc = schema.fks[(table, col)]
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def _composite_parent_pool(instance: dict, schema, table: str, cols: list) -> list:
    """Joint pool of (parent_col_a, parent_col_b) tuples for a composite FK."""
    pt, pc = schema.fks[(table, cols[0])]
    pt2, pc2 = schema.fks[(table, cols[1])]
    if pt2 != pt:
        return []
    a = list(schema.original_values.get((pt, pc), []))
    b = list(schema.original_values.get((pt, pc2), []))
    pairs = list(zip(a, b))
    ga = instance.get(pt, {}).get(pc, [])
    gb = instance.get(pt, {}).get(pc2, [])
    pairs += list(zip(ga, gb))
    return [(x, y) for (x, y) in pairs if x is not None and y is not None]


def _is_composite_child(schema, table: str, col: str) -> bool:
    """True if (table, col) is the first column of a composite FK (handled jointly)."""
    if (table, col) not in schema.fks:
        return False
    pt, pc = schema.fks[(table, col)]
    for (t2, c2), (pt2, pc2) in schema.fks.items():
        if t2 == table and c2 != col and pt2 == pt and pc2 != pc:
            return True
    return False


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's final rows (compact or generated) or are NULL."""
    out = {}
    handled = set()
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name in handled:
            continue
        nullable = not cm.notnull and cm.pk_pos == 0
        if _is_composite_child(schema, table, cm.name):
            pt, pc = schema.fks[key]
            sib = None
            for (t2, c2), (pt2, pc2) in schema.fks.items():
                if t2 == table and c2 != cm.name and pt2 == pt and pc2 != pc:
                    sib = c2
                    break
            if sib is None:
                continue
            pairs = _composite_parent_pool(instance, schema, table, [cm.name, sib])
            a_vals, b_vals = [], []
            n_null = max(1, int(round(n * spec.NULL_FK_SHARE))) if nullable else 0
            null_idx = set(rng.sample(range(n), min(n_null, n))) if n_null else set()
            for i in range(n):
                if i in null_idx or not pairs:
                    a_vals.append(None)
                    b_vals.append(None)
                else:
                    x, y = rng.choice(pairs)
                    a_vals.append(x)
                    b_vals.append(y)
            out[cm.name] = a_vals
            out[sib] = b_vals
            handled.add(cm.name)
            handled.add(sib)
            continue
        pv = _parent_pool(instance, schema, table, cm.name)
        vals = []
        n_null = max(1, int(round(n * spec.NULL_FK_SHARE))) if nullable else 0
        null_idx = set(rng.sample(range(n), min(n_null, n))) if n_null else set()
        for i in range(n):
            if i in null_idx or not pv:
                vals.append(None)
            else:
                vals.append(rng.choice(pv))
        out[cm.name] = vals
        handled.add(cm.name)
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes with per-instance jitter (0-230 rows per table, or level x 4)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t)
        if base is None:
            base = 30 + int(rng.random() * 200)
        j = 0.8 + 0.4 * rng.random()
        sizes[t] = max(0, min(2500, int(base * j)))
    return sizes


def _apply_null_rule(table: str, cm, values: list, rng) -> list:
    """NULL is a value to generate: 10% NULL (or the override), at least one NULL row."""
    if cm.notnull or cm.pk_pos > 0:
        return values
    share = spec.NULL_SHARE_OVERRIDE.get((table, cm.name), spec.NULL_SHARE)
    n = len(values)
    if n == 0:
        return values
    out = list(values)
    n_null = max(1, int(round(n * share)))
    idx = list(range(n))
    rng.shuffle(idx)
    for i in idx[:n_null]:
        out[i] = None
    return out


def _apply_duplicates(table: str, cm, values: list, rng) -> list:
    """DISTINCT-target columns: 30% of rows reuse an earlier value."""
    if (table, cm.name) not in spec.DUPLICATE_COLUMNS:
        return values
    n = len(values)
    if n < 2:
        return values
    out = list(values)
    n_dup = int(round(n * spec.DUPLICATE_SHARE))
    for i in range(n - n_dup, n):
        j = rng.randrange(0, i)
        out[i] = out[j]
    return out


def _apply_ties(table: str, cm, values: list, rng) -> list:
    """ORDER/LIMIT-target columns: plant at least two rows sharing the rank-1 value."""
    if (table, cm.name) not in spec.TIE_COLUMNS:
        return values
    n = len(values)
    if n < 2:
        return values
    out = list(values)
    non_null = [v for v in out if v is not None]
    if not non_null:
        return out
    lo, hi = min(non_null), max(non_null)
    idx = list(range(n))
    rng.shuffle(idx)
    out[idx[0]] = lo
    out[idx[1]] = lo
    if n >= 4:
        out[idx[2]] = hi
        out[idx[3]] = hi
    return out


def _apply_formula(table: str, cm, values: list, rng) -> list:
    """Enforce the semantic formula by construction (Python, never SQL)."""
    rule = spec.FORMULAS.get((table, cm.name))
    if rule is None:
        return values
    out = []
    for v in values:
        if v is None or rule(v):
            out.append(v)
        else:
            for _ in range(20):
                nv = _redraw(table, cm, rng)
                if nv is None or rule(nv):
                    out.append(nv)
                    break
            else:
                out.append(None if not cm.notnull else _fallback(table, cm))
    return out


def _redraw(table: str, cm, rng):
    t = (cm.type_str or '').lower()
    if 'int' in t:
        lo, hi = spec.INT_RANGE
        return rng.randint(lo, hi)
    if any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number')):
        if 'bal' in cm.name:
            lo, hi = spec.REAL_BALANCE
        elif any(k in cm.name for k in ('discount', 'tax')):
            lo, hi = spec.REAL_RATE
        else:
            lo, hi = spec.REAL_AMOUNT
        return round(rng.uniform(lo, hi), 2)
    if 'date' in t:
        lo, hi = spec.DATE_RANGE
        d0 = dt.datetime.strptime(lo, '%Y-%m-%d')
        d1 = dt.datetime.strptime(hi, '%Y-%m-%d')
        return _iso((d0 + dt.timedelta(days=rng.randint(0, (d1 - d0).days))).date())
    return None


def _fallback(table: str, cm):
    t = (cm.type_str or '').lower()
    if 'int' in t:
        return 1
    if any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number')):
        return 0.0
    if 'date' in t:
        return spec.DATE_RANGE[0]
    return ''


def _parse_iso(s):
    if s is None:
        return None
    try:
        return dt.datetime.strptime(str(s), '%Y-%m-%d').date()
    except ValueError:
        return None


def _apply_date_order(table: str, cols: dict, rng) -> None:
    """Date order rules computed in Python from the sampled dates held in memory."""
    if table != 'lineitem':
        return
    n = len(cols.get('l_shipdate', []))
    if n == 0:
        return
    min_d = dt.datetime.strptime(spec.MIN_DATE, '%Y-%m-%d').date()
    for i in range(n):
        commit = cols['l_commitdate'][i]
        ship = cols['l_shipdate'][i]
        receipt = cols['l_receiptdate'][i]
        cd = _parse_iso(commit)
        sd = _parse_iso(ship)
        rd = _parse_iso(receipt)
        if cd is not None and cd < min_d:
            cols['l_commitdate'][i] = spec.MIN_DATE
            commit = spec.MIN_DATE
            cd = min_d
        if sd is not None and cd is not None and sd < cd:
            cols['l_shipdate'][i] = commit
            ship = commit
            sd = cd
        if rd is not None and sd is not None and rd < sd:
            cols['l_receiptdate'][i] = ship


def _fresh_pk_pool(schema, table: str, n: int, rng) -> list:
    """Fresh sequential integers above the compact maximum (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if not tm.primary_key or len(tm.primary_key) != 1:
        return []
    pk = tm.primary_key[0]
    existing = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    start = (max(existing) + 1) if existing else 1
    return list(range(start, start + n))


def _final_key_set(schema, table: str, cols: dict) -> set:
    """Final (post-dedup) key set of a table: compact keys + generated keys."""
    tm = schema.tables[table]
    keys = set()
    if len(tm.primary_key) == 1:
        pk = tm.primary_key[0]
        for v in schema.original_values.get((table, pk), []):
            if v is not None:
                keys.add(v)
        for v in cols.get(pk, []):
            if v is not None:
                keys.add(v)
    return keys


def _repair_fks(inst: dict, schema, rng) -> None:
    """Re-validate every FK value against the parent's final key set; repair or NULL."""
    for table in schema.tables:
        cols = inst.get(table, {})
        if not cols:
            continue
        n = len(next(iter(cols.values())))
        handled = set()
        for cm in schema.tables[table].columns:
            key = (table, cm.name)
            if key not in schema.fks or cm.name in handled:
                continue
            pt, pc = schema.fks[key]
            parent_keys = _final_key_set(schema, pt, inst.get(pt, {}))
            nullable = not cm.notnull and cm.pk_pos == 0
            if _is_composite_child(schema, table, cm.name):
                sib = None
                for (t2, c2), (pt2, pc2) in schema.fks.items():
                    if t2 == table and c2 != cm.name and pt2 == pt and pc2 != pc:
                        sib = c2
                        break
                if sib is None:
                    continue
                pt2, pc2 = schema.fks[(table, sib)]
                a = list(schema.original_values.get((pt, pc), []))
                b = list(schema.original_values.get((pt, pc2), []))
                pairs = list(zip(a, b))
                ga = inst.get(pt, {}).get(pc, [])
                gb = inst.get(pt, {}).get(pc2, [])
                pairs += list(zip(ga, gb))
                pairs = [(x, y) for (x, y) in pairs if x is not None and y is not None]
                for i in range(n):
                    x, y = cols[cm.name][i], cols[sib][i]
                    if x is None and y is None:
                        continue
                    if (x, y) not in pairs:
                        if pairs:
                            nx, ny = rng.choice(pairs)
                            cols[cm.name][i] = nx
                            cols[sib][i] = ny
                        else:
                            cols[cm.name][i] = None
                            cols[sib][i] = None
                handled.add(cm.name)
                handled.add(sib)
                continue
            for i in range(n):
                v = cols[cm.name][i]
                if v is None:
                    continue
                if v not in parent_keys:
                    if parent_keys:
                        cols[cm.name][i] = rng.choice(sorted(parent_keys))
                    elif nullable:
                        cols[cm.name][i] = None
                    else:
                        pass
            handled.add(cm.name)


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as *appended* rows."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        pk_pool = _fresh_pk_pool(schema, t, n, rng)
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            if cm.pk_pos > 0 and pk_pool:
                cols[cm.name] = list(pk_pool)
                continue
            s = spec_sampler(t, cm, rng, literal_pool.get(key, []),
                             schema.original_values.get(key, []), pk_pool=pk_pool)
            vals = [s.sample() for _ in range(n)]
            vals = _apply_formula(t, cm, vals, rng)
            vals = _apply_duplicates(t, cm, vals, rng)
            vals = _apply_ties(t, cm, vals, rng)
            vals = _apply_null_rule(t, cm, vals, rng)
            cols[cm.name] = vals
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        _apply_date_order(t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    _repair_fks(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
