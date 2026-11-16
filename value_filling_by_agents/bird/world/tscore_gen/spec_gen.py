"""Specification-driven row builder (by construction, no SQL rule evaluation)."""
import re
from collections import defaultdict

CONTINENTS = ('Asia', 'Europe', 'North America', 'South America', 'Africa', 'Oceania', 'Antarctica')
OFFICIAL = ('T', 'F', 't', 'f')
SPEC_DEFAULTS = {
    'table_sizes': {'Country': 40, 'City': 120, 'CountryLanguage': 80},
    'null_targets': {'Country.IndepYear': 0.20, 'Country.LifeExpectancy': 0.07,
                     'Country.GNPOld': 0.25, 'Country.HeadOfState': 0.01, 'Country.Capital': 0.03},
    'country_codes': ['USA', 'usa', 'GBR', 'FRA', 'DEU', 'ITA', 'CHN', 'JPN', 'ESP', 'NLD'],
    'code2': ['US', 'us', 'GB', 'FR', 'DE', 'IT', 'CN', 'JP', 'ES', 'NL'],
    'country_names': ['United States', 'usa', 'Cyprus', 'cyprus', 'Italy', 'italy', 'China',
                      'china', 'France', 'Germany', 'Japan', 'Spain', 'Netherlands', 'Brazil'],
    'government_forms': ['Republic', 'republic', 'Constitutional Monarchy', 'Federal Republic',
                         'Parliamentary Coprincipality', 'Islamic Emirate', 'Emirate Federation'],
    'regions': ['Baltic Countries', 'baltic countries', 'Caribbean', 'Southern and Central Asia',
                'Central Africa', 'Southern Europe', 'Middle East', 'Polynesia'],
    'languages': ['Portuguese', 'portuguese', 'English', 'english', 'Dutch', 'Spanish',
                  'Balochi', 'Dari', 'Pashto', 'Turkmenian'],
    'local_names': ['Aruba', 'Afganistan/Afqanestan', 'Angola', 'Anguilla', 'Shqiperia',
                    'Andorra', 'Nederlandse Antillen'],
    'heads': ['Beatrix', 'Mohammad Omar', 'Jose Eduardo dos Santos', 'Elisabeth II',
              'Rexhep Mejdani', 'Zayid bin Sultan al-Nahayan', 'Fernando de la Rua'],
}


def _load_spec_tuning(spec: dict) -> dict:
    """Merge specification.json overrides for table sizes, NULL targets and generator pools."""
    out = {k: (v.copy() if isinstance(v, dict) else list(v)) for k, v in SPEC_DEFAULTS.items()}
    if not spec:
        return out
    sizes = spec.get('table_sizes_per_instance') or {}
    if sizes:
        for t, n in sizes.items():
            if t in out['table_sizes']:
                out['table_sizes'][t] = int(n)
    nt = spec.get('null_targets') or {}
    for k, v in nt.items():
        try:
            out['null_targets'][k] = float(str(v).split('~')[-1].split('%')[0]) / 100.0
        except Exception:
            pass
    for e in spec.get('per_column_exceptions') or []:
        tg = e.get('targets') or {}
        vals = tg.get('values') or []
        if not vals:
            continue
        col = (e.get('table'), e.get('column'))
        if col == ('Country', 'Code'):
            out['country_codes'] = list(dict.fromkeys(out['country_codes'] + [str(v) for v in vals]))
        elif col == ('Country', 'Name'):
            out['country_names'] = list(dict.fromkeys(out['country_names'] + [str(v) for v in vals]))
        elif col == ('Country', 'GovernmentForm'):
            out['government_forms'] = list(dict.fromkeys(out['government_forms'] + [str(v) for v in vals]))
        elif col == ('Country', 'Region'):
            out['regions'] = list(dict.fromkeys(out['regions'] + [str(v) for v in vals]))
        elif col == ('CountryLanguage', 'Language'):
            out['languages'] = list(dict.fromkeys(out['languages'] + [str(v) for v in vals]))
    return out


def _pool_fill(base: list, extra: list, rng, target: int) -> list:
    """Extend a pool with pool literals and chance-string variants up to at least `target`."""
    out = list(dict.fromkeys([str(x) for x in base]))
    for x in extra:
        if x is not None and str(x) not in out:
            out.append(str(x))
    if out:
        i = 0
        while len(out) < target and i < 40 * target:
            v = rng.choice(out[:len(base) + len(extra)]) if (base or extra) else str(rng.randint(1000, 9999))
            u = rng.random()
            if u < 0.4:
                nv = v.upper() if rng.random() < 0.5 else (v[:1].upper() + v[1:].lower())
            elif u < 0.7:
                nv = v + ' '
            elif u < 0.85 and len(v) > 2:
                nv = v[:-1]
            else:
                nv = str(rng.randint(1000, 9999))
            if nv not in out:
                out.append(nv)
            i += 1
    return out


def _maybe_case_variant(v: str, rng) -> str:
    """~5% of values become near-duplicates (case variant, trailing space)."""
    if rng.random() >= 0.05 or not isinstance(v, str) or not v:
        return v
    r = rng.random()
    if r < 0.4:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if r < 0.8:
        return v + ' '
    return v[:-1] if len(v) > 2 else v


def _duplicated(rng, shared: list, n: int, share_lo=0.25, share_hi=0.45) -> list:
    """Draw n values s.t."""
    if not shared:
        return [None] * n
    target = int(round(n * rng.uniform(share_lo, share_hi)))
    forced = [rng.choice(shared) for _ in range(max(0, target))]
    rest = [rng.choice(shared) for _ in range(n - len(forced))]
    out = forced + rest
    rng.shuffle(out)
    return out


def _rebalance_duplicates(rng, values: list, shared: list, pinned: set = None,
                          share_lo=0.25, share_hi=0.45) -> list:
    """Re-balance a value list so the duplicate share stays in [share_lo, share_hi] after forcing."""
    n = len(values)
    if n < 2 or not shared:
        return values
    pinned = pinned or set()
    counts = defaultdict(int)
    for v in values:
        counts[v] += 1
    dup_rows = sum(c for c in counts.values() if c > 1)
    lo = int(round(n * share_lo))
    hi = int(round(n * share_hi))
    if lo <= dup_rows <= hi:
        return values
    out = list(values)
    if dup_rows < lo:
        singles = [i for i, v in enumerate(out) if counts[v] == 1 and i not in pinned]
        rng.shuffle(singles)
        need = lo - dup_rows
        for i in singles[:need]:
            out[i] = rng.choice(shared)
    else:
        seen = set()
        for i, v in enumerate(out):
            if i in pinned:
                seen.add(v)
                continue
            if counts[v] > 1 and v in seen and dup_rows > hi:
                out[i] = rng.choice(shared)
                counts[v] -= 1
                dup_rows -= 1
            else:
                seen.add(v)
    return out


def _null_mask(rng, n: int, share: float, nullable: bool) -> list:
    """NULL mask with at least one NULL when nullable (even if share == 0)."""
    if not nullable:
        return [False] * n
    if n <= 0:
        return []
    if share <= 0:
        share = max(1.0 / n, 0.01)
    k = max(1, int(round(n * share)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    mask = [False] * n
    for i in idx:
        mask[i] = True
    return mask


def _ensure_group_variation_int(rng, values: list, groups: dict, lo=0, hi=100) -> list:
    """Within each group with >=2 rows, ensure at least two different values (integers)."""
    out = list(values)
    for g, idxs in groups.items():
        if len(idxs) < 2:
            continue
        if len({out[i] for i in idxs}) >= 2:
            continue
        a, b = idxs[0], idxs[1]
        out[a] = rng.randint(lo, hi)
        out[b] = out[a] + rng.randint(1, max(1, hi - lo))
        if out[b] > hi:
            out[b] = hi
    return out


def _ensure_group_variation_float(rng, values: list, groups: dict, lo=0.0, hi=100.0,
                                  precision=2, pinned: set = None) -> list:
    """Within each group with >=2 non-NULL rows, ensure at least two different values (floats)."""
    out = list(values)
    pinned = pinned or set()
    for g, idxs in groups.items():
        nonnull = [i for i in idxs if out[i] is not None]
        if len(nonnull) < 2:
            continue
        if len({out[i] for i in nonnull}) >= 2:
            continue
        cand = [i for i in nonnull if i not in pinned]
        if len(cand) < 2:
            cand = nonnull
        a, b = cand[0], cand[1]
        base = round(rng.uniform(lo, hi), precision)
        out[a] = base
        delta = round(rng.uniform(0.1, max(0.1, (hi - lo) / 10.0)), precision)
        nb = round(base + delta, precision)
        if nb > hi:
            nb = round(hi, precision)
        out[b] = nb
    return out


def _country_generated(schema, spec, pool, rng) -> dict:
    """Generate the Country table according to the specification."""
    tm = schema.tables['Country'] if 'Country' in schema.tables else None
    if tm is None:
        return {}
    cfg = _load_spec_tuning(spec)
    n = int(cfg['table_sizes'].get('Country', 40))
    if n <= 0:
        return {}
    cols = [c.name for c in tm.columns]
    obs = schema.original_values
    nm = {c.name: c for c in tm.columns}

    def obs_pool(col):
        return [v for v in obs.get(('Country', col), []) if v is not None]

    def pool_for(col):
        return [v for v in pool.get(('Country', col), []) if v is not None]

    codes = _pool_fill(obs_pool('Code') + cfg['country_codes'],
                       pool_for('Code') + [v.upper() for v in pool_for('Code')], rng, max(8, n))
    code_row = [rng.choice([c for c in codes if len(c) == 3] or codes) for _ in range(n)]
    reserved = ['USA', 'usa'] if n >= 2 else []
    for k, v in enumerate(reserved):
        code_row[k] = v
    existing_codes = {str(x) for x in obs.get(('Country', 'Code'), []) if x is not None}
    seen = set(existing_codes)
    emitted_reserved = set()
    for i in range(n):
        c = str(code_row[i])
        if len(c) != 3:
            c = (c.upper() + 'XXX')[:3]
        if c in reserved and c not in emitted_reserved:
            emitted_reserved.add(c)
            seen.add(c)
            code_row[i] = c
            continue
        if c in seen:
            base = c
            j = 0
            while c in seen:
                j += 1
                c = (base[:2] + chr(ord('A') + (j % 26)))[:3]
        seen.add(c)
        code_row[i] = c

    names_shared = _pool_fill(obs_pool('Name') + cfg['country_names'],
                              pool_for('Name'), rng, max(10, n // 2))
    name_row = _duplicated(rng, names_shared, n)
    forced_names = ['Cyprus', 'cyprus', 'Italy', 'italy', 'China', 'china']
    pinned = set()
    for k, v in enumerate(forced_names):
        if k < n:
            name_row[k] = v
            pinned.add(k)
    name_row = _rebalance_duplicates(rng, name_row, names_shared, pinned=pinned)

    continent_row = [rng.choice(CONTINENTS) for _ in range(n)]

    region_row = []
    for _ in range(n):
        u = rng.random()
        if u < 0.20:
            region_row.append('Baltic Countries')
        elif u < 0.35:
            region_row.append('baltic countries')
        else:
            region_row.append(rng.choice(_pool_fill(obs_pool('Region') + cfg['regions'], pool_for('Region'), rng, 10)))

    sa = [round(rng.uniform(0.0, 2.0e6), 2) for _ in range(n)]
    sa_pinned = set()
    if n >= 6:
        tie_v = round(rng.uniform(100.0, 90000.0), 2)
        sa[0] = sa[1] = sa[2] = tie_v
        sa_pinned.update((0, 1, 2))
        mn = round(rng.uniform(0.5, 50.0), 2)
        sa[3] = sa[4] = mn
        sa_pinned.update((3, 4))
    sa = [max(0.0, x) for x in sa]

    iy_null = _null_mask(rng, n, cfg['null_targets'].get('Country.IndepYear', 0.20), True)
    iy = [None if iy_null[i] else int(rng.randint(1000, 2100)) for i in range(n)]

    pop = [int(rng.randint(0, 1_200_000_000)) for _ in range(n)]
    if n >= 2:
        pop[0] = pop[1]

    le_null = _null_mask(rng, n, cfg['null_targets'].get('Country.LifeExpectancy', 0.07), True)
    le = [None if le_null[i] else round(rng.uniform(30.0, 85.0), 1) for i in range(n)]
    le_pinned = set()
    if n >= 4:
        mx = round(rng.uniform(80.0, 90.0), 1)
        le[0] = mx
        le[1] = mx
        le_pinned.update((0, 1))

    gnp = [round(rng.uniform(0.0, 6.0e6), 2) for _ in range(n)]
    if n >= 6:
        gnp[0] = 0.0
        gnp[1] = 0.1

    go_null = _null_mask(rng, n, cfg['null_targets'].get('Country.GNPOld', 0.25), True)
    go = [None if go_null[i] else round(rng.uniform(0.0, 6.0e6), 2) for i in range(n)]
    if n >= 4:
        tie = round(rng.uniform(1.0, 1000.0), 2)
        go[0] = tie
        go[1] = tie

    ln_shared = _pool_fill(obs_pool('LocalName') + cfg['local_names'], pool_for('LocalName'), rng, max(8, n // 2))
    ln = _duplicated(rng, ln_shared, n)

    gf = []
    for _ in range(n):
        u = rng.random()
        if u < 0.25:
            gf.append('Republic')
        elif u < 0.40:
            gf.append('republic')
        else:
            gf.append(rng.choice(_pool_fill(obs_pool('GovernmentForm') + cfg['government_forms'],
                                             pool_for('GovernmentForm'), rng, 10)))
    gf = [g if g is not None else 'Republic' for g in gf]

    hos_null = _null_mask(rng, n, cfg['null_targets'].get('Country.HeadOfState', 0.01), True)
    hs_shared = _pool_fill(obs_pool('HeadOfState') + cfg['heads'], pool_for('HeadOfState'), rng, max(6, n // 2))
    hs = _duplicated(rng, hs_shared, n)
    hs = [None if hos_null[i] else hs[i] for i in range(n)]

    cap_null = _null_mask(rng, n, cfg['null_targets'].get('Country.Capital', 0.03), True)
    city_ids = [v for v in obs.get(('City', 'ID'), []) if v is not None]
    cap = []
    for i in range(n):
        if cap_null[i] or not city_ids:
            cap.append(None)
        else:
            cap.append(int(rng.choice(city_ids)))

    c2_shared = _pool_fill(obs_pool('Code2') + cfg['code2'], pool_for('Code2'), rng, max(8, n))
    c2_shared = [c for c in c2_shared if len(c) == 2]
    if not c2_shared:
        c2_shared = ['US', 'GB']
    c2 = [rng.choice(c2_shared) for _ in range(n)]
    existing_code2 = {str(x) for x in obs.get(('Country', 'Code2'), []) if x is not None}
    seen_c2 = set(existing_code2)
    for i in range(n):
        c = str(c2[i])
        if len(c) != 2:
            c = (c.upper() + 'XX')[:2]
        if c in seen_c2:
            for j in range(1, 27):
                cand = (c[:1] + chr(ord('A') + (j % 26)))[:2]
                if cand not in seen_c2:
                    c = cand
                    break
        c2[i] = c
        seen_c2.add(c)

    groups = defaultdict(list)
    for i, cont in enumerate(continent_row):
        groups[cont].append(i)
    pop = _ensure_group_variation_int(rng, pop, groups, 0, 1_200_000_000)
    le = _ensure_group_variation_float(rng, le, groups, 0.0, 100.0, precision=1, pinned=le_pinned)
    le = [None if le_null[i] else le[i] for i in range(n)]
    sa = _ensure_group_variation_float(rng, sa, groups, 0.0, 2_000_000.0, precision=2, pinned=sa_pinned)

    out = {}
    for c in cols:
        if c == 'Code':
            out[c] = code_row
        elif c == 'Name':
            out[c] = name_row
        elif c == 'Continent':
            out[c] = continent_row
        elif c == 'Region':
            out[c] = region_row
        elif c == 'SurfaceArea':
            out[c] = sa
        elif c == 'IndepYear':
            out[c] = iy
        elif c == 'Population':
            out[c] = pop
        elif c == 'LifeExpectancy':
            out[c] = le
        elif c == 'GNP':
            out[c] = gnp
        elif c == 'GNPOld':
            out[c] = go
        elif c == 'LocalName':
            out[c] = ln
        elif c == 'GovernmentForm':
            out[c] = gf
        elif c == 'HeadOfState':
            out[c] = hs
        elif c == 'Capital':
            out[c] = cap
        elif c == 'Code2':
            out[c] = c2
        else:
            spec_col = nm[c]
            t = (spec_col.type_str or '').lower()
            if 'int' in t:
                out[c] = [int(rng.randint(0, 1000000)) for _ in range(n)]
            elif any(k in t for k in ('real', 'float', 'double', 'numeric', 'decimal')):
                out[c] = [round(rng.uniform(0.0, 1000.0), 2) for _ in range(n)]
            else:
                out[c] = [_maybe_case_variant('C' + str(i), rng) for i in range(n)]
    return {'table': 'Country', 'cols': out, 'codes': code_row}


def _language_generated(schema, spec, pool, rng, country_codes: list) -> dict:
    """Generate CountryLanguage rows: FK only to existing/generated Country codes, PK (CountryCode,Language)."""
    tm = schema.tables.get('CountryLanguage')
    if tm is None:
        return {}
    cfg = _load_spec_tuning(spec)
    n = int(cfg['table_sizes'].get('CountryLanguage', 80))
    if n <= 0:
        return {}
    obs = schema.original_values
    cols = [c.name for c in tm.columns]

    def obs_pool(col):
        return [v for v in obs.get(('CountryLanguage', col), []) if v is not None]

    def pool_for(col):
        return [v for v in pool.get(('CountryLanguage', col), []) if v is not None]

    codes = [c for c in country_codes if c is not None]
    existing_fk = [v for v in obs.get(('CountryLanguage', 'CountryCode'), []) if v is not None]
    fk_pool = list(dict.fromkeys(existing_fk + codes))
    if not fk_pool:
        return {}

    langs_shared = _pool_fill(obs_pool('Language') + cfg['languages'], pool_for('Language'), rng, max(10, 24))
    lang_row = _duplicated(rng, langs_shared, n)
    forced_langs = ['Portuguese', 'portuguese', 'English', 'english']
    pinned = set()
    for k, v in enumerate(forced_langs):
        if k < n:
            lang_row[k] = v
            pinned.add(k)
    lang_row = _rebalance_duplicates(rng, lang_row, langs_shared, pinned=pinned)

    cc_row = [rng.choice(fk_pool) for _ in range(n)]

    pk_seen = set()
    existing_pk = set()
    try:
        for i in range(min(len(obs.get(('CountryLanguage', 'CountryCode'), [])),
                           len(obs.get(('CountryLanguage', 'Language'), [])))):
            existing_pk.add((obs[('CountryLanguage', 'CountryCode')][i], obs[('CountryLanguage', 'Language')][i]))
    except Exception:
        pass
    pk_seen |= existing_pk
    for i in range(n):
        pair = (cc_row[i], lang_row[i])
        if pair in pk_seen:
            base = str(lang_row[i]) if lang_row[i] is not None else 'Lang'
            for j in range(1, 10):
                cand = base + ' ' * j
                if (cc_row[i], cand) not in pk_seen:
                    lang_row[i] = cand
                    pair = (cc_row[i], cand)
                    break
        pk_seen.add(pair)

    iso = []
    for _ in range(n):
        tv = rng.random()
        if tv < 0.6:
            iso.append('T')
        else:
            iso.append('F')
    if n >= 4:
        iso[0] = 'T'
        iso[1] = 't'
        iso[2] = 'F'
        iso[3] = 'f'

    pct = [round(rng.uniform(0.0, 100.0), 1) for _ in range(n)]
    groups = defaultdict(list)
    for i, c in enumerate(cc_row):
        groups[c].append(i)
    for c, idxs in groups.items():
        if len(idxs) >= 2:
            pct[idxs[0]] = round(rng.uniform(0.0, 50.0), 1)
            pct[idxs[1]] = round(pct[idxs[0]] + rng.uniform(1.0, 40.0), 1)
            if pct[idxs[1]] > 100.0:
                pct[idxs[1]] = 100.0

    out = {}
    for c in cols:
        if c == 'CountryCode':
            out[c] = cc_row
        elif c == 'Language':
            out[c] = lang_row
        elif c == 'IsOfficial':
            out[c] = iso
        elif c == 'Percentage':
            out[c] = pct
        else:
            tcol = next((x.type_str for x in tm.columns if x.name == c), '')
            t = (tcol or '').lower()
            if 'int' in t:
                out[c] = [int(rng.randint(0, 100)) for _ in range(n)]
            elif 'real' in t:
                out[c] = [round(rng.uniform(0.0, 100.0), 2) for _ in range(n)]
            else:
                out[c] = [_maybe_case_variant('L' + str(i), rng) for i in range(n)]
    return {'table': 'CountryLanguage', 'cols': out}


def _city_generated(schema, spec, pool, rng, country_codes: list) -> dict:
    """Generate City rows: only new IDs (> max compact ID), FK only to existing/generated Country."""
    tm = schema.tables.get('City')
    if tm is None:
        return {}
    cfg = _load_spec_tuning(spec)
    n = int(cfg['table_sizes'].get('City', 0))
    if n <= 0:
        return {}
    obs = schema.original_values
    cols = [c.name for c in tm.columns]

    def obs_pool(col):
        return [v for v in obs.get(('City', col), []) if v is not None]

    def pool_for(col):
        return [v for v in pool.get(('City', col), []) if v is not None]

    id_max = 0
    if obs.get(('City', 'ID')):
        id_max = max(int(x) for x in obs[('City', 'ID')] if x is not None) or 0
    ids = [id_max + 1 + i for i in range(n)]

    names_shared = _pool_fill(obs_pool('Name') + ['PHL', 'phl', 'PHL%', '%PHL', 'phl%', '%phl'],
                              pool_for('Name'), rng, max(10, 20))
    name_row = _duplicated(rng, names_shared, n)
    forced = ['PHL', 'phl', '%PHL', '%phl', 'PHL%', 'phl%']
    pinned = set()
    for k, v in enumerate(forced):
        if k < n:
            name_row[k] = v
            pinned.add(k)
    name_row = _rebalance_duplicates(rng, name_row, names_shared, pinned=pinned)

    fk_pool = list(dict.fromkeys([v for v in obs.get(('City', 'CountryCode'), []) if v is not None]
                                  + [c for c in country_codes if c]))
    if not fk_pool:
        return {}
    cc_row = [rng.choice(fk_pool) for _ in range(n)]

    dist_shared = _pool_fill(obs_pool('District') + ['England', 'england'], pool_for('District'), rng,
                             max(10, n))
    dist_row = _duplicated(rng, dist_shared, n)

    pop = [int(rng.randint(0, 20_000_000)) for _ in range(n)]
    groups = defaultdict(list)
    for i, c in enumerate(cc_row):
        groups[c].append(i)
    for c, idxs in groups.items():
        if len(idxs) >= 2:
            pop[idxs[0]] = int(rng.randint(10000, 100000))
            pop[idxs[1]] = pop[idxs[0]] + int(rng.randint(1, 10000))

    out = {}
    for c in cols:
        if c == 'ID':
            out[c] = ids
        elif c == 'Name':
            out[c] = name_row
        elif c == 'CountryCode':
            out[c] = cc_row
        elif c == 'District':
            out[c] = dist_row
        elif c == 'Population':
            out[c] = pop
        else:
            tcol = next((x.type_str for x in tm.columns if x.name == c), '')
            t = (tcol or '').lower()
            if 'int' in t:
                out[c] = [int(rng.randint(0, 1000)) for _ in range(n)]
            elif 'real' in t:
                out[c] = [round(rng.uniform(0.0, 100.0), 2) for _ in range(n)]
            else:
                out[c] = [_maybe_case_variant('D' + str(i), rng) for i in range(n)]
    return {'table': 'City', 'cols': out}


def build_spec_instance(schema, spec: dict, pool: dict, rng) -> dict:
    """Return {table: {col: [values...]}} of new rows to append to the compact DB copy."""
    out: dict = {}
    country = _country_generated(schema, spec, pool, rng)
    if country:
        out['Country'] = country['cols']
        codes = country.get('codes') or []
    else:
        codes = [v for v in schema.original_values.get(('Country', 'Code'), []) if v is not None]

    compact_codes = {str(x) for x in schema.original_values.get(('Country', 'Code'), []) if x is not None}
    inserted_codes = []
    seen = set(compact_codes)
    for c in codes:
        if c is None:
            continue
        if c in seen:
            continue
        seen.add(c)
        inserted_codes.append(c)
    safe_codes = [c for c in inserted_codes if c not in compact_codes]
    if not safe_codes:
        safe_codes = [c for c in codes if c is not None]

    cl = _language_generated(schema, spec, pool, rng, safe_codes)
    if cl:
        out['CountryLanguage'] = cl['cols']
    city = _city_generated(schema, spec, pool, rng, safe_codes)
    if city:
        out['City'] = city['cols']
    return out
