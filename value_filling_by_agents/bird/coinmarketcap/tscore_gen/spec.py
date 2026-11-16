"""Specification loader: per-column exceptions, enum domains, boundary literals, sizes."""
import json
import os

_DEFAULT = {
    'table_sizes': {'coins': 40, 'historical': 200},
    'enums': {
        ('coins', 'status'): ['active', 'untracked', 'inactive', 'extinct'],
        ('coins', 'category'): ['coin', 'token'],
    },
    'boundaries': {
        ('coins', 'name'): ['Bitcoin', 'bitcoin', 'Litecoin', 'litecoin', 'Bicoin', 'bicoin',
                            'Peercoin', 'peercoin'],
        ('coins', 'slug'): ['bitcoin', 'BITCOIN', 'peercoin', 'PEERCOIN'],
        ('coins', 'symbol'): ['BTC', 'btc'],
        ('coins', 'subreddit'): ['bitcoin', 'BITCOIN', 'litecoin', 'LITECOIN'],
        ('coins', 'date_added'): ['2013-12-31', '2014-01-01', '2014-12-31', '2015-01-01'],
        ('historical', 'date'): ['2012-12-31', '2013-01-01', '2013-05-02', '2013-05-03',
                                 '2013-05-04', '2013-12-31', '2014-01-01'],
        ('historical', 'open'): [-0.0001, 0.0, 0.0001],
        ('historical', 'circulating_supply'): [9999999.9999, 10000000.0, 10000000.0001],
        ('historical', 'total_supply'): [9999999.9999, 10000000.0, 10000000.0001],
        ('historical', 'cmc_rank'): [1, 5],
        ('historical', 'percent_change_1h'): [0.0],
    },
    'like_literals': {
        ('coins', 'date_added'): ['2014%'],
        ('historical', 'date'): ['2013-%', '2013-05-29%', '2013-05-29', '2013%', '2016-10-11'],
    },
    'null_share': {
        ('coins', 'name'): 0.01,
        ('coins', 'tag_names'): 0.15,
        ('historical', 'open'): 0.15,
    },
    'duplicate_share': {
        ('coins', 'name'): 0.30,
        ('historical', 'date'): 0.30,
        ('historical', 'price'): 0.30,
    },
    'tie_columns': {
        ('coins', 'name'): 'ASC',
        ('historical', 'date'): 'ASC',
        ('historical', 'high'): 'DESC',
        ('historical', 'percent_change_24h'): 'ASC',
    },
}


def _key(k: str) -> tuple:
    t, c = k.split('.', 1)
    return (t, c)


def load_specification(path: str = None) -> dict:
    """Load tscore_gen/specification.json if present, else the built-in defaults."""
    spec = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _DEFAULT.items()}
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'specification.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        for ex in raw.get('per_column_exceptions', []):
            col = _key(ex['column'])
            pat = ex.get('pattern')
            tg = ex.get('targets', {})
            if pat == 'enum_small' and 'values' in tg:
                spec['enums'][col] = list(tg['values'])
            elif pat == 'comparison_boundary' and 'values' in tg:
                spec['boundaries'][col] = list(tg['values'])
            elif pat == 'like_near_variant' and 'literals' in tg:
                spec['like_literals'][col] = list(tg['literals'])
            elif pat == 'null_rows' and 'null_share' in tg:
                try:
                    spec['null_share'][col] = float(tg['null_share'])
                except (TypeError, ValueError):
                    pass
            elif pat == 'duplicates_for_distinct' and 'duplicate_share' in tg:
                try:
                    spec['duplicate_share'][col] = float(str(tg['duplicate_share']).split('-')[0].strip().rstrip('%')) / 100.0
                except (TypeError, ValueError):
                    pass
            elif pat == 'ties_for_order_limit' and 'direction' in tg:
                spec['tie_columns'][col] = str(tg['direction']).split()[0].upper()
        sizes = raw.get('table_sizes_per_instance')
        if isinstance(sizes, dict):
            spec['table_sizes'] = {k: int(v) for k, v in sizes.items()}
    return spec
