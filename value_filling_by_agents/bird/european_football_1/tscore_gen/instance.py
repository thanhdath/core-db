"""Random instance construction: compact rows + appended generated rows."""
import random

from .samplers import make_spec_sampler
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


def _null_share(schema, table: str, col: str, spec: dict) -> float:
    """NULL share: specification target, else the compact database's share, at least one NULL row."""
    key = '%s.%s' % (table, col)
    sc = spec.get('columns', {}).get(key, {})
    if 'null_share' in sc:
        return float(sc['null_share'])
    ov = schema.original_values.get((table, col), [])
    if ov:
        share = sum(1 for v in ov if v is None) / float(len(ov))
        return min(0.30, max(0.05, share))
    return 0.10


def _table_size(schema, table: str, spec: dict, rng: random.Random) -> int:
    """Specification size with per-instance variation (0-230 rows)."""
    base = int(spec.get('table_sizes', {}).get(table, 20))
    base = max(0, min(230, base))
    if base == 0:
        return 0
    lo = max(1, int(base * 0.6))
    hi = min(230, max(lo, int(base * 1.4)))
    return rng.randint(lo, hi)


def _goal_pair(fthg, ftag, rng: random.Random):
    """Goal-pair emphasis: equal / one-step pairs or total goals 9..11 (non-NULL operands only)."""
    if fthg is None or ftag is None:
        return fthg, ftag
    if rng.random() < 0.35:
        u = rng.random()
        if u < 0.4:
            ftag = fthg
        elif u < 0.7:
            ftag = max(0, min(7, fthg + rng.choice([-1, 1])))
        else:
            total = rng.choice([9, 10, 11])
            fthg = max(0, min(8, total - ftag))
    return fthg, ftag


def _ftr_from_goals(fthg, ftag, rng: random.Random):
    """Derived FTR from the goals (H/h, D/d, A/a); NULL operands leave FTR to the NULL rule."""
    if fthg is None or ftag is None:
        return None
    if fthg > ftag:
        return rng.choice(['H', 'h'])
    if fthg < ftag:
        return rng.choice(['A', 'a'])
    return rng.choice(['D', 'd'])


def _apply_rules(table: str, cols: dict, spec: dict, rng: random.Random) -> None:
    """Apply semantic rules by construction on the in-memory columns (never with SQL)."""
    n = len(next(iter(cols.values()))) if cols else 0
    for rule in spec.get('rules', []):
        if rule.get('table') != table:
            continue
        c = rule.get('column')
        if c not in cols:
            continue
        kind = rule.get('kind')
        if kind == 'between':
            lo, hi = int(rule['lo']), int(rule['hi'])
            cols[c] = [None if v is None else max(lo, min(hi, int(v))) for v in cols[c]]
        elif kind == 'in':
            allowed = list(rule.get('values') or [])
            if allowed:
                cols[c] = [None if v is None else (v if v in allowed else rng.choice(allowed))
                           for v in cols[c]]
        elif kind == 'goal_pair':
            other = rule.get('other')
            if other in cols:
                for i in range(n):
                    a, b = _goal_pair(cols[c][i], cols[other][i], rng)
                    cols[c][i], cols[other][i] = a, b
    if table == 'matchs' and 'FTHG' in cols and 'FTAG' in cols and 'FTR' in cols:
        for i in range(n):
            if cols['FTR'][i] is not None:
                cols['FTR'][i] = _ftr_from_goals(cols['FTHG'][i], cols['FTAG'][i], rng)


def build_random_instance(schema, literal_pool: dict, size, rng, spec=None) -> dict:
    """Build one instance: generated rows per table, in foreign-key order."""
    spec = spec or {}
    order = [t for lvl in schema.table_order for t in lvl]
    fk_cols = set(schema.fks.keys())
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in fk_cols:
                continue
            key = '%s.%s' % (t, cm.name)
            sc = spec.get('columns', {}).get(key, {})
            nullable = (not cm.notnull) and cm.pk_pos == 0
            share = _null_share(schema, t, cm.name, spec) if nullable else 0.0
            samplers[(t, cm.name)] = make_spec_sampler(
                cm, sc, literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []), rng, nullable, share)
    if size is None:
        size = {t: _table_size(schema, t, spec, rng) for t in order}
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = list(inst.get(pt, {}).get(pc) or [])
            parent_vals += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
            sc = spec.get('columns', {}).get('%s.%s' % (t, cm.name), {})
            unmatched = float(sc.get('unmatched_prob', 0.15))
            nullable = not cm.notnull
            share = _null_share(schema, t, cm.name, spec) if nullable else 0.0
            out = []
            for _ in range(n):
                u = rng.random()
                if nullable and u < share:
                    out.append(None)
                elif u < share + unmatched or not parent_vals:
                    out.append(None if nullable else ('UNMATCHED_%d' % rng.randrange(10 ** 6)))
                else:
                    out.append(rng.choice(parent_vals))
            cols[cm.name] = out
        _apply_rules(t, cols, spec, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
