"""The generation specification, encoded as data (tscore_gen/specification.json is the source)."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC_PATH = os.path.join(_HERE, 'specification.json')

_DEFAULT = {
    'table_sizes': {'Episode': 21, 'Person': 40, 'Award': 20, 'Character_Award': 12,
                    'Credit': 200, 'Keyword': 60, 'Vote': 60},
    'columns': {
        'Episode': {
            'episode_id': {'pattern': 'episode_id',
                           'boundaries': ['S20-E5', 's20-e5', 'S20-E4', 'S20-E6']},
            'season': {'domain': [1, 30], 'boundaries': [19, 20, 21]},
            'episode': {'domain': [1, 30], 'boundaries': [1, 2, 4, 5, 6]},
            'number_in_series': {'domain': [1, 1000]},
            'rating': {'domain': [0.0, 10.0], 'boundaries': [4.9, 5.0, 5.1, 9.9, 10.0]},
            'votes': {'domain': [0, 100000], 'boundaries': [0, 1, 4, 5, 6]},
            'air_date': {'date_domain': [2007, 2010],
                         'boundaries': ['2007-12-31', '2008-01-01', '2008-12-31',
                                        '2009-01-01', '2009-12-31', '2010-01-01'],
                         'like_prefixes': ['2009%', '2008-10%', '2008%', '2008-11%',
                                           '2008-%', '2009-%']},
        },
        'Person': {
            'name': {'boundaries': ['Pamela Hayden', 'pamela hayden', 'Dan Castellaneta',
                                    'dan castellaneta', 'Ian Maxtone-Graham',
                                    'ian maxtone-graham', 'Emily Blunt', 'emily blunt',
                                    'Dell Hake', 'dell hake', 'Billy Kimball',
                                    'billy kimball']},
            'birthdate': {'date_domain': [1900, 2000],
                          'boundaries': ['1961-12-31', '1962-01-01', '1962-12-31', '1963-01-01'],
                          'like_prefixes': ['1962-%', '1962%']},
            'birth_country': {'boundaries': ['USA', 'usa']},
            'height_meters': {'domain': [1.0, 2.5]},
        },
        'Award': {
            'year': {'domain': [1990, 2030], 'boundaries': [2008, 2009, 2010]},
            'result': {'enum': ['Winner', 'Nominee'],
                       'boundaries': ['Winner', 'winner', 'Nominee', 'nominee']},
            'award_category': {'boundaries': ["People's Choice Award", "people's choice award",
                                              'WGA Award (TV)', 'wga award (tv)',
                                              'Jupiter Award ', 'jupiter award ']},
        },
        'Credit': {
            'person': {'boundaries': ['Pamela Hayden', 'pamela hayden', 'Emily Blunt',
                                      'emily blunt', 'Dell Hake', 'dell hake']},
            'episode_id': {'boundaries': ['S20-E10', 's20-e10', 'S20-E5', 's20-e5',
                                          'S20-E6', 's20-e6']},
            'role': {'boundaries': ['co-executive producer', 'CO-EXECUTIVE PRODUCER',
                                    'director', 'DIRECTOR', 'writer', 'WRITER']},
            'credited': {'enum': ['true', 'false'],
                         'boundaries': ['true', 'TRUE', 'false', 'FALSE', '', 'x']},
        },
        'Keyword': {
            'keyword': {'boundaries': ['riot', 'RIOT', 'cake', 'CAKE', 'ak', 'AK']},
        },
        'Vote': {
            'episode_id': {'boundaries': ['S20-E10', 's20-e10', 'S20-E5', 's20-e5',
                                          'S20-E6', 's20-e6']},
            'stars': {'domain': [1, 10], 'boundaries': [4, 5, 6, 7, 8, 9]},
            'votes': {'domain': [0, 100000], 'boundaries': [49, 50, 51, 199, 200, 201]},
            'percent': {'domain': [0.0, 100.0]},
        },
    },
    'null_shares': {
        'Person': {'birthdate': 0.642, 'birth_name': 0.71, 'birth_place': 0.667, 'birth_region': 0.699,
                   'birth_country': 0.678, 'height_meters': 0.864, 'nickname': 0.959},
        'Award': {'person': 0.147, 'role': 0.707, 'episode_id': 0.427, 'season': 1.0, 'song': 1.0},
        'Credit': {'person': 0.05, 'episode_id': 0.05},
        'Vote': {'episode_id': 0.05, 'stars': 0.05},
    },
    'formulas': {
        'Episode.season': 'season BETWEEN 1 AND 30',
        'Episode.episode': 'episode > 0',
        'Episode.number_in_series': 'number_in_series > 0',
        'Episode.rating': 'rating BETWEEN 0 AND 10',
        'Episode.votes': 'votes >= 0',
        'Person.height_meters': 'height_meters BETWEEN 1.0 AND 2.5',
        'Award.result': "result IN ('Winner','Nominee')",
        'Award.year': 'year BETWEEN 1990 AND 2030',
        'Credit.credited': "credited IN ('true','false')",
        'Vote.stars': 'stars BETWEEN 1 AND 10',
        'Vote.votes': 'votes >= 0',
        'Vote.percent': 'percent BETWEEN 0 AND 100',
    },
    'hard_formulas': ['Award.result', 'Credit.credited'],
}

_DEFAULT_NULL_SHARE = 0.1


def _merge_default(spec: dict) -> dict:
    """Fill any missing sections from the built-in default (never overrides a real spec)."""
    if not isinstance(spec, dict):
        return _DEFAULT
    out = dict(spec)
    for key in ('null_shares', 'formulas', 'hard_formulas', 'table_sizes'):
        if key not in out or out[key] is None:
            out[key] = _DEFAULT[key]
    cols = dict(spec.get('columns') or {})
    for t, cols_t in _DEFAULT['columns'].items():
        if t not in cols:
            cols[t] = cols_t
        else:
            merged = dict(cols_t)
            merged.update(cols[t])
            cols[t] = merged
    out['columns'] = cols
    return out


def load_specification() -> dict:
    """Read specification.json if present, else the built-in default."""
    if os.path.exists(_SPEC_PATH):
        try:
            with open(_SPEC_PATH) as f:
                spec = json.load(f)
            if isinstance(spec, dict):
                return _merge_default(spec)
        except Exception:
            pass
    return _DEFAULT


def column_spec(spec: dict, table: str, column: str) -> dict:
    """Per-column specification entry (empty dict if none)."""
    return (spec.get('columns', {}).get(table, {}) or {}).get(column, {}) or {}


def null_share(spec: dict, table: str, column: str, default: float = _DEFAULT_NULL_SHARE) -> float:
    """Compact-database NULL share for a nullable column."""
    shares = (spec.get('null_shares', {}) or {}).get(table, {}) or {}
    if column in shares:
        v = float(shares[column])
        return v if v > 0.0 else _DEFAULT_NULL_SHARE
    dflt = (_DEFAULT.get('null_shares', {}).get(table, {}) or {}).get(column)
    if dflt is not None:
        return float(dflt) if float(dflt) > 0.0 else _DEFAULT_NULL_SHARE
    return float(default) if float(default) > 0.0 else _DEFAULT_NULL_SHARE


def table_size(spec: dict, table: str, default: int = 20) -> int:
    """Target number of generated rows for a table."""
    return int((spec.get('table_sizes', {}) or {}).get(table, default))


def is_hard_formula(spec: dict, table: str, column: str) -> bool:
    """True if the column's semantic formula is enforced by clamping/enumeration."""
    return ('%s.%s' % (table, column)) in set(spec.get('hard_formulas', []) or [])
