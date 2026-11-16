"""Specification loading: per-column value domains, ranges, enums, NULL targets, sizes."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC_PATH = os.path.join(_HERE, 'specification.json')

_DEFAULT = {
    'table_sizes': {'people': 8, 'church': 6, 'wedding': 3},
    'null_targets': [],
    'columns': {
        'church.Church_ID': {'kind': 'int_pk', 'start': 1},
        'church.Name': {'kind': 'text', 'duplicate_share': (0.2, 0.5)},
        'church.Organized_by': {'kind': 'text', 'group_sizes': '1,2,>=3'},
        'church.Open_Date': {'kind': 'int_year', 'range': (-2000, 2100),
                             'boundaries': [-1730, -1729, -1728, 1839, 1840, 1841, 1849, 1850, 1851, 1852],
                             'tie_rank': 3, 'group_sizes': '1,2,>=3'},
        'church.Continuation_of': {'kind': 'text'},
        'people.People_ID': {'kind': 'int_pk', 'start': 1},
        'people.Name': {'kind': 'text_name'},
        'people.Country': {'kind': 'text_country'},
        'people.Is_Male': {'kind': 'enum', 'values': ['T', 'F']},
        'people.Age': {'kind': 'int_quantity', 'range': (0, 120), 'boundaries': [29, 30, 31, 32]},
        'wedding.Church_ID': {'kind': 'int_fk', 'parent': 'church.Church_ID', 'duplicate_share': (0.2, 0.5)},
        'wedding.Male_ID': {'kind': 'int_fk', 'parent': 'people.People_ID'},
        'wedding.Female_ID': {'kind': 'int_fk', 'parent': 'people.People_ID'},
        'wedding.Year': {'kind': 'int_year', 'range': (1900, 2100), 'boundaries': [2015, 2016, 2017]},
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_specification(db: str) -> dict:
    """Return the specification dict for db (file if present, else built-in defaults)."""
    spec = _DEFAULT
    if os.path.exists(_SPEC_PATH):
        try:
            with open(_SPEC_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                if db in data and isinstance(data[db], dict):
                    spec = _merge(_DEFAULT, data[db])
                elif 'columns' in data:
                    spec = _merge(_DEFAULT, data)
        except Exception:
            spec = _DEFAULT
    return spec


def column_spec(spec: dict, table: str, column: str) -> dict:
    """Per-column spec entry (empty dict when unknown)."""
    return (spec.get('columns') or {}).get('%s.%s' % (table, column), {})
