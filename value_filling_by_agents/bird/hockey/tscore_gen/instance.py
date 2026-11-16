"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
from .values import (ColumnSampler, EnumSampler, HeightSampler, IdSampler, NameSampler,
                     NoteSampler, NumericTextSampler, NumberSampler, _init_sampler)


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
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
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
    """Spec table_sizes_per_instance, jittered per instance (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 20)
        sizes[t] = max(0, min(230, int(base * (0.5 + rng.random()))))
    return sizes


def _boundary_values(table: str, col: str) -> list:
    return list(spec.BOUNDARY.get((table, col), []))


def _make_spec_sampler(table: str, cm, literal_pool: list, original_values, p: float, rng,
                       n_pk: int, nullable: bool) -> ColumnSampler:
    """Build a sampler that honours the specification's value domain for (table, column)."""
    name = cm.name
    ov = [v for v in original_values if v is not None]
    pool = list(ov[:5]) + sorted({str(v) for v in literal_pool})
    pool += [str(v) for v in _boundary_values(table, name)]

    if name == 'lgID':
        return EnumSampler(spec.LG_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'confID':
        return EnumSampler(spec.CONF_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'divID':
        return EnumSampler(spec.DIV_IDS, p, float('inf'), rng, nullable=nullable)
    if table == 'HOF' and name == 'category':
        return EnumSampler(spec.HOF_CATEGORIES, p, float('inf'), rng, nullable=False)
    if table == 'AwardsCoaches' and name == 'award':
        return EnumSampler(spec.AWARDS_COACHES, p, float('inf'), rng, nullable=False)
    if table == 'AwardsPlayers' and name == 'pos':
        return EnumSampler(spec.AWARDS_PLAYERS_POS, p, float('inf'), rng, nullable=nullable)
    if table == 'AwardsPlayers' and name == 'award':
        return EnumSampler(spec.AWARDS_PLAYERS_AWARDS, p, float('inf'), rng, nullable=False)
    if table == 'AwardsMisc' and name == 'award':
        return EnumSampler(['Patrick'], p, float('inf'), rng, nullable=False)
    if table == 'AwardsMisc' and name == 'lgID':
        return EnumSampler(['NHL'], p, float('inf'), rng, nullable=nullable)
    if table == 'CombinedShutouts' and name == 'R/P':
        return EnumSampler(spec.RP, p, float('inf'), rng, nullable=False)
    if table == 'Master' and name == 'shootCatch':
        return EnumSampler(spec.SHOOT_CATCH, p, float('inf'), rng, nullable=nullable)
    if table == 'abbrev' and name == 'Type':
        return EnumSampler(spec.ABBREV_TYPES, p, float('inf'), rng, nullable=False)
    if table == 'Teams' and name == 'playoff':
        return EnumSampler(spec.PLAYOFFS, p, float('inf'), rng, nullable=nullable)
    if table == 'SeriesPost' and name == 'round':
        return EnumSampler(spec.ROUNDS, p, float('inf'), rng, nullable=False)

    if name in ('note', 'notes'):
        if table == 'Coaches':
            return NoteSampler(spec.NOTES_COACHES, p, float('inf'), rng, nullable=nullable)
        if table in ('AwardsPlayers', 'AwardsCoaches'):
            return NoteSampler(spec.NOTES_AWARDS, p, float('inf'), rng, nullable=nullable)
        if table == 'SeriesPost':
            return NoteSampler(spec.NOTES_SERIES, p, float('inf'), rng, nullable=nullable)
        if table == 'AwardsMisc':
            return NoteSampler(spec.NOTES_MISC, p, float('inf'), rng, nullable=nullable)
        return NoteSampler([], p, float('inf'), rng, nullable=nullable)

    if name == 'firstName':
        return NameSampler(spec.FIRST_NAMES, p, float('inf'), rng, nullable=nullable)
    if name == 'lastName':
        return NameSampler(spec.LAST_NAMES, p, float('inf'), rng, nullable=False)
    if name in ('birthCity', 'deathCity'):
        return NameSampler(spec.CITIES, p, float('inf'), rng, nullable=nullable)
    if name in ('birthCountry', 'deathCountry'):
        return NameSampler(spec.COUNTRIES, p, float('inf'), rng, nullable=nullable)
    if name in ('birthState', 'deathState'):
        return NameSampler(spec.STATES, p, float('inf'), rng, nullable=nullable)
    if name == 'name' and table == 'Teams':
        return NameSampler(spec.TEAM_NAMES, p, float('inf'), rng, nullable=False)
    if name == 'name' and table == 'HOF':
        return NameSampler(spec.FIRST_NAMES + spec.LAST_NAMES, p, float('inf'), rng, nullable=False)
    if name == 'name' and table == 'AwardsMisc':
        return NameSampler(spec.MISC_NAMES, p, float('inf'), rng, nullable=False)
    if name == 'Fullname':
        return NameSampler(spec.ABBREV_FULLNAMES, p, float('inf'), rng, nullable=False)
    if name == 'Code':
        return EnumSampler(spec.ABBREV_CODES, p, float('inf'), rng, nullable=False)
    if name == 'tmID':
        return IdSampler(spec.TEAM_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'oppID':
        return IdSampler(spec.TEAM_IDS, p, float('inf'), rng, nullable=False)
    if name == 'franchID':
        return IdSampler(spec.FRANCH_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'playerID':
        return IdSampler(spec.PLAYER_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'coachID':
        return IdSampler(spec.COACH_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'hofID':
        return IdSampler(spec.HOF_IDS, p, float('inf'), rng, nullable=nullable)
    if name == 'ID' and table == 'AwardsMisc':
        return IdSampler(spec.MISC_IDS, p, float('inf'), rng, nullable=nullable)
    if name in ('IDgoalie1', 'IDgoalie2'):
        return IdSampler(spec.PLAYER_IDS, p, float('inf'), rng, nullable=False)
    if name in ('legendsID', 'ihdbID', 'hrefID'):
        return IdSampler(spec.PLAYER_IDS, p, float('inf'), rng, nullable=nullable)

    if name == 'year':
        if table == 'HOF':
            return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                                 lo=spec.HOF_YEAR_MIN, hi=spec.HOF_YEAR_MAX)
        if table == 'AwardsPlayers':
            return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                                 lo=spec.AWARDS_PLAYERS_YEAR_MIN, hi=spec.AWARDS_PLAYERS_YEAR_MAX)
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.YEAR_MIN, hi=spec.YEAR_MAX)
    if name in ('firstNHL', 'lastNHL', 'firstWHA', 'lastWHA', 'birthYear', 'deathYear'):
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.YEAR_MIN, hi=spec.YEAR_MAX)

    if name == 'rank':
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.RANK_MIN, hi=spec.RANK_MAX)
    if name in ('month', 'birthMon', 'deathMon'):
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.MONTH_MIN, hi=spec.MONTH_MAX)
    if name in ('date', 'birthDay', 'deathDay'):
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.DAY_MIN, hi=spec.DAY_MAX)
    if name == 'stint':
        hi = 4 if table == 'Scoring' else (2 if table == 'GoaliesShootout' else 3)
        return NumberSampler(pool, p, float('inf'), rng, is_int=True, lo=1, hi=hi)
    if name == 'half':
        return NumberSampler(pool, p, float('inf'), rng, is_int=True, lo=1, hi=2)

    if name in ('G', 'W', 'L', 'T', 'Pts', 'GF', 'GA', 'GP', 'A', 'PIM', 'Min', 'SHO', 'ENG',
                'SA', 'PostGP', 'PostMin', 'PostW', 'PostL', 'PostT', 'PostENG', 'PostSHO',
                'PostGA', 'PostSA', 'g', 'w', 'l', 't', 'S', 'GDG', 'GoalsWinner', 'GoalsLoser',
                'hW', 'hL', 'hT', 'rW', 'rL', 'rT', 'JanW', 'JanL', 'JanT', 'FebW', 'FebL',
                'FebT'):
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.COUNT_MIN, hi=spec.COUNT_MAX)

    if name in ('PPG', 'PPA', 'SHG', 'SHA', 'GWG', 'GTG', 'SOG', 'PostG', 'PostA', 'PostPts',
                'PostPIM', 'PostPPG', 'PostPPA', 'PostSHG', 'PostSHA', 'PostGWG', 'PostSOG',
                'PIM', 'BenchMinor', 'PPC', 'PKG', 'PKC', 'SHF', 'SoW', 'SoL', 'OTL', 'hOTL',
                'rOTL', 'SepW', 'SepL', 'SepT', 'SepOL', 'OctW', 'OctL', 'OctT', 'OctOL',
                'NovW', 'NovL', 'NovT', 'NovOL', 'DecW', 'DecL', 'DecT', 'DecOL', 'JanOL',
                'FebOL', 'MarW', 'MarL', 'MarT', 'MarOL', 'AprW', 'AprL', 'AprT', 'AprOL',
                'T/OL', 'postg', 'postw', 'postl', 'postt', '+/-', 'Post+/-'):
        return NumericTextSampler(pool, p, float('inf'), rng, nullable=nullable)

    if name == 'height':
        return HeightSampler(pool, p, float('inf'), rng)
    if name == 'weight':
        return NumberSampler(pool, p, float('inf'), rng, is_int=True,
                             lo=spec.WEIGHT_MIN, hi=spec.WEIGHT_MAX)

    return _init_sampler(cm, pool, ov, p, rng, n_pk)


def _apply_null_rule(table: str, cols: dict, schema, rng) -> dict:
    """For every nullable column, plant NULLs at the compact share (>=1 row) and guarantee at least one NULL row for
    the spec's NULL targets."""
    tm = schema.tables[table]
    n = len(next(iter(cols.values()))) if cols else 0
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        share = _compact_null_share(schema, table, cm.name)
        share = max(0.05, min(0.30, share))
        if (table, cm.name) in spec.UNMATCHED_PARENT:
            share = min(share, spec.FK_PARENT_NULL_CAP)
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None
    for (t, c) in spec.NULL_TARGETS:
        if t != table or c not in cols:
            continue
        cm = next((x for x in tm.columns if x.name == c), None)
        if cm is None or cm.notnull or cm.pk_pos > 0:
            continue
        if all(v is not None for v in cols[c]):
            cols[c][rng.randrange(n)] = None
    return cols


def _compact_null_share(schema, table: str, col: str) -> float:
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.1
    nulls = sum(1 for v in vals if v is None)
    return nulls / len(vals)


def _enforce_death_after_birth(cols: dict, rng) -> dict:
    """deathYear >= birthYear when both non-NULL (resample deathYear)."""
    if not spec.DEATH_AFTER_BIRTH:
        return cols
    by, dy = cols.get('birthYear'), cols.get('deathYear')
    if by is None or dy is None:
        return cols
    for i in range(len(dy)):
        b, d = by[i], dy[i]
        if b is None or d is None:
            continue
        try:
            bi, di = int(b), int(d)
        except (TypeError, ValueError):
            continue
        if di < bi:
            dy[i] = str(rng.randint(bi, spec.YEAR_MAX))
    return cols


def _enforce_height_boundary(cols: dict, rng) -> dict:
    """Guarantee exact height values 72 and 73 (plain or slash form) so the predicate master.height > 72 has
    equal-and-one-step-from coverage."""
    h = cols.get('height')
    if not h:
        return cols
    n = len(h)
    if n < 2:
        return cols
    idx = list(range(n))
    rng.shuffle(idx)
    h[idx[0]] = '72'
    h[idx[1]] = '73'
    return cols


def _plant_group_sizes(table: str, cols: dict, rng) -> dict:
    """For GROUP_SIZE_TARGETS, ensure groups of size 1, 2 and >=3 exist."""
    for (t, c) in spec.GROUP_SIZE_TARGETS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 6:
            continue
        vals = [v for v in cols[c] if v is not None]
        if len(vals) < 3:
            continue
        v1, v2, v3 = rng.sample(vals, 3)
        idx = list(range(n))
        rng.shuffle(idx)
        cols[c][idx[0]] = v1
        cols[c][idx[1]] = v2
        cols[c][idx[2]] = v2
        cols[c][idx[3]] = v3
        cols[c][idx[4]] = v3
        cols[c][idx[5]] = v3
    return cols


def _plant_ties(table: str, cols: dict, rng) -> dict:
    """For TIE_TARGETS, plant at least two rows tied at rank 1."""
    for (t, c, agg, kind) in spec.TIE_TARGETS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 2:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        if kind == 'sum':
            if 'SHO' not in cols:
                continue
            idx = list(range(n))
            rng.shuffle(idx)
            p1, p2 = vals[0], (vals[1] if len(vals) > 1 else vals[0])
            cols[c][idx[0]] = p1
            cols[c][idx[1]] = p2
            cols['SHO'][idx[0]] = '5'
            cols['SHO'][idx[1]] = '5'
            for j in range(n):
                if j in (idx[0], idx[1]):
                    continue
                if cols['SHO'][j] is not None:
                    try:
                        if int(cols['SHO'][j]) > 5:
                            cols['SHO'][j] = '5'
                    except (TypeError, ValueError):
                        cols['SHO'][j] = '5'
        elif kind == 'count':
            idx = list(range(n))
            rng.shuffle(idx)
            v1 = vals[0]
            v2 = vals[1] if len(vals) > 1 else vals[0]
            k = max(1, n // 8)
            for j in idx[:k]:
                cols[c][j] = v1
            for j in idx[k:2 * k]:
                cols[c][j] = v2
        elif kind == 'coalesce':
            if 'SHO' not in cols:
                continue
            idx = list(range(n))
            rng.shuffle(idx)
            cols['SHO'][idx[0]] = None
            cols['SHO'][idx[1]] = None
            for j in range(n):
                if j in (idx[0], idx[1]):
                    continue
                if cols['SHO'][j] is not None:
                    try:
                        if int(cols['SHO'][j]) < 0:
                            cols['SHO'][j] = '0'
                    except (TypeError, ValueError):
                        cols['SHO'][j] = '0'
    return cols


def _plant_duplicates(table: str, cols: dict, rng) -> dict:
    """For DUPLICATE_TARGETS, 20-50% of rows share a value with another row."""
    for (t, c) in spec.DUPLICATE_TARGETS:
        if t != table or c not in cols:
            continue
        n = len(cols[c])
        if n < 4:
            continue
        vals = [v for v in cols[c] if v is not None]
        if not vals:
            continue
        share = 0.2 + 0.3 * rng.random()
        k = max(2, int(share * n))
        idx = rng.sample(range(n), min(k, n))
        v = rng.choice(vals)
        for i in idx:
            cols[c][i] = v
    return cols


def _reserve_unmatched_parents(inst: dict, schema, rng) -> None:
    """After all tables are built, ensure each UNMATCHED_PARENT target has a parent tuple never drawn by any child."""
    for (pt, pc) in spec.UNMATCHED_PARENT:
        if pt not in inst or pc not in inst[pt]:
            continue
        parent_vals = [v for v in inst[pt][pc] if v is not None]
        if not parent_vals:
            continue
        child_cols = []
        for (ct, cc), (t2, c2) in schema.fks.items():
            if t2 == pt and c2 == pc and ct in inst and cc in inst[ct]:
                child_cols.append((ct, cc))
        if not child_cols:
            continue
        used = set()
        for ct, cc in child_cols:
            used.update(v for v in inst[ct][cc] if v is not None)
        unused = [v for v in parent_vals if v not in used]
        if unused:
            continue
        victim = parent_vals[0]
        for ct, cc in child_cols:
            col = inst[ct][cc]
            for i, v in enumerate(col):
                if v == victim:
                    others = [x for x in parent_vals if x != victim]
                    col[i] = rng.choice(others) if others else None
                    break
            if victim not in set(x for x in col if x is not None):
                break


def _reserve_unmatched_composite(inst: dict, schema, rng) -> None:
    """Reserve a full unused parent tuple for composite-key unmatched targets."""
    for (pt, pc) in spec.UNMATCHED_PARENT:
        if pt not in inst or pc not in inst[pt]:
            continue
        tm = schema.tables[pt]
        if len(tm.primary_key) < 2:
            continue
        key_cols = tm.primary_key
        if any(kc not in inst[pt] for kc in key_cols):
            continue
        n = len(inst[pt][key_cols[0]])
        if n == 0:
            continue
        child_tables = []
        for ct, ctm in schema.tables.items():
            if ct == pt or ct not in inst:
                continue
            fk_cols = {}
            for cm in ctm.columns:
                fk = schema.fks.get((ct, cm.name))
                if fk and fk[0] == pt and fk[1] in key_cols:
                    fk_cols[fk[1]] = cm.name
            if set(fk_cols) == set(key_cols):
                child_tables.append((ct, fk_cols))
        if not child_tables:
            continue
        used = set()
        for ct, fk_cols in child_tables:
            cn = len(inst[ct][next(iter(fk_cols.values()))])
            for i in range(cn):
                tup = tuple(inst[ct][fk_cols[kc]][i] for kc in key_cols)
                if all(x is not None for x in tup):
                    used.add(tup)
        unused = None
        for i in range(n):
            tup = tuple(inst[pt][kc][i] for kc in key_cols)
            if all(x is not None for x in tup) and tup not in used:
                unused = tup
                break
        if unused is not None:
            continue
        victim = None
        for i in range(n):
            tup = tuple(inst[pt][kc][i] for kc in key_cols)
            if all(x is not None for x in tup):
                victim = tup
                break
        if victim is None:
            continue
        for ct, fk_cols in child_tables:
            cn = len(inst[ct][next(iter(fk_cols.values()))])
            for i in range(cn):
                tup = tuple(inst[ct][fk_cols[kc]][i] for kc in key_cols)
                if tup == victim:
                    for j in range(n):
                        alt = tuple(inst[pt][kc][j] for kc in key_cols)
                        if all(x is not None for x in alt) and alt != victim:
                            for kc in key_cols:
                                inst[ct][fk_cols[kc]][i] = alt[key_cols.index(kc)]
                            break
                    break
            still_used = False
            for i in range(cn):
                tup = tuple(inst[ct][fk_cols[kc]][i] for kc in key_cols)
                if tup == victim:
                    still_used = True
                    break
            if not still_used:
                break


def verify_targets(schema, inst: dict, kept: dict, rng) -> dict:
    """Re-check planted targets on the rows that were actually written."""
    errs: dict = {}

    def _surviving(table: str, col: str) -> list:
        idx = kept.get(table, [])
        vals = inst.get(table, {}).get(col, [])
        return [vals[i] for i in idx if i < len(vals)]

    for (t, c) in spec.GROUP_SIZE_TARGETS:
        vals = [v for v in _surviving(t, c) if v is not None]
        if not vals:
            continue
        from collections import Counter
        cnt = Counter(vals)
        sizes = set(cnt.values())
        if not (1 in sizes and 2 in sizes and any(s >= 3 for s in sizes)):
            errs['group_size:%s.%s' % (t, c)] = errs.get('group_size:%s.%s' % (t, c), 0) + 1

    for (t, c) in spec.DUPLICATE_TARGETS:
        vals = [v for v in _surviving(t, c) if v is not None]
        if len(vals) < 4:
            continue
        from collections import Counter
        cnt = Counter(vals)
        dup_rows = sum(v for v in cnt.values() if v > 1)
        share = dup_rows / len(vals)
        if not (0.2 <= share <= 0.5):
            errs['duplicate:%s.%s' % (t, c)] = errs.get('duplicate:%s.%s' % (t, c), 0) + 1

    for (t, c, agg, kind) in spec.TIE_TARGETS:
        if kind == 'sum':
            pids = _surviving(t, c)
            shos = _surviving(t, 'SHO')
            if not pids or not shos:
                continue
            sums: dict = {}
            for pid, sho in zip(pids, shos):
                if pid is None:
                    continue
                try:
                    v = int(sho) if sho is not None else 0
                except (TypeError, ValueError):
                    v = 0
                sums[pid] = sums.get(pid, 0) + v
            if not sums:
                continue
            mx = max(sums.values())
            tied = [p for p, s in sums.items() if s == mx]
            if len(tied) < 2:
                errs['tie:sum:%s.%s' % (t, c)] = errs.get('tie:sum:%s.%s' % (t, c), 0) + 1
        elif kind == 'coalesce':
            shos = _surviving(t, 'SHO')
            if not shos:
                continue
            nulls = sum(1 for v in shos if v is None)
            if nulls < 2:
                errs['tie:coalesce:%s.%s' % (t, c)] = errs.get('tie:coalesce:%s.%s' % (t, c), 0) + 1
        elif kind == 'count':
            vals = [v for v in _surviving(t, c) if v is not None]
            if not vals:
                continue
            from collections import Counter
            cnt = Counter(vals)
            mx = max(cnt.values())
            tied = [v for v, k in cnt.items() if k == mx]
            if len(tied) < 2:
                errs['tie:count:%s.%s' % (t, c)] = errs.get('tie:count:%s.%s' % (t, c), 0) + 1

    for (pt, pc) in spec.UNMATCHED_PARENT:
        if pt not in inst or pc not in inst[pt]:
            continue
        parent_vals = [v for v in _surviving(pt, pc) if v is not None]
        if not parent_vals:
            continue
        child_cols = []
        for (ct, cc), (t2, c2) in schema.fks.items():
            if t2 == pt and c2 == pc and ct in inst and cc in inst[ct]:
                child_cols.append((ct, cc))
        if not child_cols:
            continue
        used = set()
        for ct, cc in child_cols:
            used.update(v for v in _surviving(ct, cc) if v is not None)
        if not any(v not in used for v in parent_vals):
            errs['unmatched:%s.%s' % (pt, pc)] = errs.get('unmatched:%s.%s' % (pt, pc), 0) + 1

    for (pt, pc) in spec.UNMATCHED_PARENT:
        if pt not in inst or pc not in inst[pt]:
            continue
        tm = schema.tables[pt]
        if len(tm.primary_key) < 2:
            continue
        key_cols = tm.primary_key
        if any(kc not in inst[pt] for kc in key_cols):
            continue
        idx = kept.get(pt, [])
        parent_tuples = set()
        for i in idx:
            tup = tuple(inst[pt][kc][i] for kc in key_cols)
            if all(x is not None for x in tup):
                parent_tuples.add(tup)
        if not parent_tuples:
            continue
        child_tables = []
        for ct, ctm in schema.tables.items():
            if ct == pt or ct not in inst:
                continue
            fk_cols = {}
            for cm in ctm.columns:
                fk = schema.fks.get((ct, cm.name))
                if fk and fk[0] == pt and fk[1] in key_cols:
                    fk_cols[fk[1]] = cm.name
            if set(fk_cols) == set(key_cols):
                child_tables.append((ct, fk_cols))
        if not child_tables:
            continue
        used = set()
        for ct, fk_cols in child_tables:
            cidx = kept.get(ct, [])
            for i in cidx:
                tup = tuple(inst[ct][fk_cols[kc]][i] for kc in key_cols)
                if all(x is not None for x in tup):
                    used.add(tup)
        if not any(tup not in used for tup in parent_tuples):
            errs['unmatched_composite:%s' % pt] = errs.get('unmatched_composite:%s' % pt, 0) + 1

    return errs


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) as appended rows on the compact DB."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            nullable = (not cm.notnull) and cm.pk_pos == 0
            samplers[(t, cm.name)] = _make_spec_sampler(
                t, cm, literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []), p, rng,
                len(tm.primary_key), nullable)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = _apply_null_rule(t, cols, schema, rng)
        cols = _enforce_death_after_birth(cols, rng)
        if t == 'Master':
            cols = _enforce_height_boundary(cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _plant_group_sizes(t, cols, rng)
        cols = _plant_ties(t, cols, rng)
        cols = _plant_duplicates(t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols
    _reserve_unmatched_parents(inst, schema, rng)
    _reserve_unmatched_composite(inst, schema, rng)
    return {t: inst[t] for t in schema.tables}
