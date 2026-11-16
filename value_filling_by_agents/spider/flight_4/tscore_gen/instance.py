"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append-only generation."""
import random

from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _compact_max(schema, table: str, col: str) -> int:
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _compact_values(schema, table: str, col: str) -> list:
    return [v for v in schema.original_values.get((table, col), []) if v is not None]


def _fresh_pk_start(schema, table: str) -> int:
    tm = schema.tables[table]
    if not tm.primary_key:
        return 1
    return _compact_max(schema, table, tm.primary_key[0]) + 1


def _plant_group_sizes(values: list, rng, n: int) -> list:
    """Force group sizes 1, 2 and >= 3 into a list of values (by construction)."""
    if n < 6:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    a, b, c = rng.sample(pool, 3) if len(pool) >= 3 else (pool[0], pool[0], pool[0])
    values[0] = a
    values[1] = b
    values[2] = b
    values[3] = c
    values[4] = c
    values[5] = c
    return values


def _plant_duplicates(values: list, rng, share: float = 0.35) -> list:
    """Make ~share of the values duplicates of earlier values (20-50% target)."""
    n = len(values)
    if n < 4:
        return values
    k = max(1, int(n * share))
    for i in range(n - k, n):
        values[i] = values[rng.randrange(0, n - k)]
    return values


def _plant_tie(values: list, rng) -> list:
    """Make the first two values equal so the top group is tied at rank 1."""
    if len(values) >= 2:
        values[1] = values[0]
    return values


def _plant_nulls(values: list, rng, share: float) -> list:
    """Ensure at least one NULL and roughly `share` NULLs."""
    n = len(values)
    if n == 0:
        return values
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    for i in idx:
        values[i] = None
    return values


def _sample_column(schema, table: str, col: str, n: int, literal_pool: dict, rng, p: float) -> list:
    """Draw n values for a non-FK column using the generic samplers."""
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == col)
    ov = list(schema.original_values.get((table, col), []))
    sampler = _init_sampler(cm, literal_pool.get((table, col), []), ov, p, rng, len(tm.primary_key))
    return [sampler.sample() for _ in range(n)]


def _choose_sizes(schema, rng) -> dict:
    """Spec table sizes with small per-instance variation (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 0)
        if base:
            jitter = int(base * 0.15)
            sizes[t] = max(0, base + rng.randint(-jitter, jitter))
        else:
            sizes[t] = rng.randint(0, 230)
    return sizes


def _fk_parent_values(schema, inst: dict, table: str, col: str) -> list:
    """Parent values available for an FK: compact rows plus generated rows."""
    pt, pc = schema.fks[(table, col)]
    vals = list(_compact_values(schema, pt, pc))
    vals += [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
    return vals


def _fill_fk(schema, inst: dict, table: str, col: str, n: int, rng, nullable: bool) -> list:
    """FK column: draw from parent values; NULL by the NULL rule."""
    parents = _fk_parent_values(schema, inst, table, col)
    out = []
    for _ in range(n):
        if nullable and rng.random() < spec.FK_NULL_P:
            out.append(None)
        elif parents:
            out.append(rng.choice(parents))
        else:
            out.append(None)
    return out


def _lookup(schema, inst: dict, table: str, col: str, key_col: str, key_val, target_col: str):
    """Look up target_col in parent table where key_col == key_val (compact + generated)."""
    pt, pc = schema.fks[(table, col)]
    keys = schema.original_values.get((pt, pc), [])
    tvals = schema.original_values.get((pt, target_col), [])
    for k, v in zip(keys, tvals):
        if k == key_val:
            return v
    gkeys = inst.get(pt, {}).get(pc, [])
    gvals = inst.get(pt, {}).get(target_col, [])
    for k, v in zip(gkeys, gvals):
        if k == key_val:
            return v
    return None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance's *generated* rows (fuzz.py:111-196, append-only)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = _choose_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos > 0:
                continue
            cols[cm.name] = _sample_column(schema, t, cm.name, n, literal_pool, rng, p)
        if tm.primary_key:
            start = _fresh_pk_start(schema, t)
            if len(tm.primary_key) == 1:
                cols[tm.primary_key[0]] = list(range(start, start + n))
            else:
                for j, pk in enumerate(tm.primary_key):
                    cols[pk] = list(range(start + j, start + j + n))
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                continue
            nullable = not cm.notnull and cm.pk_pos == 0
            cols[cm.name] = _fill_fk(schema, inst, t, cm.name, n, rng, nullable)
        inst[t] = cols
        _apply_dependencies(schema, inst, t)
        _plant_targets(schema, inst, t, rng)
    return {t: inst[t] for t in schema.tables}


def _apply_dependencies(schema, inst: dict, table: str) -> None:
    """Compute copied columns (dst_ap, src_ap, airline) from parent lookups in Python."""
    cols = inst[table]
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct != table:
            continue
        for target in _copied_columns(schema, table, cc):
            if target in cols:
                continue
            vals = []
            for kv in cols.get(cc, []):
                if kv is None:
                    vals.append(None)
                else:
                    vals.append(_lookup(schema, inst, table, cc, pc, kv, target))
            cols[target] = vals


def _copied_columns(schema, table: str, fk_col: str) -> list:
    """Child columns that mirror a parent column via the FK (spec: dependencies copied_columns)."""
    mapping = {
        ('routes', 'dst_apid'): ['dst_ap'],
        ('routes', 'src_apid'): ['src_ap'],
        ('routes', 'alid'): ['airline'],
    }
    return mapping.get((table, fk_col), [])


def _plant_targets(schema, inst: dict, table: str, rng) -> None:
    """Plant group-size, duplicate, tie, NULL and elevation targets for this table."""
    cols = inst[table]
    n = _n_rows(cols)
    if n == 0:
        return
    for (gt, gc) in spec.GROUP_SIZE_TARGETS:
        if gt == table and gc in cols:
            cols[gc] = _plant_group_sizes(cols[gc], rng, n)
    for (dt, dc) in spec.DUPLICATE_TARGETS:
        if dt == table and dc in cols:
            cols[dc] = _plant_duplicates(cols[dc], rng)
    for (tt, tc) in spec.TIE_TARGETS:
        if tt == table and tc in cols:
            cols[tc] = _plant_tie(cols[tc], rng)
    for (nt, nc) in spec.NULL_TARGETS:
        if nt == table and nc in cols:
            share = 0.01 if nc in ('alid', 'dst_apid', 'src_apid') else 0.5
            cols[nc] = _plant_nulls(cols[nc], rng, share)
    if table == 'airports' and 'elevation' in cols:
        vals = cols['elevation']
        for i in range(len(vals)):
            if rng.random() < 0.1:
                vals[i] = spec.ELEVATION_MAX
            else:
                vals[i] = rng.randint(spec.ELEVATION_MIN, spec.ELEVATION_MAX)
        for i in range(min(spec.ELEVATION_TIE_ROWS, len(vals))):
            vals[i] = spec.ELEVATION_MAX
    if table == 'airports':
        if 'x' in cols:
            cols['x'] = [round(rng.uniform(spec.X_MIN, spec.X_MAX), 6) for _ in range(n)]
        if 'y' in cols:
            cols['y'] = [round(rng.uniform(spec.Y_MIN, spec.Y_MAX), 6) for _ in range(n)]
    if table == 'airlines' and 'active' in cols:
        cols['active'] = [rng.choice(spec.ACTIVE_VALUES) for _ in range(n)]
    if table == 'routes' and 'codeshare' in cols:
        cols['codeshare'] = [rng.choice(spec.CODESHARE_VALUES) for _ in range(n)]
