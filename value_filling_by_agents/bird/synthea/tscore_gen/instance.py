"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import datetime as dt
import re
import uuid

from .spec import (BOUNDARY_VALUES, DEPENDENCIES, ENUM_POOLS, LIKE_VARIANTS, NULL_TARGETS,
                   UNMATCHED_CHILD)
from .values import (BoundarySampler, EnumSampler, _init_sampler, make_column_sampler)

_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _is_date_str(v) -> bool:
    return isinstance(v, str) and _DATE_RE.match(v) is not None


def _to_date(v):
    if v is None:
        return None
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        m = _DATE_RE.match(v)
        if m:
            try:
                return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


def _fmt(d: dt.date) -> str:
    return d.strftime('%Y-%m-%d')


def _fresh_uuid(rng) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def sample_fresh_primary_keys(table_meta, columns: dict, compact_seen: set, rng) -> dict:
    """Drop rows whose PK tuple repeats (compact or generated), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(compact_seen), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict, compact_unique: dict, rng) -> dict:
    """Drop rows repeating any single unique column value (compact or generated)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(compact_unique.get(cm.name, ())), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _compact_unique_values(schema, table: str) -> dict:
    """Unique column values already present in the compact table."""
    tm = schema.tables[table]
    out = {}
    for cm in tm.columns:
        if cm.unique:
            out[cm.name] = {v for v in schema.original_values.get((table, cm.name), []) if v is not None}
    return out


def _compact_pk_tuples(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def choose_table_sizes(schema, rng, spec: dict) -> dict:
    """Specification table sizes, jittered per instance (0-230 rows, or level x4 capped at 2500)."""
    base = spec.get('table_sizes') or {}
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                b = int(base.get(t, 30))
                sizes[t] = max(0, int(b * (0.5 + rng.random())))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _enum_sampler(table: str, col: str, rng):
    pool = ENUM_POOLS.get((table, col))
    if pool:
        return EnumSampler(pool, rng)
    return None


def _boundary_wrap(table: str, col: str, base, rng):
    b = BOUNDARY_VALUES.get((table, col))
    if b:
        return BoundarySampler(base, b, rng)
    return base


def _like_variant_wrap(table: str, col: str, base, rng):
    vs = LIKE_VARIANTS.get((table, col))
    if vs:
        return BoundarySampler(base, vs, rng, share=0.2)
    return base


def _null_share(schema, table: str, col: str) -> float:
    """NULL share following the compact database's share for that column (5-30 % band)."""
    share = NULL_TARGETS.get((table, col))
    if share is None:
        vals = schema.original_values.get((table, col), [])
        if not vals:
            return 0.15
        n_null = sum(1 for v in vals if v is None)
        share = n_null / len(vals)
    if share <= 0.0:
        return 0.15
    return min(max(share, 0.05), 0.30)


def _plant_nulls(table: str, col: str, values: list, schema, rng) -> list:
    """NULL rule: at least one NULL row per nullable column, share ~ compact share."""
    if (table, col) not in NULL_TARGETS:
        return values
    n = len(values)
    if n == 0:
        return values
    share = _null_share(schema, table, col)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _apply_formulas(table: str, cols: dict, schema, rng) -> None:
    """Semantic formulas, implemented in Python (never SQL)."""
    if table == 'all_prevalences':
        rate = cols.get('PREVALENCE RATE')
        pct = cols.get('PREVALENCE PERCENTAGE')
        if rate is not None and pct is not None:
            for i in range(len(rate)):
                r = rate[i]
                if r is None:
                    continue
                r = min(max(float(r), 0.0), 1.0)
                rate[i] = r
                pct[i] = round(r * 100.0, 4)
        occ = cols.get('OCCURRENCES')
        if occ is not None:
            cols['OCCURRENCES'] = [None if v is None else max(0, int(v)) for v in occ]
        pc = cols.get('POPULATION COUNT')
        if pc is not None:
            cols['POPULATION COUNT'] = [None if v is None else max(1, int(v)) for v in pc]

    if table == 'patients':
        bd = cols.get('birthdate')
        dd = cols.get('deathdate')
        if bd is not None and dd is not None:
            for i in range(len(bd)):
                b = _to_date(bd[i])
                d = _to_date(dd[i])
                if b is None:
                    continue
                if d is not None and d <= b:
                    dd[i] = _fmt(b + dt.timedelta(days=rng.randint(1, 365 * 90)))

    if table in ('careplans', 'conditions', 'medications'):
        st = cols.get('START')
        sp = cols.get('STOP')
        if st is not None and sp is not None:
            for i in range(len(st)):
                s = _to_date(st[i])
                e = _to_date(sp[i])
                if s is None:
                    continue
                if e is not None and e < s:
                    sp[i] = _fmt(s + dt.timedelta(days=rng.randint(0, 365 * 3)))

    if table == 'claims':
        tot = cols.get('TOTAL')
        if tot is not None:
            cols['TOTAL'] = [None if v is None else max(0, int(v)) for v in tot]

    if table == 'observations':
        val = cols.get('VALUE')
        if val is not None:
            out = []
            for v in val:
                if v is None:
                    out.append(None)
                else:
                    try:
                        f = float(v)
                    except (TypeError, ValueError):
                        out.append(None)
                        continue
                    out.append(min(max(f, -1000.0), 1000.0))
            cols['VALUE'] = out


def _encounter_after_birth(inst: dict, schema, rng) -> None:
    """encounters.DATE >= patient.birthdate (inferred rule), generated encounters only."""
    enc = inst.get('encounters')
    if not enc:
        return
    dates = enc.get('DATE')
    pats = enc.get('PATIENT')
    if dates is None or pats is None:
        return
    birth = {}
    pids = schema.original_values.get(('patients', 'patient'), [])
    bds = schema.original_values.get(('patients', 'birthdate'), [])
    for i, pid in enumerate(pids):
        if i < len(bds):
            birth[pid] = _to_date(bds[i])
    pat = inst.get('patients') or {}
    for i, pid in enumerate(pat.get('patient', [])):
        b = pat.get('birthdate', [])
        if i < len(b):
            birth[pid] = _to_date(b[i])
    for i in range(len(dates)):
        pid = pats[i]
        b = birth.get(pid)
        d = _to_date(dates[i])
        if b is None:
            continue
        if d is None or d < b:
            dates[i] = _fmt(b + dt.timedelta(days=rng.randint(0, 365 * 40)))


def _parent_values(inst: dict, schema, pt: str, pc: str) -> list:
    """Parent column values: generated rows first, then compact rows (non-NULL)."""
    pv = [v for v in (inst.get(pt, {}).get(pc) or []) if v is not None]
    pv += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    return pv


def _fill_foreign_keys(inst: dict, schema, table: str, n: int, rng, spec: dict) -> dict:
    """FK child columns draw from the parent's compact + generated values (or NULL)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(inst, schema, pt, pc)
        nullable = not cm.notnull and cm.pk_pos == 0
        if not pv:
            out[cm.name] = [None] * n
            continue
        vals = [rng.choice(pv) for _ in range(n)]
        if key in UNMATCHED_CHILD and n > 0 and nullable:
            k = max(1, int(0.1 * n))
            for i in rng.sample(range(n), k):
                vals[i] = None
        out[cm.name] = vals
    return out


def _fill_dependent_description(inst: dict, schema, table: str, n: int, rng) -> dict:
    """conditions.DESCRIPTION draws from all_prevalences.ITEM (compact + generated)."""
    out = {}
    if table != 'conditions':
        return out
    items = _parent_values(inst, schema, 'all_prevalences', 'ITEM')
    if not items:
        return out
    out['DESCRIPTION'] = [rng.choice(items) for _ in range(n)]
    return out


def _repair_child_fks(inst: dict, schema, rng) -> None:
    """After dedup, re-validate child FK values against the final parent value sets."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        parent_vals = [v for v in (inst.get(pt, {}).get(pc) or []) if v is not None]
        parent_vals += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        pset = set(parent_vals)
        cm = next((c for c in schema.tables[ct].columns if c.name == cc), None)
        nullable = cm is not None and not cm.notnull and cm.pk_pos == 0
        vals = inst[ct][cc]
        for i, v in enumerate(vals):
            if v is None or v in pset:
                continue
            if parent_vals:
                vals[i] = rng.choice(parent_vals)
            elif nullable:
                vals[i] = None
            else:
                vals[i] = None


def build_random_instance(schema, literal_pool: dict, size, rng, spec: dict = None) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
    if spec is None:
        from .spec import load_specification
        spec = load_specification()
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if t == 'conditions' and cm.name == 'DESCRIPTION':
                continue
            base = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                 schema.original_values.get((t, cm.name), []), p, rng,
                                 len(tm.primary_key))
            enum = _enum_sampler(t, cm.name, rng)
            if enum is not None:
                base = enum
            base = _boundary_wrap(t, cm.name, base, rng)
            base = _like_variant_wrap(t, cm.name, base, rng)
            samplers[(t, cm.name)] = base
    if size is None:
        size = choose_table_sizes(schema, rng, spec)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(_fill_foreign_keys(inst, schema, t, n, rng, spec))
        cols.update(_fill_dependent_description(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.name in cols and (t, cm.name) in NULL_TARGETS:
                cols[cm.name] = _plant_nulls(t, cm.name, cols[cm.name], schema, rng)
        _apply_formulas(t, cols, schema, rng)
        compact_pk = _compact_pk_tuples(schema, t)
        compact_uniq = _compact_unique_values(schema, t)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns if cm.name in cols},
                                         compact_pk, rng)
        cols = drop_unique_duplicates(tm, cols, compact_uniq, rng)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    _encounter_after_birth(inst, schema, rng)
    _repair_child_fks(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
