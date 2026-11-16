"""Specification-driven row generation, implemented by construction in Python."""
import re

from .values import _init_sampler

NULLABLE = {
    ('enzyme', 'name'), ('enzyme', 'Location'), ('enzyme', 'Product'),
    ('enzyme', 'Chromosome'), ('enzyme', 'OMIM'), ('enzyme', 'Porphyria'),
    ('medicine', 'name'), ('medicine', 'Trade_Name'), ('medicine', 'FDA_approved'),
    ('medicine_enzyme_interaction', 'interaction_type'),
}
ENUMS = {
    ('medicine', 'FDA_approved'): ['No', 'Yes'],
    ('medicine_enzyme_interaction', 'interaction_type'): ['activitor', 'inhibitor'],
    ('enzyme', 'Location'): ['Mitochondrion', 'Cytosol'],
}
REQUIRED_VALUES = {
    ('medicine', 'FDA_approved'): ['No', 'Yes'],
    ('medicine_enzyme_interaction', 'interaction_type'): ['activitor', 'inhibitor'],
    ('enzyme', 'Location'): ['Mitochondrion', 'Cytosol'],
}
POSITIVE = {('enzyme', 'OMIM')}
LIKE_ANCHORS = {('enzyme', 'name'): ('ALA synthase', 'Hydroxymethyl bilane ALA')}
FRESH_SHARE = 0.15
NULL_SHARE = 0.0
NEAR_VARIANT_P = 0.15
SIZES = {'enzyme': 8, 'medicine': 21, 'medicine_enzyme_interaction': 19}
N_INTERACTIONS = SIZES['medicine_enzyme_interaction']
DUP_SHARE_LO, DUP_SHARE_HI = 0.2, 0.5


def _isnum(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _to_positive_int(v, rng) -> int:
    """Coerce a (possibly near-variant / float-formatted) string to a positive int."""
    try:
        iv = int(float(str(v).strip()))
    except (TypeError, ValueError, OverflowError):
        return rng.randint(1, 10 ** 6)
    return iv if iv > 0 else rng.randint(1, 10 ** 6)


def _near_variant(v: str, rng) -> str:
    """Case change, trailing space or one-character edit of a pool value."""
    if not isinstance(v, str) or not v:
        return v
    u = rng.random()
    if u < 0.34:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.67:
        return v + ' '
    i = rng.randrange(len(v))
    return v[:i] + v[i + 1:]


def build_spec(schema, pool: dict) -> dict:
    """Turn the specification into plain Python data (no SQL, no rule evaluation)."""
    spec = {'nullable': set(NULLABLE), 'enums': dict(ENUMS), 'positive': set(POSITIVE),
            'like_anchors': dict(LIKE_ANCHORS), 'fresh_share': FRESH_SHARE,
            'null_share': NULL_SHARE, 'near_variant_p': NEAR_VARIANT_P,
            'required_values': {k: list(v) for k, v in REQUIRED_VALUES.items()},
            'pool': {k: list(v) for k, v in pool.items()},
            'sizes': dict(SIZES)}
    spec['nullable'] = {k for k in spec['nullable'] if k[0] in schema.tables
                        and any(c.name == k[1] for c in schema.tables[k[0]].columns)}
    spec['enums'] = {k: v for k, v in spec['enums'].items()
                     if k[0] in schema.tables
                     and any(c.name == k[1] for c in schema.tables[k[0]].columns)}
    spec['required_values'] = {k: v for k, v in spec['required_values'].items()
                               if k[0] in schema.tables
                               and any(c.name == k[1] for c in schema.tables[k[0]].columns)}
    spec['positive'] = {k for k in spec['positive'] if k[0] in schema.tables
                        and any(c.name == k[1] for c in schema.tables[k[0]].columns)}
    spec['like_anchors'] = {k: v for k, v in spec['like_anchors'].items()
                            if k[0] in schema.tables
                            and any(c.name == k[1] for c in schema.tables[k[0]].columns)}
    return spec


def plan_offsets(schema, spec: dict) -> dict:
    """Final post-offset single-column integer PKs of the generated rows, per table."""
    out: dict = {}
    for t, n in spec['sizes'].items():
        tm = schema.tables.get(t)
        if tm is None or len(tm.primary_key) != 1:
            continue
        pk = tm.primary_key[0]
        ov = [v for v in schema.original_values.get((t, pk), []) if isinstance(v, int)]
        base = (max(ov) if ov else 0) + 1
        out[t] = list(range(base, base + int(n)))
    return out


def _sampler(schema, spec, table: str, col, rng):
    """Initialise the generic sampler with observed values + pool literals."""
    key = (table, col.name)
    ov = list(schema.original_values.get(key, []))
    lit = list(spec['pool'].get(key, []))
    p = 0.0 if col.checked else 0.2
    return _init_sampler(col, lit, ov, p, rng, 1 if col.pk_pos else 0)


def _sample_column(schema, spec, table: str, col, n: int, rng, start_id: int = 1) -> list:
    """Draw n values for one column honouring the NULL rule and the semantic rules."""
    key = (table, col.name)
    nullable = key in spec['nullable'] and not col.notnull and not col.pk_pos
    if col.pk_pos:
        return list(range(start_id, start_id + n))
    if key in spec['enums']:
        vals = spec['enums'][key]
        out = [rng.choice(vals) for _ in range(n)]
    else:
        s = _sampler(schema, spec, table, col, rng)
        out = []
        for _ in range(n):
            if rng.random() < spec['fresh_share'] and s.elements:
                v = _near_variant(str(rng.choice(s.elements)), rng)
            else:
                v = s.sample()
            out.append(v)
    if key in spec['positive']:
        out = [_to_positive_int(v, rng) for v in out]
    if key in spec['like_anchors']:
        a, b = spec['like_anchors'][key]
        if n >= 1:
            out[0] = a
        if n >= 2:
            out[1] = b
    if nullable:
        k = max(1, int(round(spec['null_share'] * n)))
        for i in rng.sample(range(n), min(k, n)):
            out[i] = None
    return out


def _fk_values(schema, spec, table: str, col, n: int, rng, parent_rows: dict) -> list:
    """FK columns draw from the parent's rows (compact or generated) or are NULL."""
    pt, pc = schema.fks[(table, col.name)]
    pv = parent_rows.get(pt, {}).get(pc) or []
    if not pv:
        return [None] * n
    return [rng.choice(pv) for _ in range(n)]


def _plan_interactions(enzyme_ids: list, medicine_ids: list, rng) -> list:
    """Plan (enzyme_id, medicine_id, interaction_type) tuples against FINAL parent ids."""
    if not enzyme_ids or not medicine_ids:
        return []
    e = list(enzyme_ids)
    m = list(medicine_ids)
    rng.shuffle(e)
    rng.shuffle(m)
    pairs = []
    used = set()

    def add(ei, mi):
        if (ei, mi) in used:
            return False
        used.add((ei, mi))
        pairs.append((ei, mi))
        return True

    e_sizes = [3, 2, 1, 1]
    for k, sz in enumerate(e_sizes):
        if k >= len(e):
            break
        ei = e[k]
        for j in range(sz):
            add(ei, m[(k + j) % len(m)])

    m_sizes = [3, 2, 1, 1]
    for k, sz in enumerate(m_sizes):
        if k >= len(m):
            break
        mi = m[k]
        for j in range(sz):
            add(e[(k + j) % len(e)], mi)

    target = N_INTERACTIONS
    guard = 0
    while len(pairs) < target and guard < 5000:
        guard += 1
        add(rng.choice(e), rng.choice(m))
    pairs = pairs[:target]

    types = ['activitor', 'inhibitor']
    out = []
    for i, (ei, mi) in enumerate(pairs):
        t = types[i % 2] if i < 2 else rng.choice(types)
        out.append((ei, mi, t))
    return out


def _dedupe(table_meta, cols: dict) -> dict:
    """Drop rows whose PK tuple repeats (first occurrence kept)."""
    if not table_meta.primary_key or not cols:
        return cols
    n = len(next(iter(cols.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(cols[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return {c: [v[i] for i in keep] for c, v in cols.items()}


def _plant_nulls(spec, table: str, cols: dict, rng) -> None:
    """Plant >= 1 NULL per nullable column; never strip the last required enum value."""
    for c, vals in cols.items():
        key = (table, c)
        if key not in spec['nullable'] or not vals:
            continue
        if any(v is None for v in vals):
            continue
        required = spec['required_values'].get(key)
        if not required:
            vals[rng.randrange(len(vals))] = None
            continue
        counts = {}
        for v in vals:
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        safe = [i for i, v in enumerate(vals)
                if v is not None and counts.get(v, 0) > 1]
        if safe:
            vals[rng.choice(safe)] = None


def generate_rows(schema, pool: dict, spec: dict, rng) -> dict:
    """Build the generated rows for one instance (dict table -> dict column -> list)."""
    order = [t for lvl in schema.table_order for t in lvl]
    sizes = spec['sizes']
    offsets = plan_offsets(schema, spec)
    parent_rows: dict = {}
    out: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(sizes.get(t, 0))
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            if cm.pk_pos:
                ids = offsets.get(t)
                if ids is not None:
                    cols[cm.name] = list(ids)
                else:
                    cols[cm.name] = _sample_column(schema, spec, t, cm, n, rng, 1)
            else:
                cols[cm.name] = _sample_column(schema, spec, t, cm, n, rng)
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                cols[cm.name] = _fk_values(schema, spec, t, cm, n, rng, parent_rows)
        cols = _dedupe(tm, cols)
        _plant_nulls(spec, t, cols, rng)
        out[t] = cols
        parent_rows[t] = cols

    it = 'medicine_enzyme_interaction'
    if it in schema.tables:
        e_ids = parent_rows.get('enzyme', {}).get('id', [])
        m_ids = parent_rows.get('medicine', {}).get('id', [])
        plan = _plan_interactions(e_ids, m_ids, rng)
        cols = {'enzyme_id': [p[0] for p in plan],
                'medicine_id': [p[1] for p in plan],
                'interaction_type': [p[2] for p in plan]}
        tm = schema.tables[it]
        cols = _dedupe(tm, cols)
        _plant_nulls(spec, it, cols, rng)
        out[it] = cols
    return out
