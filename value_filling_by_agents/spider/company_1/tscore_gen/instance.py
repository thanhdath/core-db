"""Random instance construction: compact copy + appended rows (fuzz/fuzz.py:83-196, adapted)."""
import datetime as dt

from .values import _init_sampler, make_column_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _is_int_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'int' in t and 'point' not in t


def _is_real_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric'))


def _is_date_type(type_str: str) -> bool:
    t = (type_str or '').lower()
    return 'date' in t or 'time' in t


def _parse_iso(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _rand_date(rng, lo: str, hi: str) -> str:
    a, b = _parse_iso(lo), _parse_iso(hi)
    if a is None or b is None or b < a:
        a, b = dt.date(1900, 1, 1), dt.date(1999, 12, 31)
    return (a + dt.timedelta(days=rng.randint(0, (b - a).days))).isoformat()


def _norm_key(schema, table: str, column: str) -> str:
    """Resolve a (table, column) key to the schema's declared column name (case-insensitive)."""
    tm = schema.tables.get(table)
    if tm is None:
        raise KeyError('unknown table %r; available tables: %r' % (table, sorted(schema.tables)))
    for c in tm.columns:
        if c.name.lower() == str(column).lower():
            return c.name
    raise KeyError('unknown column %r.%r; available columns: %r'
                   % (table, column, [c.name for c in tm.columns]))


def _fk_lookup(schema, table: str, column: str):
    """Case-insensitive lookup in schema.fks; returns (parent_table, parent_column) or None."""
    for (ct, cc), pv in schema.fks.items():
        if ct == table and cc.lower() == str(column).lower():
            return pv
    return None


def choose_table_sizes(schema, spec: dict, rng) -> dict:
    """Target sizes from the specification, varied per instance (0-230 rows, level x4 capped 2500)."""
    target = spec.get('table_sizes') or {}
    sizes = {}
    if not spec.get('size_variation', True):
        for t in schema.tables:
            sizes[t] = int(target.get(t, 0))
        return sizes
    if rng.random() < 0.5:
        for t in schema.tables:
            base = int(target.get(t, 0))
            lo = max(0, base - max(1, base // 2))
            hi = min(230, base + max(1, base // 2))
            sizes[t] = rng.randint(lo, hi) if hi >= lo else base
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _pk_pool(schema, table: str, compact: dict, generated: dict) -> list:
    """All existing PK tuples of a table (compact + generated), in memory."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return []
    out = []
    for src in (compact.get(table, {}), generated.get(table, {})):
        n = _n_rows(src)
        for i in range(n):
            out.append(tuple(src[c][i] for c in tm.primary_key))
    return out


def _fresh_pk(schema, table: str, cols: dict, i: int, used: set, rng, planted_cols: set = frozenset()) -> bool:
    """Make row i's PK tuple unique against compact rows and earlier generated rows."""
    tm = schema.tables[table]
    if not tm.primary_key:
        return True
    key = tuple(cols[c][i] for c in tm.primary_key)
    if key not in used:
        used.add(key)
        return True
    if table == 'works_on' and 'Essn' in tm.primary_key and 'Pno' in tm.primary_key:
        is_orphan = 'Essn' in planted_cols
        v = cols['Essn'][i]
        if isinstance(v, int) and not isinstance(v, bool):
            for step in (1, 2, 3, 5, 10, 100, 1000):
                cand = v + step
                trial = list(key)
                trial[tm.primary_key.index('Essn')] = cand
                trial = tuple(trial)
                if trial not in used:
                    cols['Essn'][i] = cand
                    used.add(trial)
                    return True
        return False
    for c in reversed(tm.primary_key):
        if _fk_lookup(schema, table, c) is not None:
            continue
        v = cols[c][i]
        if isinstance(v, int) and not isinstance(v, bool):
            for step in (1, 2, 3, 5, 10, 100, 1000):
                cand = v + step
                trial = list(key)
                trial[tm.primary_key.index(c)] = cand
                trial = tuple(trial)
                if trial not in used:
                    cols[c][i] = cand
                    used.add(trial)
                    return True
    return False


def _column_sampler(schema, table: str, cm, spec: dict, pool: dict, rng, n_pk: int):
    """Build a sampler for a non-FK column, honouring the specification by construction."""
    key = '%s.%s' % (table, cm.name)
    ov = list(schema.original_values.get((table, cm.name), []))
    lit = list(pool.get((table, cm.name), []))
    lit += [str(v) for v in spec.get('literal_pools', {}).get(key, [])]
    enum = spec.get('enum_pools', {}).get(key)
    if enum:
        els = [str(e) for e in enum]
        return make_column_sampler(cm, els, 0.0, float('inf'), rng)
    rng_pair = spec.get('numeric_ranges', {}).get(key)
    bounds = spec.get('comparison_boundaries', {}).get(key)
    if bounds and (_is_int_type(cm.type_str) or _is_real_type(cm.type_str)):
        els = [str(b) for b in bounds] + [str(v) for v in ov if v is not None] + lit
        s = make_column_sampler(cm, els, 0.0, float('inf'), rng)
        return _BoundarySampler(s, bounds, rng, _is_int_type(cm.type_str))
    if rng_pair and (_is_int_type(cm.type_str) or _is_real_type(cm.type_str)):
        lo, hi = rng_pair
        els = [str(v) for v in ov if v is not None] + lit
        s = make_column_sampler(cm, els, 0.0, float('inf'), rng)
        return _RangeSampler(s, lo, hi, rng, _is_int_type(cm.type_str))
    dr = spec.get('date_ranges', {}).get(key)
    if dr and _is_date_type(cm.type_str):
        return _DateRangeSampler(dr[0], dr[1], rng)
    dup = spec.get('duplicate_share', {}).get(key)
    if dup:
        return _DuplicateSampler(cm, ov, lit, dup, rng, n_pk)
    return _init_sampler(cm, lit, ov, 0.2, rng, n_pk)


class _BoundarySampler:
    """Values at the comparison boundary (x = c for > vs >=) plus one step on each side."""

    def __init__(self, base, bounds, rng, is_int):
        self.base, self.bounds, self.rng, self.is_int = base, list(bounds), rng, is_int

    def sample(self):
        r = self.rng
        if r.random() < 0.6:
            v = r.choice(self.bounds)
            if r.random() < 0.25:
                v += r.choice((-1, 1))
            return int(v) if self.is_int else float(v)
        return self.base.sample()


class _RangeSampler:
    """Uniform value inside the observed range, with boundary values and one step outside."""

    def __init__(self, base, lo, hi, rng, is_int):
        self.base, self.lo, self.hi, self.rng, self.is_int = base, lo, hi, rng, is_int

    def sample(self):
        r = self.rng
        u = r.random()
        if u < 0.15:
            v = self.lo
        elif u < 0.30:
            v = self.hi
        elif u < 0.40:
            v = self.lo - 1
        elif u < 0.50:
            v = self.hi + 1
        elif u < 0.75:
            v = r.randint(int(self.lo), int(self.hi)) if self.is_int else r.uniform(self.lo, self.hi)
        else:
            return self.base.sample()
        return int(v) if self.is_int else float(v)


class _DateRangeSampler:
    """ISO date inside the plausible range (>= '1900-01-01')."""

    def __init__(self, lo, hi, rng):
        self.lo, self.hi, self.rng = lo, hi, rng

    def sample(self):
        return _rand_date(self.rng, self.lo, self.hi)


class _DuplicateSampler:
    """Duplicate share 20-50% (soft target): a fraction of rows repeats an earlier value."""

    def __init__(self, cm, ov, lit, share, rng, n_pk):
        self.base = _init_sampler(cm, lit, ov, 0.2, rng, n_pk)
        self.share = min(0.5, max(0.2, float(share)))
        self.rng = rng
        self.seen: list = []

    def sample(self):
        r = self.rng
        if self.seen and r.random() < self.share:
            return r.choice(self.seen)
        v = self.base.sample()
        self.seen.append(v)
        return v


def _fk_values(schema, table: str, cm, compact: dict, generated: dict, n: int, rng) -> list:
    """FK child column draws from the parent's compact + generated values (with replacement)."""
    fk = _fk_lookup(schema, table, cm.name)
    if fk is None:
        return [None] * n
    pt, pc = fk
    pv = list(compact.get(pt, {}).get(pc, []) or []) + list(generated.get(pt, {}).get(pc, []) or [])
    pv = [v for v in pv if v is not None]
    if not pv:
        return [None] * n
    return [rng.choice(pv) for _ in range(n)]


def _apply_null_rule(table: str, cm, values: list, spec: dict, rng, planted: set = frozenset()) -> list:
    """NULL is a value: at least one NULL per nullable column, share from the compact statistics."""
    if not values:
        return values
    key = '%s.%s' % (table, cm.name)
    share = spec.get('null_share', {}).get(key)
    if share is None:
        return values
    n = len(values)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    candidates = [i for i in range(n) if i not in planted]
    if not candidates:
        return values
    k = min(k, len(candidates))
    idx = rng.sample(candidates, k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _apply_semantic_rules(table: str, cols: dict, spec: dict, rng) -> None:
    """Rules constrain only non-NULL operands; a planted NULL is never replaced."""
    for rule in spec.get('semantic_rules', []):
        if rule.get('table') != table:
            continue
        c = rule.get('column')
        if c not in cols:
            continue
        op, val = rule.get('op'), rule.get('value')
        if op == 'in':
            allowed = list(val) if isinstance(val, (list, tuple)) else [val]
            for i, v in enumerate(cols[c]):
                if v is None:
                    continue
                if v not in allowed:
                    cols[c][i] = rng.choice(allowed)
            continue
        for i, v in enumerate(cols[c]):
            if v is None:
                continue
            bad = False
            try:
                if op == '>=':
                    bad = v < val
                elif op == '>':
                    bad = v <= val
                elif op == '<=':
                    bad = v > val
                elif op == '<':
                    bad = v >= val
            except TypeError:
                bad = False
            if bad:
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    cols[c][i] = val + (1 if op in ('>', '>=') else -1)
                else:
                    cols[c][i] = val


def build_random_instance(schema, literal_pool: dict, spec, size, rng):
    """Build one random instance: compact rows + appended generated rows (fuzz.py:111-196)."""
    spec = spec or {}
    compact = schema.original_values
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, spec, rng)
    generated: dict = {}
    planted_all: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        if n <= 0:
            generated[t] = {c.name: [] for c in tm.columns}
            continue
        cols: dict = {}
        for cm in tm.columns:
            if _fk_lookup(schema, t, cm.name) is not None:
                continue
            s = _column_sampler(schema, t, cm, spec, literal_pool, rng, len(tm.primary_key))
            cols[cm.name] = [s.sample() for _ in range(n)]
        for cm in tm.columns:
            if _fk_lookup(schema, t, cm.name) is not None:
                cols[cm.name] = _fk_values(schema, t, cm, compact, generated, n, rng)
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            cols[cm.name] = _apply_null_rule(t, cm, cols[cm.name], spec, rng)
        planted: dict = {}
        for key, cnt in spec.get('planted_orphans', {}).items():
            tt, cc = key.split('.', 1)
            if tt != t:
                continue
            try:
                cc = _norm_key(schema, t, cc)
            except KeyError:
                continue
            if cc not in cols:
                continue
            planted[cc] = set()
            for i in range(min(int(cnt), n)):
                cols[cc][i] = _orphan_value(schema, t, cc, compact, generated, rng)
                planted[cc].add(i)
        _apply_semantic_rules(t, cols, spec, rng)
        used = set(_pk_pool(schema, t, compact, generated))
        keep = []
        for i in range(n):
            planted_cols = {c for c, idxs in planted.items() if i in idxs}
            if _fresh_pk(schema, t, cols, i, used, rng, planted_cols):
                keep.append(i)
        cols = _filter(cols, keep)
        for c, idxs in planted.items():
            planted_all['%s.%s' % (t, c)] = {i for i in idxs if i in set(keep)}
        for cm in tm.columns:
            fk = _fk_lookup(schema, t, cm.name)
            if fk is None:
                continue
            pt, pc = fk
            if pt == t:
                final = [v for v in cols.get(pc, []) if v is not None]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        generated[t] = {c.name: cols.get(c.name, []) for c in tm.columns}
    inst = {t: generated.get(t, {c.name: [] for c in schema.tables[t].columns}) for t in schema.tables}
    return inst, planted_all


def _orphan_value(schema, table: str, column: str, compact: dict, generated: dict, rng):
    """A value for a child FK that has no matching parent row."""
    fk = _fk_lookup(schema, table, column)
    if fk is None:
        return rng.randint(10 ** 8, 10 ** 9)
    pt, pc = fk
    parents = set(compact.get(pt, {}).get(pc, []) or []) | set(generated.get(pt, {}).get(pc, []) or [])
    parents = {v for v in parents if v is not None}
    ints = [v for v in parents if isinstance(v, int) and not isinstance(v, bool)]
    if ints:
        cand = max(ints) + rng.randint(1, 1000)
        while cand in parents:
            cand += 1
        return cand
    return 'orphan_%d' % rng.randint(1, 10 ** 6)
