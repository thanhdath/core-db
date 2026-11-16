"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
from .values import _init_sampler


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


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact + generated) with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = list(instance.get(pt, {}).get(pc) or [])
        pv += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        pv = [v for v in pv if v is not None]
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def _revalidate_fks(columns: dict, schema, table: str, rng) -> dict:
    """Replace FK values that are not in the parent key set with a valid parent key or NULL."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in columns:
            continue
        pt, pc = schema.fks[key]
        valid = set(v for v in schema.original_values.get((pt, pc), []) if v is not None)
        vals = columns[cm.name]
        for i, v in enumerate(vals):
            if v is None:
                continue
            if v not in valid:
                vals[i] = rng.choice(sorted(valid)) if valid else None
    return columns


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes per instance (generated rows appended to the compact copy)."""
    return {t: spec.TABLE_SIZES.get(t, 0) for t in schema.tables}


def _plant_nulls(columns: dict, table_meta, schema, table: str, rng, exclude: dict) -> dict:
    """NULL rule: at least one NULL per nullable column (compact null_rate 0.0 -> 1 row)."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in table_meta.columns:
        if cm.name not in columns:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        k = min(spec.NULL_ROWS_PER_COLUMN, n)
        ex = exclude.get(cm.name, set())
        cand = [i for i in range(n) if i not in ex]
        if not cand:
            cand = list(range(n))
        idx = rng.sample(cand, min(k, len(cand)))
        for i in idx:
            columns[cm.name][i] = None
    return columns


def _apply_derived(columns: dict, table: str) -> dict:
    """Derived columns computed in Python from sampled values (never with SQL)."""
    if table == 'county_public_safety':
        pop = columns.get('Population')
        off = columns.get('Police_officers')
        if pop is not None and off is not None:
            rpo = []
            for p, o in zip(pop, off):
                if p is None or o is None:
                    rpo.append(None)
                else:
                    rpo.append(spec.residents_per_officer(int(p), int(o)))
            columns['Residents_per_officer'] = rpo
    return columns


def _apply_duplicates(columns: dict, table: str, rng, protected: dict) -> dict:
    """Plant duplicate shares for DISTINCT patterns (by construction)."""
    def dup(col_name, share):
        col = columns.get(col_name)
        if not col or len(col) < 2:
            return
        n = len(col)
        k = max(1, int(n * share))
        ex = protected.get(col_name, set())
        for i in range(1, min(k + 1, n)):
            if i in ex:
                continue
            col[i] = col[0]

    if table == 'county_public_safety':
        dup('Crime_rate', spec.CRIME_RATE_DUP_SHARE)
        dup('Name', spec.NAME_DUP_SHARE)
    if table == 'city':
        dup('Name', spec.CITY_NAME_DUP_SHARE)
        dup('County_ID', spec.CITY_COUNTY_DUP_SHARE)
    return columns


def _apply_group_sizes(columns: dict, table: str, rng, protected: dict) -> dict:
    """Plant group sizes 1, 2 and >= 3 for GROUP patterns (by construction)."""
    if table == 'county_public_safety':
        loc = columns.get('Location')
        if loc and len(loc) >= 6:
            ex = protected.get('Location', set())
            if not any(i in ex for i in range(6)):
                loc[0] = 'East'
                loc[1] = 'West'
                loc[2] = 'West'
                loc[3] = 'North'
                loc[4] = 'North'
                loc[5] = 'North'
    return columns


def _preseed_protected(table: str, n: int) -> dict:
    """Compute boundary/tie target indices first and pre-seed the protected set with them."""
    protected: dict = {}
    if table == 'county_public_safety':
        for i in range(min(len(spec.POPULATION_BOUNDARY), n)):
            protected.setdefault('Population', set()).add(i)
        for i in range(min(len(spec.CRIME_RATE_BOUNDARY), n)):
            protected.setdefault('Crime_rate', set()).add(i)
        for i in range(min(len(spec.LOCATION_BOUNDARY), n)):
            protected.setdefault('Location', set()).add(i)
        for col, top in (('Population', spec.POPULATION_TIE_TOP),
                         ('Police_officers', spec.POLICE_OFFICERS_TIE_TOP),
                         ('Police_force', spec.POLICE_FORCE_TIE_TOP)):
            ex = protected.setdefault(col, set())
            added = 0
            for i in range(n):
                if added >= top:
                    break
                if i not in ex:
                    ex.add(i)
                    added += 1
    if table == 'city':
        if n >= spec.CITY_WHITE_TIE_RANK:
            protected.setdefault('White', set()).add(spec.CITY_WHITE_TIE_RANK - 1)
        if n >= 1:
            protected.setdefault('County_ID', set()).add(0)
        if n >= 2:
            protected.setdefault('County_ID', set()).add(1)
    return protected


def _apply_boundaries(columns: dict, table: str, rng, protected: dict) -> dict:
    """Plant boundary literals for comparison-boundary patterns (by construction)."""
    protected = {k: set(v) for k, v in protected.items()}
    if table == 'county_public_safety':
        pop = columns.get('Population')
        if pop:
            for i, v in enumerate(spec.POPULATION_BOUNDARY):
                if i < len(pop):
                    pop[i] = v
                    protected.setdefault('Population', set()).add(i)
        cr = columns.get('Crime_rate')
        if cr:
            for i, v in enumerate(spec.CRIME_RATE_BOUNDARY):
                if i < len(cr):
                    cr[i] = v
                    protected.setdefault('Crime_rate', set()).add(i)
        loc = columns.get('Location')
        if loc:
            for i, v in enumerate(spec.LOCATION_BOUNDARY):
                if v in spec.LOCATION_ENUM and i < len(loc):
                    loc[i] = v
                    protected.setdefault('Location', set()).add(i)
    return columns, protected


def _apply_ties(columns: dict, table: str, rng, protected: dict) -> dict:
    """Plant tied sort values at the requested ranks (by construction)."""
    protected = {k: set(v) for k, v in protected.items()}
    if table == 'county_public_safety':
        pop = columns.get('Population')
        if pop and len(pop) >= 2:
            ex = protected.get('Population', set())
            top = max(pop)
            cand = [i for i in range(len(pop)) if i not in ex]
            for i in cand[:spec.POPULATION_TIE_TOP]:
                pop[i] = top
                protected.setdefault('Population', set()).add(i)
        off = columns.get('Police_officers')
        if off and len(off) >= 2:
            ex = protected.get('Police_officers', set())
            top = max(off)
            cand = [i for i in range(len(off)) if i not in ex]
            for i in cand[:spec.POLICE_OFFICERS_TIE_TOP]:
                off[i] = top
                protected.setdefault('Police_officers', set()).add(i)
            if len(set(off)) < spec.POLICE_OFFICERS_DISTINCT and len(off) >= 2:
                j = [i for i in range(len(off)) if i not in ex][0]
                off[j] = (top - 1) if top > 1 else 1
        pf = columns.get('Police_force')
        if pf and len(pf) >= 2:
            ex = protected.get('Police_force', set())
            top = max(pf)
            cand = [i for i in range(len(pf)) if i not in ex]
            for i in cand[:spec.POLICE_FORCE_TIE_TOP]:
                pf[i] = top
                protected.setdefault('Police_force', set()).add(i)
    if table == 'city':
        w = columns.get('White')
        if w and len(w) >= spec.CITY_WHITE_TIE_RANK:
            ex = protected.get('White', set())
            order = sorted(range(len(w)), key=lambda i: (w[i] is None, -(w[i] or 0)))
            if len(order) >= spec.CITY_WHITE_TIE_RANK:
                r4 = order[spec.CITY_WHITE_TIE_RANK - 2]
                r5 = order[spec.CITY_WHITE_TIE_RANK - 1]
                if r5 not in ex:
                    w[r5] = w[r4]
                    protected.setdefault('White', set()).add(r5)
    return columns, protected


def _apply_city_county_boundary(columns: dict, schema, rng, protected: dict) -> dict:
    """equal_and_one_step_from: parent key equal to parent +/- 1 within the valid FK set."""
    protected = {k: set(v) for k, v in protected.items()}
    cid = columns.get('County_ID')
    if cid is None:
        return columns, protected
    valid = sorted(v for v in (schema.original_values.get(('county_public_safety', 'County_ID'), []) or [])
                   if v is not None)
    if not valid:
        return columns, protected
    ex = protected.get('County_ID', set())
    cand = [i for i in range(len(cid)) if i not in ex]
    if not cand:
        return columns, protected
    cid[cand[0]] = valid[0]
    protected.setdefault('County_ID', set()).add(cand[0])
    if len(cand) > 1:
        step = valid[0] + 1
        if step in valid:
            cid[cand[1]] = step
        else:
            cid[cand[1]] = valid[0]
        protected.setdefault('County_ID', set()).add(cand[1])
    return columns, protected


def _assert_planted(columns: dict, table: str) -> None:
    """Assert the planted boundary literals and tie ranks are present."""
    if table == 'county_public_safety':
        pop = columns.get('Population') or []
        for v in spec.POPULATION_BOUNDARY:
            assert v in pop, 'population boundary %r missing' % v
        cr = columns.get('Crime_rate') or []
        for v in spec.CRIME_RATE_BOUNDARY:
            assert v in cr, 'crime_rate boundary %r missing' % v
        loc = columns.get('Location') or []
        for v in spec.LOCATION_BOUNDARY:
            assert v in loc, 'location boundary %r missing' % v
        off = columns.get('Police_officers') or []
        if len(off) >= 2:
            assert len(set(off)) >= spec.POLICE_OFFICERS_DISTINCT, 'police_officers distinct values missing'
    if table == 'city':
        w = columns.get('White') or []
        if len(w) >= spec.CITY_WHITE_TIE_RANK:
            vals = sorted([v for v in w if v is not None], reverse=True)
            if len(vals) >= spec.CITY_WHITE_TIE_RANK:
                assert vals[spec.CITY_WHITE_TIE_RANK - 2] == vals[spec.CITY_WHITE_TIE_RANK - 1], \
                    'white tie at rank %d missing' % spec.CITY_WHITE_TIE_RANK


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        protected = _preseed_protected(t, n)
        cols = _apply_duplicates(cols, t, rng, protected)
        cols = _apply_group_sizes(cols, t, rng, protected)
        cols, protected = _apply_boundaries(cols, t, rng, protected)
        cols, protected = _apply_ties(cols, t, rng, protected)
        if t == 'city':
            cols, protected = _apply_city_county_boundary(cols, schema, rng, protected)
        cols = _revalidate_fks(cols, schema, t, rng)
        cols = _apply_derived(cols, t)
        cols = _plant_nulls(cols, tm, schema, t, rng, protected)
        _assert_planted(cols, t)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
