"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the specification."""
from . import spec_samplers as sp

SPEC_SIZES = {'branch': 8, 'member': 10, 'membership_register_branch': 8, 'purchase': 8}


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _dedup_pk(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats (first occurrence kept)."""
    if not table_meta.primary_key or not columns:
        return columns
    if any(c not in columns for c in table_meta.primary_key):
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def _drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single-column UNIQUE value (first occurrence kept)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns and cm.pk_pos == 0:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_int_max(schema, table: str, col: str) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _spec_table_sizes(rng) -> dict:
    """Specification sizes; small jitter (0..3) so instances vary and target group sizes (1, 2, >=3) are all
    achievable; never below the spec size."""
    return {t: v + rng.randint(0, 3) for t, v in SPEC_SIZES.items()}


def _make_sampler_for_column(schema, table: str, col, rng, literal_pool):
    """Dispatch specification exceptions to the right spec sampler."""
    name = col.name
    pool = schema.original_values.get((table, name), [])

    if table == 'branch':
        if name == 'Branch_ID':
            return sp.IntRangeSampler(rng, 100, 900, distinct=1, positive=True)
        if name == 'Name':
            return sp.GroupedTextSampler(rng, pool, group_sizes=(1, 2, 3))
        if name == 'Open_year':
            return sp.TextBoundarySampler(
                rng, 2000, 2020,
                boundary_pool=[2009, 2010, 2011, 2012],
                prefer_boundary=0.5, group_sizes=(1, 2, 3))
        if name == 'Address_road':
            return sp.TextPoolSampler(rng, pool)
        if name == 'City':
            return sp.CitySampler(rng)
        if name == 'membership_amount':
            return sp.BoundaryTextSampler(
                rng, 0, 199,
                boundary_pool=[99, 100, 101],
                prefer_boundary=0.4)
    if table == 'member':
        if name == 'Member_ID':
            return sp.IntRangeSampler(rng, 100, 900, distinct=1, positive=True)
        if name == 'Card_Number':
            return sp.CardNumberSampler(rng, pool)
        if name == 'Name':
            return sp.DupTextSampler(rng, pool, dup_share=0.35)
        if name == 'Hometown':
            return sp.TextPoolSampler(
                rng, pool,
                near_variants=['Kentucky', 'Kentuckz', 'x Kentucky', 'kentucky', 'Kentucky x',
                               'Lexington, Kentucky'],
                fresh_pool=['Owensboro', 'Frankfort', 'Paducah', 'Bowling Green'])
        if name == 'Level':
            return sp.GroupedIntSampler(rng, 1, 10, boundary_pool=[2, 4, 6],
                                        prefer_boundary=0.4, group_sizes=(1, 2, 3))
    if table == 'membership_register_branch':
        if name == 'Member_ID':
            return None
        if name == 'Branch_ID':
            return None
        if name == 'Register_Year':
            return sp.BoundaryTextSampler(
                rng, 2010, 2020,
                boundary_pool=[2013, 2014, 2015, 2016, 2017],
                prefer_boundary=0.5, max_distinct=0)
    if table == 'purchase':
        if name == 'Member_ID':
            return None
        if name == 'Branch_ID':
            return None
        if name == 'Year':
            return sp.BoundaryTextSampler(
                rng, 2015, 2019,
                boundary_pool=[2017, 2018, 2019],
                prefer_boundary=0.6, max_distinct=0)
        if name == 'Total_pounds':
            class RealAmt:
                def __init__(self, rng_):
                    self.rng = rng_

                def sample(self, n):
                    return [round(self.rng.uniform(1.0, 5000.0), 2) for _ in range(n)]

            return RealAmt(rng)
    return None


def _plant_nulls(values: list, rng, null_share: float) -> list:
    """Plant NULLs per the NULL rule: at least one NULL if allowed, share ~ null_share."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(null_share * n)))
    idxs = set(rng.sample(range(n), min(k, n)))
    return [None if i in idxs else values[i] for i in range(n)]


def _fk_parent_pool(schema, inst_pk, pt: str, pc: str) -> list:
    """Parent key pool: compact values + final generated parent PKs (post-dedup)."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in inst_pk.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _fill_fk_columns(schema, inst_pk, table: str, n: int, rng) -> dict:
    """Fill the FK columns of `table` for n rows from the parent's final key pool."""
    tm = schema.tables[table]
    pk_cols = set(tm.primary_key)
    out = {}
    for cm in tm.columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _fk_parent_pool(schema, inst_pk, pt, pc)
        col = [None] * n
        if cm.notnull:
            if cm.name in pk_cols:
                if len(pv) < n:
                    raise ValueError(
                        'PK+FK %s.%s needs %d distinct parent keys but pool has %d'
                        % (table, cm.name, n, len(pv)))
                col = rng.sample(pv, n)
            else:
                draw_pool = pv[:-1] if len(pv) > 1 else pv
                for i in range(n):
                    col[i] = rng.choice(draw_pool) if draw_pool else None
        else:
            ns = schema.null_share.get(key, 0.0)
            if ns <= 0:
                ns = 0.1
            k = max(1, int(round(ns * n)))
            null_idx = set(rng.sample(range(n), min(k, n)))
            draw_pool = pv[:-1] if len(pv) > 1 else pv
            for i in range(n):
                if i in null_idx or not draw_pool:
                    col[i] = None
                else:
                    col[i] = rng.choice(draw_pool)
        out[cm.name] = col
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance: generated rows to append to the compact DB."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = _spec_table_sizes(rng) if size is None else size
    inst: dict = {}
    inst_pk: dict = {}

    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        if n <= 0:
            inst[t] = {c.name: [] for c in tm.columns}
            inst_pk[t] = {c.name: [] for c in tm.columns}
            continue

        cols: dict = {}
        for cm in tm.columns:
            sampler = _make_sampler_for_column(schema, t, cm, rng, literal_pool)
            if sampler is None:
                continue
            if isinstance(sampler, sp.IntRangeSampler):
                start = _compact_int_max(schema, t, cm.name) + 1
                vals = sampler.sample(n, start=start)
            else:
                vals = sampler.sample(n)
            cols[cm.name] = vals

        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            key = (t, cm.name)
            if key in schema.fks:
                continue
            if cm.name not in cols:
                continue
            ns = schema.null_share.get(key, 0.0)
            if ns > 0:
                cols[cm.name] = _plant_nulls(cols[cm.name], rng, ns)

        cols = _dedup_pk(tm, cols)
        cols = _drop_unique_duplicates(tm, cols)
        n_final = len(next(iter(cols.values()))) if cols else n

        fk_cols = _fill_fk_columns(schema, inst_pk, t, n_final, rng)
        cols.update(fk_cols)

        for cm in tm.columns:
            if cm.name in cols:
                inst_pk.setdefault(t, {})[cm.name] = cols[cm.name]

        inst[t] = cols

    return {t: inst.get(t, {c.name: [] for c in schema.tables[t].columns}) for t in schema.tables}
