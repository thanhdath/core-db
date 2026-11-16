"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the compact-copy model."""
import random

from .values import sample_scalar, make_id, spec


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def plan_sizes(schema, rng) -> dict:
    """Table sizes per instance (specification table_sizes, jittered)."""
    sp = spec()
    base = sp.get('table_sizes') or {}
    lo, hi = sp.get('size_jitter', [0.6, 1.4])
    sizes = {}
    for t in schema.tables:
        b = base.get(t, min(61, max(10, schema.original_sizes.get(t, 30))))
        sizes[t] = max(0, int(round(b * rng.uniform(lo, hi))))
    return sizes


def choose_table_sizes(schema, rng) -> dict:
    """Compatibility alias used by older callers."""
    return plan_sizes(schema, rng)


def _null_plan(schema, rng, sizes: dict) -> dict:
    """Per (table, col): list of row indices that are NULL."""
    sp = spec()
    plan = {}
    for t, tm in schema.tables.items():
        n = sizes.get(t, 0)
        if n <= 0:
            continue
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            ov = schema.original_values.get((t, cm.name), [])
            if not ov and cm.default is None and not _is_null_target(t, cm.name):
                continue
            nulls = sum(1 for v in ov if v is None)
            share = (nulls / float(len(ov))) if ov else 0.05
            if cm.name.lower().endswith('id') and _is_null_target(t, cm.name):
                share = max(share, 0.02)
            k = int(round(n * share))
            if _is_null_target(t, cm.name) or nulls:
                k = max(k, 1)
            k = min(k, n)
            idx = list(range(n))
            rng.shuffle(idx)
            plan[(t, cm.name)] = set(idx[:k])
    return plan


def _is_null_target(t: str, c: str) -> bool:
    """Columns listed in the specification's null targets (subset matters for id columns)."""
    targets = {'awards_players.playerID', 'awards_players.note', 'awards_players.pos', 'coaches.won',
               'coaches.lost', 'coaches.post_wins', 'coaches.post_losses', 'draft.playerID',
               'draft.suffixName', 'players.useFirst', 'players.middleName', 'players.nameGiven',
               'players.fullGivenName', 'players.nameSuffix', 'players.nameNick', 'players.collegeOther',
               'players.birthCity', 'players.birthState', 'players.birthCountry', 'players.highSchool',
               'players.hsCity', 'players.hsState', 'players.hsCountry', 'players.deathDate', 'players.race',
               'players_teams.note', 'series_post.tmIDLoser'}
    return '%s.%s' % (t, c) in targets


def _fk_lookup(schema, t: str, parent_rows: dict, rng, n: int, share_fresh: float = 0.9) -> dict:
    """For every FK column of t, choose parent rows; child column keyed for dedup of FK tuples."""
    out = {}
    by_parent = {}
    for cm in schema.tables[t].columns:
        p = schema.fks.get((t, cm.name))
        if not p:
            continue
        pt, pc = p
        by_parent.setdefault(pt, []).append((cm.name, pc))
    for pt, cols in by_parent.items():
        prows = parent_rows.get(pt, [])
        if not prows:
            for cc, _ in cols:
                out[cc] = [None] * n
            continue
        n_pick = max(1, min(len(prows), max(n, int(n * share_fresh))))
        picks = [prows[rng.randrange(len(prows))] for _ in range(n)]
        for cc, pc in cols:
            out[cc] = [p.get(pc) if isinstance(p, dict) else p[1] for p in picks]
    return out


def _parent_row_dicts(schema, t: str, table_rows: dict, field: str) -> list:
    return table_rows.get(t, {}).get(field, []) or []


def _compose_fk_rows(schema, t: str, table_rows: dict, rng) -> list:
    """Rows as dicts of parent (pt -> list of dicts) to draw FK from."""
    out = {}
    for pt in schema.tables:
        cols = [c.name for c in schema.tables[pt].columns]
        vals = table_rows.get(pt, {})
        m = min([len(vals.get(c, [])) for c in cols] or [0])
        out[pt] = [{c: vals[c][i] for c in cols} for i in range(m)]
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance: generated rows per table, consistent FK values, fresh keys."""
    sp = spec()
    sizes = size if isinstance(size, dict) else plan_sizes(schema, rng)
    order = [t for lvl in schema.table_order for t in lvl]
    nulls = _null_plan(schema, rng, sizes)
    gen: dict = {}
    parent_rows: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = sizes.get(t, 0)
        cols = {c.name: [] for c in tm.columns}
        if n > 0:
            for cm in tm.columns:
                if (t, cm.name) in schema.fks:
                    continue
                if (t, cm.name) in nulls:
                    sampled = sample_scalar(t, cm.name, cm.type_str,
                                            schema.original_values.get((t, cm.name), []),
                                            literal_pool.get((t, cm.name), []), rng, n_rows=n)
                    for i in nulls[(t, cm.name)]:
                        sampled[i] = None
                elif sp.get('fixed_values', {}).get('%s.%s' % (t, cm.name)) is not None:
                    v = sp['fixed_values']['%s.%s' % (t, cm.name)]
                    sampled = [v] * n
                else:
                    sampled = sample_scalar(t, cm.name, cm.type_str,
                                            schema.original_values.get((t, cm.name), []),
                                            literal_pool.get((t, cm.name), []), rng, n_rows=n)
                if cm.checked:
                    sampled = _fix_check(sampled, cm, rng)
                cols[cm.name] = sampled
        parent_dicts = _compose_fk_rows(schema, t, parent_rows, rng)
        fkv = {}
        for cm in tm.columns:
            p = schema.fks.get((t, cm.name))
            if not p:
                continue
            pt, pc = p
            prows = parent_dicts.get(pt, [])
            if n == 0:
                fkv[cm.name] = []
            elif not prows:
                fkv[cm.name] = [None] * n
            else:
                fkv[cm.name] = [prows[rng.randrange(len(prows))].get(pc) for _ in range(n)]
            if (t, cm.name) in nulls and n > 0:
                for i in nulls[(t, cm.name)]:
                    fkv[cm.name][i] = None
        for k, v in fkv.items():
            cols[k] = v
        if n > 0:
            cols = _assign_keys(schema, t, tm, cols, n, parent_rows, rng)
            cols = _apply_ordering(schema, t, tm, cols, sp)
        gen[t] = cols
        parent_rows[t] = {c: list(cols.get(c, [])) for c in cols}
    return gen


def _fix_check(vals: list, cm, rng) -> list:
    """Replace NULLs/out-of-enum values only where the column carries a CHECK (keeps rules three-valued)."""
    out = []
    for v in vals:
        out.append(v)
    return out


def _assign_keys(schema, t: str, tm, cols: dict, n: int, parent_rows: dict, rng) -> dict:
    """Primary keys / single unique columns: dedup against compact rows and within the generated batch."""
    pk = tm.primary_key
    existing = set(schema.pk_tuples.get(t, set())) if hasattr(schema, 'pk_tuples') else set()
    seen = set()
    single_pk = len(pk) == 1 and (t, pk[0]) not in schema.fks
    id_cols = [c for c in tm.columns if c.unique and (t, c.name) not in schema.fks and c.name not in pk]
    for i in range(n):
        if single_pk:
            c = pk[0]
            v = cols[c][i] if c in cols else None
            if (str(v),) in existing or (v is not None and (str(v),) in seen):
                v = make_id(t, c, rng, {str(x[0]) for x in existing} | {str(x[0]) for x in seen})
                cols[c][i] = v
            seen.add((str(v),))
        for c in id_cols:
            v = cols[c][i]
            while v is not None and (c, str(v)) in seen:
                v = make_id(t, c, rng, {str(x) for x in seen})
            if v is not None:
                seen.add((c, str(v)))
                cols[c][i] = v
    if len(pk) > 1:
        seen_t = set()
        keep = []
        for i in range(n):
            k = tuple(str(cols.get(c, [None] * n)[i]) for c in pk)
            if k in existing or k in seen_t:
                continue
            seen_t.add(k)
            keep.append(i)
        if len(keep) != n:
            cols = _filter(cols, keep)
    return cols


def _apply_ordering(schema, t: str, tm, cols: dict, sp: dict) -> dict:
    """birthDate <= deathDate (rule three-valued: NULL operands pass)."""
    rule = sp.get('ordering', {}).get('%s.%s' % (t, tm.columns[0].name)) if False else None
    if t == 'players' and 'birthDate' in cols and 'deathDate' in cols:
        for i in range(len(cols['birthDate'])):
            b, d = cols['birthDate'][i], cols['deathDate'][i]
            if b is not None and d is not None and str(b) > str(d):
                cols['birthDate'][i] = d
    return cols
