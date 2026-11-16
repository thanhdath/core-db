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
    """FK child columns draw from the parent's finalized values with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 230)
        jitter = rng.randint(-base // 10, base // 10) if base else 0
        sizes[t] = max(0, min(2500, base + jitter))
    return sizes


def _column_spec(table: str, column: str):
    """(check, lo, hi, boundary_literals) for a column, from spec.py."""
    key = (table, column)
    if key == ('businesses', 'business_id'):
        return spec.business_id_ok, 1, None, []
    if key == ('businesses', 'business_certificate'):
        return spec.certificate_ok, 1, None, spec.CERTIFICATE_BOUNDARY
    if key == ('businesses', 'latitude'):
        return spec.latitude_ok, -90.0, 90.0, []
    if key == ('businesses', 'longitude'):
        return spec.longitude_ok, -180.0, 180.0, []
    if key == ('businesses', 'application_date'):
        return spec.application_date_ok, None, None, spec.APPLICATION_DATE_BOUNDARY
    if key == ('businesses', 'name'):
        return None, None, None, spec.NAME_BOUNDARY
    if key == ('inspections', 'score'):
        return spec.score_ok, 0, 100, spec.SCORE_BOUNDARY
    if key == ('inspections', 'date'):
        return spec.inspection_date_ok, '2012-01-01', '2016-12-31', spec.INSPECTION_DATE_BOUNDARY
    if key == ('inspections', 'type'):
        return spec.inspection_type_ok, None, None, spec.TYPE_BOUNDARY
    if key == ('violations', 'date'):
        return spec.violation_date_ok, '2012-01-01', '2016-12-31', spec.VIOLATION_DATE_BOUNDARY
    if key == ('violations', 'risk_category'):
        return spec.risk_category_ok, None, None, spec.RISK_BOUNDARY
    if key == ('violations', 'description'):
        return None, None, None, spec.DESCRIPTION_BOUNDARY
    return None, None, None, []


def _plant_boundary(values: list, boundary: list, rng, share: float = 0.15,
                    exclude: set = frozenset()) -> list:
    """Replace a share of the values with boundary literals (round-robin, deterministic)."""
    if not boundary or not values:
        return values
    cand = [i for i in range(len(values)) if i not in exclude]
    if not cand:
        return values
    k = max(1, int(len(values) * share))
    idx = rng.sample(cand, min(k, len(cand)))
    for j, i in enumerate(idx):
        values[i] = boundary[j % len(boundary)]
    return values


def _plant_duplicates(values: list, rng, share: float = 0.3, exclude: set = frozenset()) -> list:
    """Make ~share of the values repeat an earlier value (20-50 % duplicate share)."""
    if len(values) < 2:
        return values
    cand = [i for i in range(1, len(values)) if i not in exclude]
    if not cand:
        return values
    k = max(1, int(len(values) * share))
    for i in rng.sample(cand, min(k, len(cand))):
        src = [j for j in range(i) if j not in exclude]
        if src:
            values[i] = values[rng.choice(src)]
    return values


def _apply_null_rule(values: list, rate: float, rng) -> tuple:
    """NULL is a value: at least one NULL row, share ~ rate (never for NOT NULL columns)."""
    n = len(values)
    if n == 0:
        return values, set()
    k = max(1, int(round(n * rate)))
    k = min(k, n - 1) if n > 1 else 1
    pos = set(rng.sample(range(n), k))
    for i in pos:
        values[i] = None
    return values, pos


def _fresh_pk_start(schema, table: str, column: str) -> int:
    """First fresh integer above the compact maximum (keys fresh against compact rows)."""
    ov = schema.original_values.get((table, column), [])
    nums = [v for v in ov if isinstance(v, int)]
    return (max(nums) + 1) if nums else 1


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) implementing the specification."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            check, lo, hi, boundary = _column_spec(t, cm.name)
            pool = list(literal_pool.get((t, cm.name), [])) + list(boundary)
            samplers[(t, cm.name)] = _init_sampler(
                cm, pool, schema.original_values.get((t, cm.name), []), p, rng,
                len(tm.primary_key), check=check, lo=lo, hi=hi)
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        for c in tm.primary_key:
            if c in cols and cols[c]:
                start = _fresh_pk_start(schema, t, c)
                cols[c] = [start + i for i in range(len(cols[c]))]
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
        inst[t] = cols

    _apply_spec(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}


def _apply_spec(schema, inst: dict, rng) -> None:
    """Apply the NULL rule first, then plant boundary literals, duplicates and ties at positions excluded from NULL
    sampling (so planted targets survive)."""
    null_pos: dict = {}
    for t, tm in schema.tables.items():
        if t not in inst:
            continue
        for cm in tm.columns:
            if cm.name not in inst[t] or cm.pk_pos > 0 or not cm.notnull is False:
                continue
            if cm.notnull:
                continue
            rate = spec.NULL_RATE.get((t, cm.name), 0.0)
            if rate <= 0:
                continue
            inst[t][cm.name], pos = _apply_null_rule(inst[t][cm.name], rate, rng)
            null_pos[(t, cm.name)] = pos

    def ex(t, c):
        return null_pos.get((t, c), set())

    b = inst.get('businesses')
    if b:
        if 'name' in b:
            b['name'] = _plant_boundary(b['name'], spec.NAME_BOUNDARY, rng, 0.15, ex('businesses', 'name'))
            b['name'] = _plant_duplicates(b['name'], rng, 0.3, ex('businesses', 'name'))
        if 'address' in b:
            b['address'] = _plant_duplicates(b['address'], rng, 0.3, ex('businesses', 'address'))
        if 'owner_name' in b:
            b['owner_name'] = _plant_duplicates(b['owner_name'], rng, 0.3, ex('businesses', 'owner_name'))
        if 'city' in b:
            vals = [v for v in b['city'] if v is not None]
            if vals:
                top = max(set(vals), key=vals.count)
                cand = [i for i in range(len(b['city'])) if i not in ex('businesses', 'city')]
                for i in rng.sample(cand, min(max(1, len(b['city']) // 5), len(cand))):
                    b['city'][i] = top
        if 'application_date' in b:
            b['application_date'] = _plant_boundary(b['application_date'],
                                                    spec.APPLICATION_DATE_BOUNDARY, rng, 0.15,
                                                    ex('businesses', 'application_date'))
        if 'business_certificate' in b:
            b['business_certificate'] = _plant_boundary(b['business_certificate'],
                                                        spec.CERTIFICATE_BOUNDARY, rng, 0.1)

    i = inst.get('inspections')
    if i:
        if 'score' in i:
            i['score'] = _plant_boundary(i['score'], spec.SCORE_BOUNDARY, rng, 0.15, ex('inspections', 'score'))
            nonnull = [j for j, v in enumerate(i['score']) if v is not None]
            if len(nonnull) >= 2:
                top = max(i['score'][j] for j in nonnull)
                for j in nonnull[:2]:
                    i['score'][j] = top
        if 'date' in i:
            i['date'] = _plant_boundary(i['date'], spec.INSPECTION_DATE_BOUNDARY, rng, 0.15)
        if 'type' in i:
            i['type'] = _plant_boundary(i['type'], spec.TYPE_BOUNDARY, rng, 0.1)

    v = inst.get('violations')
    if v:
        if 'date' in v:
            v['date'] = _plant_boundary(v['date'], spec.VIOLATION_DATE_BOUNDARY, rng, 0.15)
        if 'risk_category' in v:
            v['risk_category'] = _plant_boundary(v['risk_category'], spec.RISK_BOUNDARY, rng, 0.2)
        if 'description' in v:
            v['description'] = _plant_boundary(v['description'], spec.DESCRIPTION_BOUNDARY, rng, 0.15)
            v['description'] = _plant_duplicates(v['description'], rng, 0.3)
        if 'violation_type_id' in v:
            v['violation_type_id'] = _plant_duplicates(v['violation_type_id'], rng, 0.3)
