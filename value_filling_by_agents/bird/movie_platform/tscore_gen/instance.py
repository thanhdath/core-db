"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append to a compact DB."""
import datetime as dt
import re

from .spec import (boundary_literals, different_values_for, duplicate_share_for,
                   null_share_for, policy_for, seed_parent_keys, tie_target_for)
from .spec_samplers import make_spec_sampler

_DATE_LO = dt.datetime(2009, 1, 1)
_DATE_HI = dt.datetime(2020, 12, 31, 23, 59, 59)
_TS_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_date_col(name: str) -> bool:
    low = name.lower()
    return 'date' in low or 'timestamp' in low or 'time' in low


def _clamp_date(v):
    """Clamp a date/timestamp string to the 2009-2020 domain; leave non-strings alone."""
    if not isinstance(v, str):
        return v
    try:
        if _TS_RE.match(v):
            d = dt.datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
            if d < _DATE_LO:
                d = _DATE_LO
            elif d > _DATE_HI:
                d = _DATE_HI
            return d.strftime('%Y-%m-%d %H:%M:%S')
        if _DATE_RE.match(v):
            d = dt.datetime.strptime(v, '%Y-%m-%d')
            if d < _DATE_LO:
                d = _DATE_LO
            elif d > _DATE_HI:
                d = _DATE_HI
            return d.strftime('%Y-%m-%d')
    except ValueError:
        return v
    return v


def _clamp_dates(table, columns, schema):
    """Re-clamp every date/timestamp column to the declared domain."""
    for cm in schema.tables[table].columns:
        if cm.name in columns and _is_date_col(cm.name):
            columns[cm.name] = [_clamp_date(v) for v in columns[cm.name]]
    return columns


def sample_fresh_primary_keys(table_meta, columns: dict, taken: set) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(taken), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   compact: dict) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) or are NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or []) + list(compact.get(pt, {}).get(pc) or [])
        if pv:
            out[cm.name] = [rng.choice(pv) for _ in range(n)]
        else:
            out[cm.name] = [None] * n
    return out


def choose_table_sizes(schema, rng, spec_sizes=None) -> dict:
    """Specification sizes (0-230 rows per table) or level sizes x4 capped at 2500."""
    sizes = {}
    if spec_sizes:
        for t in schema.tables:
            base = int(spec_sizes.get(t, 200))
            sizes[t] = max(0, min(230, base + rng.randint(-20, 20)))
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


def _init_sampler(column, literal_pool, original_values, p, rng, n_pk, spec, table,
                  max_l0=float('inf')):
    """Per-column initialisation (fuzz/fuzz.py:198-224) with specification pools."""
    ov = list(original_values)
    els = (rng.choices(ov, k=min(5, len(ov))) if ov else []) + sorted({str(v) for v in literal_pool})
    if column.checked:
        p = 0.0
    if max_l0 == float('inf') and rng.random() < 0.5:
        max_l0 = rng.random() * 30
        if column.pk_pos > 0:
            max_l0 = float('inf') if n_pk == 1 else 30
    pol = policy_for(spec, table, column.name)
    return make_spec_sampler(column, els, p, max_l0, rng, pol)


def _apply_null_rule(table, columns, schema, rng, spec, compact):
    """NULL is a value: every nullable column gets NULL and non-NULL rows."""
    for cm in schema.tables[table].columns:
        if not cm.name in columns:
            continue
        if not cm.notnull and cm.pk_pos == 0:
            share = null_share_for(spec, table, cm.name, 0.05)
            n = len(columns[cm.name])
            if n == 0:
                continue
            k = max(1, int(round(share * n)))
            idx = rng.sample(range(n), min(k, n))
            for i in idx:
                columns[cm.name][i] = None
    return columns


def _apply_duplicate_share(table, columns, schema, rng, spec, protected=None):
    """Duplicate share for DISTINCT-sensitive columns (20-50 %)."""
    protected = protected or set()
    for cm in schema.tables[table].columns:
        if cm.name not in columns:
            continue
        share = duplicate_share_for(spec, table, cm.name, 0.0)
        if share <= 0:
            continue
        vals = columns[cm.name]
        n = len(vals)
        if n < 2:
            continue
        nonnull = [v for v in vals if v is not None]
        if len(nonnull) < 2:
            continue
        distinct = len({str(v) for v in nonnull})
        current = 1.0 - distinct / len(nonnull)
        target = share
        if current >= target:
            continue
        need = int(round((target - current) * len(nonnull)))
        for _ in range(max(0, need)):
            i, j = rng.randrange(n), rng.randrange(n)
            if i == j or vals[i] is None or vals[j] is None:
                continue
            if vals[i] in protected:
                continue
            vals[i] = vals[j]
    return columns


def _apply_ties(table, columns, schema, rng, spec):
    """Tie at rank 1 for ASC and DESC: force at least two equal extreme values."""
    for cm in schema.tables[table].columns:
        if cm.name not in columns or not tie_target_for(spec, table, cm.name):
            continue
        vals = columns[cm.name]
        nonnull = [v for v in vals if v is not None]
        if len(nonnull) < 2:
            continue
        try:
            lo, hi = min(nonnull), max(nonnull)
        except TypeError:
            continue
        idx = [i for i, v in enumerate(vals) if v == lo]
        while len(idx) < 2:
            for i in range(len(vals)):
                if vals[i] is not None and vals[i] != lo:
                    vals[i] = lo
                    idx.append(i)
                    break
            else:
                break
        idx = [i for i, v in enumerate(vals) if v == hi]
        while len(idx) < 2:
            for i in range(len(vals)):
                if vals[i] is not None and vals[i] != hi:
                    vals[i] = hi
                    idx.append(i)
                    break
            else:
                break
    return columns


def _apply_different_values(table, columns, schema, rng, spec):
    """At least 2 rows per group with different values."""
    for cm in schema.tables[table].columns:
        if cm.name not in columns or not different_values_for(spec, table, cm.name):
            continue
        vals = columns[cm.name]
        if len(vals) < 2:
            continue
        if len(set(map(str, vals))) < 2:
            vals[1] = (vals[0] + 1) if isinstance(vals[0], int) else str(vals[0]) + 'x'
        group_col = None
        for other in schema.tables[table].columns:
            if other.name != cm.name and other.name in columns:
                group_col = other.name
                break
        if group_col is None:
            continue
        groups: dict = {}
        for i, g in enumerate(columns[group_col]):
            groups.setdefault(g, []).append(i)
        for g, idxs in groups.items():
            if len(idxs) < 2:
                continue
            gvals = {str(vals[i]) for i in idxs}
            if len(gvals) < 2:
                i = idxs[1]
                base = vals[idxs[0]]
                vals[i] = (base + 1) if isinstance(base, int) else str(base) + 'x'
    return columns


def _apply_semantic_rules(table, columns, schema, rng, spec):
    """Semantic rules by construction (Python, never SQL)."""
    rules = (spec or {}).get('rules') or []
    for r in rules:
        if r.get('table') != table:
            continue
        col = r.get('column')
        formula = (r.get('formula') or '').lower()
        if col not in columns:
            continue
        vals = columns[col]
        if '>=' in formula and 'timestamp' in formula:
            other = formula.split('>=')[1].strip()
            if other in columns:
                for i in range(len(vals)):
                    a, b = vals[i], columns[other][i]
                    if a is not None and b is not None and str(a) < str(b):
                        vals[i] = b
        elif 'between' in formula and 'and' in formula:
            m = re.search(r'between\s+(-?\d+)\s+and\s+(-?\d+)', formula)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                lo, hi = lo - 1, hi + 1
                for i, v in enumerate(vals):
                    if v is not None and isinstance(v, (int, float)):
                        vals[i] = max(lo, min(hi, int(v)))
        elif '>=' in formula and '0' in formula:
            for i, v in enumerate(vals):
                if v is not None and isinstance(v, (int, float)) and v < 0:
                    vals[i] = 0
        elif 'in (0, 1)' in formula or "in ('0', '1')" in formula:
            for i, v in enumerate(vals):
                if v is not None and str(v) not in ('0', '1'):
                    vals[i] = 0 if rng.random() < 0.5 else 1
    return columns


def _apply_derived_columns(table, columns, schema, rng, spec):
    """Derived columns computed from sampled values held in memory."""
    if table == 'lists':
        for c in ('list_movie_number', 'list_followers', 'list_comments'):
            if c in columns:
                for i, v in enumerate(columns[c]):
                    if v is not None and v < 0:
                        columns[c][i] = 0
        if 'list_update_timestamp_utc' in columns and 'list_creation_timestamp_utc' in columns:
            for i in range(len(columns['list_update_timestamp_utc'])):
                a = columns['list_update_timestamp_utc'][i]
                b = columns['list_creation_timestamp_utc'][i]
                if a is not None and b is not None and str(a) < str(b):
                    columns['list_update_timestamp_utc'][i] = b
    if table == 'lists_users':
        if 'list_update_date_utc' in columns and 'list_creation_date_utc' in columns:
            for i in range(len(columns['list_update_date_utc'])):
                a = columns['list_update_date_utc'][i]
                b = columns['list_creation_date_utc'][i]
                if a is not None and b is not None and str(a) < str(b):
                    columns['list_update_date_utc'][i] = b
    if table == 'movies':
        if 'movie_release_year' in columns:
            for i, v in enumerate(columns['movie_release_year']):
                if v is not None and isinstance(v, (int, float)):
                    columns['movie_release_year'][i] = max(1900, min(2020, int(v)))
        if 'movie_popularity' in columns:
            for i, v in enumerate(columns['movie_popularity']):
                if v is not None and v < 0:
                    columns['movie_popularity'][i] = 0
    if table == 'ratings':
        if 'rating_score' in columns:
            for i, v in enumerate(columns['rating_score']):
                if v is not None and isinstance(v, (int, float)):
                    columns['rating_score'][i] = max(0, min(6, int(v)))
        for c in ('critic_likes', 'critic_comments'):
            if c in columns:
                for i, v in enumerate(columns[c]):
                    if v is not None and v < 0:
                        columns[c][i] = 0
    return columns


def _compact_values(schema, table: str) -> dict:
    """Compact rows of a table, kept in memory for lookups and aggregates."""
    out = {}
    for cm in schema.tables[table].columns:
        out[cm.name] = list(schema.original_values.get((table, cm.name), []))
    return out


def _coerce(cm, v):
    """Coerce a boundary literal to the column's declared type."""
    t = (cm.type_str or '').lower()
    if 'int' in t:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return v


def _seed_boundaries(inst: dict, schema, spec, rng) -> None:
    """Seed comparison-boundary literals into every column that declares them."""
    for t, cols in inst.items():
        for cm in schema.tables[t].columns:
            if cm.name not in cols:
                continue
            bl = boundary_literals(spec, t, cm.name)
            if not bl:
                continue
            col = cols[cm.name]
            if not col:
                continue
            for v in bl:
                cv = _coerce(cm, v)
                if cv is None:
                    continue
                if cv in col:
                    continue
                col[rng.randrange(len(col))] = cv


def _protected(spec, table, schema) -> set:
    """All boundary literals of a table (coerced), protected from overwrite."""
    out = set()
    for cm in schema.tables[table].columns:
        for b in boundary_literals(spec, table, cm.name):
            cv = _coerce(cm, b)
            if cv is not None:
                out.add(cv)
    return out


def _feedback(inst: dict, schema, spec) -> dict:
    """Per-instance feedback: boundary presence, duplicate share, rank-1 ties, min/max, years."""
    fb: dict = {'boundary_present': {}, 'duplicate_share': {}, 'tie_rank1': {},
                'min_max': {}, 'year_hist': {}}
    for t, cols in inst.items():
        for c, vals in cols.items():
            key = '%s.%s' % (t, c)
            bl = boundary_literals(spec, t, c)
            if bl:
                present = all(any(str(v) == str(b) for v in vals) for b in bl)
                fb['boundary_present'][key] = present
            share = duplicate_share_for(spec, t, c, 0.0)
            if share > 0 and vals:
                nonnull = [v for v in vals if v is not None]
                if nonnull:
                    distinct = len({str(v) for v in nonnull})
                    fb['duplicate_share'][key] = 1.0 - distinct / len(nonnull)
            if tie_target_for(spec, t, c) and vals:
                nonnull = [v for v in vals if v is not None]
                if len(nonnull) >= 2:
                    try:
                        lo, hi = min(nonnull), max(nonnull)
                        fb['tie_rank1'][key + ':asc'] = sum(1 for v in vals if v == lo) >= 2
                        fb['tie_rank1'][key + ':desc'] = sum(1 for v in vals if v == hi) >= 2
                    except TypeError:
                        pass
            nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if nums:
                fb['min_max'][key] = [min(nums), max(nums)]
            if 'date' in c.lower() or 'timestamp' in c.lower():
                hist: dict = {}
                for v in vals:
                    if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
                        hist[v[:4]] = hist.get(v[:4], 0) + 1
                if hist:
                    fb['year_hist'][key] = hist
    return fb


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None,
                          want_feedback: bool = False):
    """Build one random instance (fuzz/fuzz.py:111-196) to append to the compact DB."""
    spec = spec or {}
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    compact = {t: _compact_values(schema, t) for t in schema.tables}
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(
                    cm, literal_pool.get((t, cm.name), []),
                    schema.original_values.get((t, cm.name), []), p, rng,
                    len(tm.primary_key), spec, t)
    if size is None:
        size = choose_table_sizes(schema, rng, spec.get('sizes'))
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng, compact))
        cols = _apply_null_rule(t, cols, schema, rng, spec, compact)
        cols = _apply_derived_columns(t, cols, schema, rng, spec)
        _seed_boundaries({t: cols}, schema, spec, rng)
        cols = _apply_ties(t, cols, schema, rng, spec)
        protected = _protected(spec, t, schema)
        cols = _apply_duplicate_share(t, cols, schema, rng, spec, protected=protected)
        cols = _apply_different_values(t, cols, schema, rng, spec)
        cols = _apply_semantic_rules(t, cols, schema, rng, spec)
        cols = _clamp_dates(t, cols, schema)
        taken = set()
        if tm.primary_key:
            pk_vals = compact.get(t, {})
            if all(c in pk_vals for c in tm.primary_key):
                m = len(pk_vals[tm.primary_key[0]]) if tm.primary_key else 0
                for i in range(m):
                    taken.add(tuple(pk_vals[c][i] for c in tm.primary_key))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, taken)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    _seed_boundaries(inst, schema, spec, rng)
    out = {t: inst[t] for t in schema.tables}
    if want_feedback:
        return out, _feedback(out, schema, spec)
    return out
