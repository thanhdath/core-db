"""Specification loading and by-construction domain tables."""
import json
import re

_DEFAULT_ENUMS = {
    ('users', 'u_gender'): ['F', 'M'],
    ('users', 'occupation'): ['1', '2', '3', '4', '5'],
    ('actors', 'a_gender'): ['F', 'M'],
    ('movies', 'isEnglish'): ['T', 'F'],
    ('movies', 'country'): ['USA', 'France', 'UK', 'other'],
    ('movies2directors', 'genre'): ['Action', 'Adventure', 'Animation', 'Comedy', 'Crime',
                                    'Documentary', 'Drama', 'Horror'],
    ('u2base', 'rating'): ['0', '1', '2', '3', '4', '5'],
}
_DEFAULT_RANGES = {
    ('users', 'age'): (1, 100),
    ('directors', 'd_quality'): (-1, 6),
    ('directors', 'avg_revenue'): (0, 4),
    ('actors', 'a_quality'): (0, 5),
    ('movies', 'year'): (1, 5),
    ('movies', 'runningtime'): (0, 3),
    ('movies2actors', 'cast_num'): (0, 3),
}
_DEFAULT_SIZES = {'users': 40, 'directors': 20, 'actors': 60, 'movies': 50,
                  'movies2actors': 120, 'movies2directors': 60, 'u2base': 200}
_DEFAULT_BOUNDARY = {
    ('movies', 'movieid'): [2312851, 2312852, 2312853],
    ('u2base', 'movieid'): [1695218, 1695219, 1695220, 2462958, 2462959, 2462960],
    ('movies2directors', 'movieid'): [2312851, 2312852, 2312853],
    ('movies2actors', 'movieid'): [2312851, 2312852, 2312853],
    ('movies2directors', 'genre'): ['drama', 'DRAMA', 'horror', 'HORROR', 'Horror'],
    ('movies', 'country'): ['France', 'france', 'USA', 'usa', 'UK', 'uk'],
    ('u2base', 'userid'): [2462958, 2462959, 2462960],
    ('u2base', 'rating'): ['0', '1', '2', '3', '4', '5'],
    ('users', 'age'): ['17', '18', '19', '24', '25', '26'],
    ('directors', 'd_quality'): [-1, 0, 1, 4, 5, 6],
    ('actors', 'a_gender'): ['F', 'f'],
    ('users', 'u_gender'): ['F', 'f'],
}
_CASE_VARIANT_COLUMNS = {('movies2directors', 'genre'), ('movies', 'country'),
                         ('actors', 'a_gender'), ('users', 'u_gender')}


def _key(t: str, c: str) -> tuple:
    return (t.lower(), c.lower())


def _parse_range(formula: str):
    m = re.search(r'BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', formula, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _parse_enum(formula: str):
    m = re.search(r'IN\s*\(([^)]*)\)', formula, re.I)
    if not m:
        return None
    return [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]


def _widen_ranges(spec: dict) -> None:
    """Widen integer ranges so every in-type boundary target is admitted (spec uncertainty note)."""
    for k, vals in spec['boundary'].items():
        if k not in spec['ranges']:
            continue
        ints = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
        if not ints:
            continue
        lo, hi = spec['ranges'][k]
        spec['ranges'][k] = (min([lo] + ints), max([hi] + ints))


def load_specification(raw: dict) -> dict:
    """Normalise a specification JSON into the internal spec dict."""
    spec = {'enums': {}, 'ranges': {}, 'sizes': {}, 'boundary': {}, 'case_variant': set(_CASE_VARIANT_COLUMNS),
            'numeric_text': set()}
    for rule in raw.get('semantic_rules_and_formulas', []) or []:
        t, c, f = rule.get('table'), rule.get('column'), rule.get('formula', '')
        if not t or not c:
            continue
        k = _key(t, c)
        e = _parse_enum(f)
        if e:
            spec['enums'][k] = e
            if all(re.fullmatch(r'-?\d+', x) for x in e):
                spec['numeric_text'].add(k)
            continue
        r = _parse_range(f)
        if r:
            spec['ranges'][k] = r
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        spec['sizes'][t.lower()] = int(n)
    for ex in raw.get('per_column_exceptions', []) or []:
        col = ex.get('column', '')
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        vals = (ex.get('targets') or {}).get('values')
        if vals:
            spec['boundary'][_key(t, c)] = list(vals)
    _widen_ranges(spec)
    return spec


def spec_from_compact(orig: str) -> dict:
    """Fallback: default domains plus observed values read from the compact database."""
    from .schema import read_schema
    sch = read_schema(orig)
    spec = {'enums': dict(_DEFAULT_ENUMS), 'ranges': dict(_DEFAULT_RANGES),
            'sizes': dict(_DEFAULT_SIZES), 'boundary': dict(_DEFAULT_BOUNDARY),
            'case_variant': set(_CASE_VARIANT_COLUMNS), 'numeric_text': set()}
    for k, e in spec['enums'].items():
        if all(re.fullmatch(r'-?\d+', str(x)) for x in e):
            spec['numeric_text'].add(k)
    for (t, c), vals in sch.original_values.items():
        k = _key(t, c)
        if k in spec['enums'] or k in spec['ranges']:
            continue
        nums = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
        if nums and len(set(nums)) <= 8:
            spec['ranges'][k] = (min(nums), max(nums))
    _widen_ranges(spec)
    return spec


def domain_for(spec: dict, table: str, column: str):
    """('enum', list) | ('range', (lo, hi)) | ('numeric_text', list) | None."""
    key = (table.lower(), column.lower())
    if key in spec['enums']:
        return ('numeric_text' if key in spec['numeric_text'] else 'enum'), spec['enums'][key]
    if key in spec['ranges']:
        return 'range', spec['range'] if False else spec['ranges'][key]
    return None


def boundary_for(spec, table: str, column: str) -> list:
    return list(spec['boundary'].get(_key(table, column), []))


def size_for(spec: dict, table: str, rng) -> int:
    """Per-instance table size: the specified size with a small random variation (0-230 cap)."""
    base = spec['sizes'].get(table.lower())
    if base is None:
        return int(30 * rng.random() + int(rng.random() * 200))
    lo = max(0, int(base * 0.6))
    hi = min(230, max(lo + 1, int(base * 1.4)))
    return rng.randint(lo, hi)
