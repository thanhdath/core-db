"""Specification loading / derivation (tscore_gen/specification.json or compact-DB statistics)."""
import json
import sqlite3


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _stats(orig: str) -> dict:
    """Column statistics of the compact database (rows, distinct, min/max, null rate)."""
    con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
    out: dict = {}
    try:
        tabs = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by rowid")]
        for t in tabs:
            n = con.execute('select count(*) from %s' % _q(t)).fetchone()[0]
            cols = {}
            for r in con.execute('pragma table_info(%s)' % _q(t)).fetchall():
                c = r[1]
                d = con.execute('select count(distinct %s), sum(case when %s is null then 1 else 0 end) '
                                'from %s' % (_q(c), _q(c), _q(t))).fetchone()
                mn = mx = None
                try:
                    mn, mx = con.execute('select min(%s), max(%s) from %s' % (_q(c), _q(c), _q(t))).fetchone()
                except sqlite3.Error:
                    pass
                cols[c] = {'type': r[2] or '', 'nullable': not bool(r[3]), 'distinct': d[0] or 0,
                           'null_rate': (d[1] or 0) / n if n else 0.0, 'min': mn, 'max': mx}
            out[t] = {'rows': n, 'columns': cols}
    finally:
        con.close()
    return out


def spec_from_stats(orig: str) -> dict:
    """Derive a specification dict from the compact database (fallback when no JSON exists)."""
    st = _stats(orig)
    sizes = {t: v['rows'] for t, v in st.items()}
    ranges, enums, nulls = {}, {}, {}
    for t, tv in st.items():
        for c, cv in tv['columns'].items():
            key = '%s.%s' % (t, c)
            ty = (cv['type'] or '').lower()
            if cv['nullable']:
                nulls[key] = max(cv['null_rate'], 0.05)
            if any(k in ty for k in ('int', 'real', 'float', 'numeric', 'decimal')) and cv['min'] is not None:
                ranges[key] = [cv['min'], cv['max']]
            if cv['distinct'] and cv['distinct'] <= 12 and not any(
                    k in ty for k in ('int', 'real', 'float', 'numeric', 'decimal')):
                con = sqlite3.connect('file:%s?mode=ro&immutable=1' % orig, uri=True)
                try:
                    vals = [r[0] for r in con.execute(
                        'select distinct %s from %s where %s is not null order by 1' % (_q(c), _q(t), _q(c)))]
                finally:
                    con.close()
                enums[key] = vals
    return {'table_sizes': sizes, 'ranges': ranges, 'enums': enums, 'null_shares': nulls,
            'group_size_targets': {}, 'dependencies': [], 'comparison_literals': {},
            'duplicate_share': 0.3, 'tie_targets': []}


def load_specification(path: str) -> dict:
    """Read specification.json and normalise it into the dict consumed by the samplers."""
    with open(path) as f:
        raw = json.load(f)
    spec = spec_from_stats(raw.get('_orig', '')) if raw.get('_orig') else {
        'table_sizes': {}, 'ranges': {}, 'enums': {}, 'null_shares': {},
        'group_size_targets': {}, 'dependencies': [], 'comparison_literals': {},
        'duplicate_share': 0.3, 'tie_targets': []}
    spec['table_sizes'] = dict(raw.get('table_sizes_per_instance') or spec['table_sizes'])
    for rule in raw.get('semantic_rules_and_formulas') or []:
        t, c, f = rule.get('table'), rule.get('column'), (rule.get('formula') or '')
        key = '%s.%s' % (t, c)
        if 'BETWEEN' in f.upper():
            try:
                lo = int(f.upper().split('BETWEEN')[1].split('AND')[0].strip())
                hi = int(f.upper().split('AND')[1].strip())
                spec['ranges'][key] = [lo, hi]
            except Exception:
                pass
        elif ' IN (' in f.upper():
            inner = f[f.index('(') + 1:f.rindex(')')]
            vals = []
            for x in inner.split(','):
                x = x.strip().strip("'\"")
                try:
                    vals.append(int(x))
                except ValueError:
                    vals.append(x)
            spec['enums'][key] = vals
    for ex in raw.get('per_column_exceptions') or []:
        pat = ex.get('pattern')
        tg = ex.get('targets') or {}
        if pat == 'comparison_boundary':
            for col in tg.get('columns') or []:
                spec['comparison_literals'].setdefault(col, [])
                for v in tg.get('values') or []:
                    if v not in spec['comparison_literals'][col]:
                        spec['comparison_literals'][col].append(v)
        elif pat == 'group_sizes':
            for col in tg.get('columns') or []:
                spec['group_size_targets'][col] = [1, 2, 3]
        elif pat == 'duplicates_for_distinct':
            spec['duplicate_share'] = 0.3
        elif pat == 'ties_for_order_limit':
            for col in tg.get('columns') or []:
                if col not in spec['tie_targets']:
                    spec['tie_targets'].append(col)
        elif pat == 'null_in_count_column':
            for col in tg.get('columns') or []:
                spec['null_shares'].setdefault(col, 0.05)
    for d in raw.get('dependencies') or []:
        spec['dependencies'].append(d)
    for col in raw.get('null_targets') or []:
        spec['null_shares'].setdefault(col, 0.05)
    return spec
