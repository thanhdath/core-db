"""Build one instance: copy of the compact database + appended rows."""
import random

from . import spec as specmod
from . import samplers
from .spec_values import build_pool


def read_compact(path: str) -> dict:
    """Read the compact database rows as {table: {col: [values]}}."""
    import sqlite3
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % path, uri=True)
    try:
        out = {}
        for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
            cur = con.execute('select * from "%s"' % t.replace('"', '""'))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out[t] = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
        return out
    finally:
        con.close()


def _pick_size(spec: dict, schema, table: str, rng) -> int:
    """Table size: spec size, or 0-230 random rows."""
    sizes = specmod.table_sizes(spec, schema)
    if table in sizes:
        return sizes[table]
    return rng.randint(0, 230)


def _compact_pk_tuples(compact: dict, table: str, pk_cols: list) -> set:
    """Set of PK tuples already present in the compact rows."""
    cols = compact.get(table, {})
    if not pk_cols or not cols:
        return set()
    n = len(cols.get(pk_cols[0], []))
    return {tuple(cols[c][i] for c in pk_cols) for i in range(n)}


def _compact_null_share(compact: dict, table: str, column: str) -> float:
    """NULL share of a column in the compact rows (0.0 when no rows)."""
    vals = compact.get(table, {}).get(column, [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / float(len(vals))


def _plant_nulls(values: list, rng, share: float, nullable: bool) -> list:
    """Plant NULLs in a nullable column: at least one, share ~ compact share."""
    if not nullable or not values:
        return values
    n = len(values)
    if share > 0.0:
        k = max(1, int(round(share * n)))
    else:
        k = 1
    k = min(k, n - 1) if n > 1 else 1
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _is_nullable(cm, spec: dict, table: str, column: str) -> bool:
    """Nullable per schema (not NOT NULL, not PK) and not forced NOT NULL by spec."""
    if cm.notnull or cm.pk_pos > 0:
        return False
    if specmod.forced_not_null(spec, table, column):
        return False
    return True


def build_instance(schema, compact: dict, literal_pool: dict, rng: random.Random, spec: dict) -> dict:
    """Build one instance: {table: {col: [values]}} with appended rows only."""
    order = [t for lvl in schema.table_order for t in lvl]
    inst = {}
    parent_pools = {}
    for t in order:
        tm = schema.tables[t]
        n = _pick_size(spec, schema, t, rng)
        cols = {}
        existing = compact.get(t, {})
        for cm in tm.columns:
            key = (t, cm.name)
            if key in schema.fks:
                continue
            observed = existing.get(cm.name, [])
            lit = literal_pool.get(key, [])
            pool = build_pool(spec, t, cm.name, observed, lit, rng)
            ex = specmod.column_spec(spec, t, cm.name)
            pat = ex.get('pattern')
            nullable = _is_nullable(cm, spec, t, cm.name)
            share = _compact_null_share(compact, t, cm.name)
            if pat in ('primary_key', 'int_primary_key'):
                start = 1
                for v in observed:
                    if isinstance(v, int):
                        start = max(start, v + 1)
                cols[cm.name] = samplers.sample_primary_key(rng, n, start, set(observed))
            elif pat == 'int_range':
                rng_ = specmod.int_range(spec, t, cm.name)
                lo, hi = rng_ if rng_ else (0, 100)
                bounds = specmod.int_boundaries(spec, t, cm.name)
                vals = samplers.sample_int_range(rng, n, lo, hi, pool['values'], bounds)
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
            elif pat == 'int_boundary':
                rng_ = specmod.int_range(spec, t, cm.name)
                lo, hi = rng_ if rng_ else (0, 100)
                bounds = specmod.int_boundaries(spec, t, cm.name)
                vals = samplers.sample_int_boundary(rng, n, lo, hi, pool['values'], bounds)
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
            elif pat == 'text_enum':
                dup = specmod.duplicate_share(spec, t, cm.name)
                gs = specmod.group_size_target(spec, t, cm.name)
                ot = specmod.order_ties(spec, t, cm.name)
                nv = specmod.near_variants(spec, t, cm.name)
                vals = samplers.sample_enum(rng, n, pool['values'], dup, gs, ot, nv)
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
            elif pat == 'text_date':
                fmt = specmod.date_format(spec, t, cm.name)
                vals = samplers.sample_date(rng, n, fmt, pool['values'])
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
            elif pat == 'distinct_duplicates':
                dup = specmod.duplicate_share(spec, t, cm.name)
                ps = specmod.pool_size(spec, t, cm.name)
                vals = samplers.sample_text(rng, n, pool['values'], dup, pool_size=ps)
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
            else:
                vals = samplers.sample_text(rng, n, pool['values'], 0.0)
                cols[cm.name] = _plant_nulls(vals, rng, share, nullable)
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_pool = parent_pools.get(pt, [])
            allow_null = _is_nullable(cm, spec, t, cm.name)
            if not parent_pool and not allow_null:
                raise ValueError('empty parent pool for NOT NULL FK %s.%s -> %s.%s' % (t, cm.name, pt, pc))
            share = _compact_null_share(compact, t, cm.name)
            reserve = specmod.unmatched_join(spec, pt, pc)
            cols[cm.name] = samplers.sample_fk(rng, n, parent_pool, allow_null=allow_null,
                                               null_share=share, reserve_unmatched=reserve)
        if tm.primary_key:
            used = _compact_pk_tuples(compact, t, tm.primary_key)
            keep = []
            for i in range(n):
                k = tuple(cols[c][i] for c in tm.primary_key)
                if k in used:
                    continue
                used.add(k)
                keep.append(i)
            cols = {c: [v[i] for i in keep] for c, v in cols.items()}
        inst[t] = cols
        if tm.primary_key:
            pk = tm.primary_key[0]
            compact_pk = [v for v in existing.get(pk, []) if v is not None]
            parent_pools[t] = compact_pk + [v for v in cols.get(pk, []) if v is not None]
    return inst
