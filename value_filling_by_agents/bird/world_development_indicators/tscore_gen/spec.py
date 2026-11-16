"""Specification loading and per-column domain construction (by construction, in Python)."""
import json
import os
import re

_SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specification.json')

_FALLBACK_ENUMS = {
    ('Country', 'Region'): ['South Asia', 'Europe & Central Asia', 'Middle East & North Africa',
                            'East Asia & Pacific', 'Sub-Saharan Africa', 'Latin America & Caribbean',
                            'North America', ''],
    ('Country', 'IncomeGroup'): ['Low income', 'Upper middle income', 'High income: nonOECD',
                                 'Lower middle income', 'High income: OECD', ''],
    ('Country', 'LendingCategory'): ['IDA', 'IBRD', 'Blend', ''],
    ('Country', 'OtherGroups'): ['HIPC', 'Euro area', ''],
    ('Country', 'SystemOfNationalAccounts'): [
        'Country uses the 1993 System of National Accounts methodology.',
        'Country uses the 1968 System of National Accounts methodology.',
        'Country uses the 2008 System of National Accounts methodology.', ''],
    ('Country', 'PppSurveyYear'): ['', 'Rolling', '2011', '2011 (household consumption only).'],
    ('Country', 'BalanceOfPaymentsManualInUse'): ['', 'IMF Balance of Payments Manual, 6th edition.'],
    ('Country', 'ExternalDebtReportingStatus'): ['Actual', 'Preliminary', 'Estimate', ''],
    ('Country', 'SystemOfTrade'): ['General trade system', 'Special trade system', ''],
    ('Country', 'GovernmentAccountingConcept'): ['Consolidated central government',
                                                 'Budgetary central government', ''],
    ('Country', 'ImfDataDisseminationStandard'): ['General Data Dissemination System (GDDS)',
                                                  'Special Data Dissemination Standard (SDDS)', ''],
    ('Country', 'VitalRegistrationComplete'): ['Yes', 'Yes. Vital registration for Guernsey and Jersey.', ''],
    ('Country', 'SnaPriceValuation'): ['Value added at basic prices (VAB)',
                                       'Value added at producer prices (VAP)', ''],
    ('Series', 'UnitOfMeasure'): ['', '`', '%', '2005 PPP $', '2011 PPP $'],
    ('Series', 'AggregationMethod'): ['', 'Weighted average', 'Sum', 'Gap-filled total', 'Median',
                                      'Linear mixed-effect model estimates', 'Unweighted average'],
    ('Series', 'LicenseType'): ['Open', 'Restricted'],
    ('Series', 'Periodicity'): ['Annual'],
}

_FALLBACK_RANGES = {
    ('Country', 'LatestIndustrialData'): (1960, 2015),
    ('Country', 'LatestTradeData'): (1960, 2015),
    ('Country', 'LatestWaterWithdrawalData'): (1960, 2015),
    ('Indicators', 'Year'): (1960, 2015),
    ('Indicators', 'Value'): (0, 1000000),
}

_FALLBACK_NULL_SHARE = {
    ('Country', 'LatestIndustrialData'): 0.543,
    ('Country', 'LatestTradeData'): 0.247,
    ('Country', 'LatestWaterWithdrawalData'): 0.271,
}

_FALLBACK_ALWAYS_NULL = [('Series', 'OtherNotes'), ('Series', 'OtherWebLinks'), ('Series', 'RelatedIndicators')]

_FALLBACK_DUPLICATE = [('Country', 'ShortName'), ('Country', 'TableName'), ('Country', 'LongName'),
                       ('Footnotes', 'Year')]
_FALLBACK_TIES = [('Country', 'ShortName'), ('Indicators', 'IndicatorCode'), ('Indicators', 'Value'),
                  ('Indicators', 'Year')]
_FALLBACK_BOUNDARY = [('Country', 'ShortName'), ('Country', 'TableName'), ('Country', 'LongName'),
                      ('Country', 'CurrencyUnit'), ('Indicators', 'CountryName'),
                      ('Indicators', 'IndicatorName'), ('Indicators', 'IndicatorCode'),
                      ('Indicators', 'Year'), ('Series', 'SeriesCode'), ('CountryNotes', 'Seriescode'),
                      ('Footnotes', 'Year')]
_FALLBACK_LIKE = [('Indicators', 'IndicatorName'), ('Footnotes', 'Year'), ('SeriesNotes', 'Year')]

_FALLBACK_SIZES = {'Country': 40, 'Series': 40, 'CountryNotes': 80, 'Footnotes': 200,
                   'Indicators': 400, 'SeriesNotes': 40}

_FALLBACK_DEPENDENCIES = [
    {'child_column': 'Countrycode', 'parent_table': 'Country', 'parent_column': 'CountryCode',
     'copied_columns': []},
    {'child_column': 'Seriescode', 'parent_table': 'Series', 'parent_column': 'SeriesCode',
     'copied_columns': []},
    {'child_column': 'CountryCode', 'parent_table': 'Country', 'parent_column': 'CountryCode',
     'copied_columns': ['CountryName']},
    {'child_column': 'IndicatorCode', 'parent_table': 'Series', 'parent_column': 'SeriesCode',
     'copied_columns': ['IndicatorName']},
]

_BOUNDARY_LITERALS = {
    ('Country', 'ShortName'): ['Arab World', 'Brazil', 'Malaysia', 'Sudan'],
    ('Country', 'TableName'): ['Malaysia', 'Finland', 'Arab World', 'Latin America & Caribbean'],
    ('Country', 'LongName'): ['Albania', 'Malaysia'],
    ('Country', 'CurrencyUnit'): ['', 'Euro', 'euro', 'EURO', 'x'],
    ('Indicators', 'CountryName'): ['Arab World', 'Brazil', 'Sudan'],
    ('Indicators', 'IndicatorName'): ['CO2 emissions FROM gaseous fuel consumption (kt)',
                                      'Agricultural land (% of land area)', 'GDP growth (annual %)',
                                      'Land under cereal production', 'Rural population'],
    ('Indicators', 'IndicatorCode'): ['DT.DOD.DECT.CD', 'SP.DYN.CDRT.IN'],
    ('Series', 'SeriesCode'): ['SP.DYN.TO65.MA.ZS', 'BX.KLT.DINV.CD.WD', 'SP.DYN.AMRT.FE'],
    ('CountryNotes', 'Seriescode'): ['DT.DOD.DECT.CD', 'BX.KLT.DINV.CD.WD', 'SP.DYN.CDRT.IN'],
    ('Footnotes', 'Year'): ['YR2', 'YR2001', 'YR2002'],
}

_YEAR_BOUNDARIES = [1979, 1980, 1981, 1982]


def load_specification(path: str = None) -> dict:
    """Read specification.json if present, else return an empty dict (fallbacks apply)."""
    p = path or _SPEC_PATH
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _split_col(s: str) -> tuple:
    parts = str(s).split('.')
    return (parts[-2], parts[-1]) if len(parts) >= 2 else (None, parts[-1])


def _enum_from_formula(formula: str):
    """Parse `Col IN ('a', 'b', ...)` into a list of literals."""
    m = re.search(r"\bIN\s*\((.*)\)\s*$", formula, re.I | re.S)
    if not m:
        return None
    body = m.group(1)
    vals = re.findall(r"'((?:[^']|'')*)'", body)
    if not vals:
        return None
    return [v.replace("''", "'") for v in vals]


def _single_value_from_formula(formula: str):
    """Parse `Col IS NULL OR Col = 'value'` (or `Col = 'value'`) into a single-value enum."""
    if not re.search(r"\bIS\s+NULL\b", formula, re.I):
        return None
    m = re.search(r"=\s*'((?:[^']|'')*)'", formula)
    if not m:
        return None
    return [m.group(1).replace("''", "'")]


def _range_from_formula(formula: str):
    m = re.search(r"BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)", formula, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r">=\s*(-?\d+)", formula)
    if m:
        return int(m.group(1)), None
    return None


def _like_prefix_from_formula(formula: str):
    m = re.search(r"LIKE\s+'([^']*)'", formula, re.I)
    if m:
        return m.group(1)
    return None


def build_spec(raw: dict, schema) -> dict:
    """Turn the specification into per-column domains keyed by (table, column) with real names."""
    tmap = {t.lower(): t for t in schema.tables}
    cmap = {(t.lower(), c.name.lower()): c.name for t, tm in schema.tables.items() for c in tm.columns}

    def key(t, c):
        if t is None:
            return None
        tt = tmap.get(str(t).lower())
        if tt is None:
            return None
        cc = cmap.get((tt.lower(), str(c).lower()))
        return (tt, cc) if cc is not None else None

    def is_key(k):
        if k is None or k[0] not in schema.tables:
            return False
        tm = schema.tables[k[0]]
        return k[1] in tm.primary_key

    enums, ranges, null_share, always_null = {}, {}, {}, set()
    duplicate, ties, boundary, like_cols = set(), set(), set(), set()
    sizes = dict(_FALLBACK_SIZES)
    deps = []

    for (t, c), vals in _FALLBACK_ENUMS.items():
        k = key(t, c)
        if k and vals:
            enums[k] = list(vals)
    for (t, c), r in _FALLBACK_RANGES.items():
        k = key(t, c)
        if k:
            ranges[k] = r
    for (t, c), s in _FALLBACK_NULL_SHARE.items():
        k = key(t, c)
        if k:
            null_share[k] = s
    for t, c in _FALLBACK_ALWAYS_NULL:
        k = key(t, c)
        if k:
            always_null.add(k)
    for t, c in _FALLBACK_DUPLICATE:
        k = key(t, c)
        if k and not is_key(k):
            duplicate.add(k)
    for t, c in _FALLBACK_TIES:
        k = key(t, c)
        if k:
            ties.add(k)
    for t, c in _FALLBACK_BOUNDARY:
        k = key(t, c)
        if k:
            boundary.add(k)
    for t, c in _FALLBACK_LIKE:
        k = key(t, c)
        if k:
            like_cols.add(k)
    for d in _FALLBACK_DEPENDENCIES:
        pt, pc = key(d['parent_table'], d['parent_column'])
        if not pt:
            continue
        for ct_name in schema.tables:
            k = key(ct_name, d['child_column'])
            if k is None:
                continue
            ct, cc = k
            if schema.fks.get((ct, cc)) == (pt, pc):
                cps = []
                for x in d.get('copied_columns', []):
                    xc = next((c.name for c in schema.tables[ct].columns
                               if c.name.lower() == str(x).lower()), None)
                    if xc:
                        cps.append((ct, xc))
                deps.append({'child': (ct, cc), 'parent': (pt, pc), 'copied': cps})

    for rule in raw.get('semantic_rules_and_formulas', []) or []:
        t, c = rule.get('table'), rule.get('column')
        k = key(t, c)
        if not k:
            continue
        f = str(rule.get('formula', ''))
        if re.search(r'\bIS\s+NULL\b', f, re.I) and 'OR' not in f.upper():
            always_null.add(k)
            continue
        if re.search(r'\b=\s*\w+\.\w+\s+AND\b', f) or '=' in f and re.search(r'\w+\.\w+', f.split('=')[-1]):
            continue
        pref = _like_prefix_from_formula(f)
        if pref:
            like_cols.add(k)
            ranges[('__like__',) + k] = pref
            continue
        vals = _enum_from_formula(f)
        if vals is not None:
            enums[k] = vals
            continue
        sv = _single_value_from_formula(f)
        if sv is not None:
            enums[k] = sv
            continue
        r = _range_from_formula(f)
        if r is not None:
            ranges[k] = r
    for d in raw.get('dependencies', []) or []:
        ck = key(d.get('child_table'), d.get('child_column'))
        pk = key(d.get('parent_table'), d.get('parent_column'))
        if ck is None or pk is None:
            continue
        ct, cc = ck
        pt, pc = pk
        if schema.fks.get((ct, cc)) == (pt, pc):
            cps = []
            for x in d.get('copied_columns', []) or []:
                xc = next((c.name for c in schema.tables[ct].columns if c.name.lower() == str(x).lower()), None)
                if xc:
                    cps.append((ct, xc))
            deps.append({'child': (ct, cc), 'parent': (pt, pc), 'copied': cps})
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        tt = tmap.get(str(t).lower())
        if tt:
            sizes[tt] = int(n)
    for exc in raw.get('per_column_exceptions', []) or []:
        pat = exc.get('pattern')
        cols = (exc.get('targets') or {}).get('columns') or []
        for s in cols:
            k = key(*_split_col(s))
            if not k:
                continue
            if pat == 'duplicates_for_distinct':
                if not is_key(k):
                    duplicate.add(k)
            elif pat == 'ties_for_order_limit':
                ties.add(k)
            elif pat == 'comparison_boundary':
                boundary.add(k)
            elif pat == 'like_near_variant':
                like_cols.add(k)

    for k, vals in _BOUNDARY_LITERALS.items():
        kk = key(*k)
        if kk:
            boundary.add(kk)
            cur = enums.setdefault(kk, [])
            for v in vals:
                if v not in cur:
                    cur.append(v)

    yk = key('Indicators', 'Year')
    if yk:
        boundary.add(yk)
        ranges.setdefault(('__year_boundary__',) + yk, _YEAR_BOUNDARIES)

    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.notnull or cm.pk_pos > 0:
                continue
            vals = schema.original_values.get((t, cm.name), [])
            if vals:
                null_share.setdefault((t, cm.name), sum(1 for v in vals if v is None) / float(len(vals)))

    copied_cols = set()
    for d in deps:
        for cc in d['copied']:
            copied_cols.add(cc)

    return {'enums': enums, 'ranges': ranges, 'null_share': null_share, 'always_null': always_null,
            'duplicate': duplicate, 'ties': ties, 'boundary': boundary, 'like': like_cols,
            'sizes': sizes, 'deps': deps, 'copied_cols': copied_cols}
