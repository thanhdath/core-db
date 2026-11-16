"""Specification model: value pools, ranges, enums, near-variants, NULL shares, table sizes."""
import re

_OBSERVED = {
    'Inst': {'instID': [1000, 1010, 1020, 1030, 1040, 1050, 1060, 1070],
             'name': ['University of Oxford', 'Northeastern University', 'Indiana University', 'Google',
                      'Tohoku University', 'University of Pennsylvania', 'Portland State University', 'INRIA'],
             'country': ['UK', 'USA', 'Japan', 'France']},
    'Authors': {'authID': [50, 51, 52, 53, 54, 55, 56, 57],
                'lname': ['Gibbons', 'Hinze', 'James', 'Shivers', 'Turon', 'Ahmed', 'Blume', 'Ohori'],
                'fname': ['Jeremy', 'Ralf', 'Daniel W. H.', 'Olin', 'Aaron', 'Amal', 'Matthias', 'Atsushi']},
    'Papers': {'paperID': [200, 201, 202, 203, 204, 205, 206],
               'title': ['Just do it: Simple Monadic Equational Reasoning',
                         'Proving the Unique Fixed-Point Principle Correct: An Adventure with Category Theory',
                         'Functional Pearl: Modular Rollback through Control Logging',
                         'An Equivalence-Preserving CPS Translation via Multi-Language Semantics',
                         'Making Standard ML a Practical Database Programming Language',
                         'Nameless, Painless', 'Binders Unbound']},
    'Authorship': {'authID': [50, 51, 52, 53, 54, 55, 56, 57], 'instID': [1000, 1010, 1020, 1030, 1040, 1070, 1050, 1060],
                   'paperID': [200, 201, 202, 203, 204, 205, 206], 'authOrder': [1, 2, 3]},
}

_EXCEPTIONS = {
    ('Papers', 'title'): {
        'like_literals': ['%Database%', '%Functio%', '%Functional%', '%Databas%', '%tabase%'],
        'variants': ['Database', 'Databasf', 'Database x', 'database', 'Functio', 'Functip', 'Functio x', 'functio'],
        'duplicate_share': (0.2, 0.5), 'group_sizes': (1, 2, 3), 'tie': True},
    ('Papers', 'paperID'): {'group_sizes': (1, 2, 3), 'tie': True, 'unmatched_parent': True},
    ('Authors', 'lname'): {'boundary': ['Ueno', 'ueno', 'Turon', 'turon'],
                           'duplicate_share': (0.2, 0.5), 'group_sizes': (1, 2, 3), 'tie': True},
    ('Authors', 'fname'): {'boundary': ['Katsuhiro', 'katsuhiro', 'Aaron', 'aaron', 'Stephanie', 'stephanie'],
                           'duplicate_share': (0.2, 0.5), 'group_sizes': (1, 2, 3), 'tie': True},
    ('Authors', 'authID'): {'group_sizes': (1, 2, 3), 'tie': True, 'unmatched_parent': True},
    ('Authorship', 'paperID'): {'unmatched_parent': True},
    ('Authorship', 'authID'): {'unmatched_parent': True},
    ('Authorship', 'instID'): {'unmatched_parent': True,
                               'equal_and_one_step_from': 'Inst.instID'},
    ('Authorship', 'authOrder'): {'boundary': [1, 2, 3], 'tie': True, 'rows_with_different_values': True},
    ('Inst', 'name'): {'boundary': ['Tokohu University', 'tokohu university', ' Universit', ' universit',
                                    'TokUniversity', 'tokuniversity', 'Tokohu Univty', 'tokohu univty'],
                       'duplicate_share': (0.2, 0.5), 'tie': True, 'group_sizes': (1, 2, 3)},
    ('Inst', 'instID'): {'group_sizes': (1, 2, 3), 'unmatched_parent': True, 'tie': True},
    ('Inst', 'country'): {'boundary': ['USA', 'usa']},
}

_RULES = {
    ('Authorship', 'authOrder'): ('between', 1, 3),
    ('Inst', 'country'): ('in', ['UK', 'USA', 'Japan', 'France']),
    ('Inst', 'instID'): ('gt', 0),
    ('Authors', 'authID'): ('gt', 0),
    ('Papers', 'paperID'): ('gt', 0),
}

_SIZES = {'Inst': 8, 'Authors': 13, 'Papers': 7, 'Authorship': 14}


def _norm_key(t, c):
    return (str(t), str(c))


def spec_from_columns(schema) -> dict:
    """Build the specification data from the compact database's observed values."""
    pools, null_share, types = {}, {}, {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            k = _norm_key(t, cm.name)
            vals = [v for v in schema.original_values.get((t, cm.name), []) if v is not None]
            pools[k] = list(dict.fromkeys(vals))
            types[k] = (cm.type_str or '').lower()
            null_share[k] = 0.0 if (cm.notnull or cm.pk_pos > 0) else 0.07
    return _assemble(pools, null_share, types)


def load_specification(raw: dict, schema) -> dict:
    """Merge a specification.json (generic rules + per-column exceptions) with observed values."""
    base = spec_from_columns(schema)
    if not isinstance(raw, dict):
        return base
    for col in raw.get('per_column_exceptions') or []:
        name = str(col.get('column', ''))
        if '.' not in name:
            continue
        t, c = name.split('.', 1)
        k = _norm_key(t, c)
        if k not in base['pools']:
            continue
        tg = col.get('targets') or {}
        ex = base['exceptions'].setdefault(k, {})
        if 'literals' in tg:
            ex['like_literals'] = list(tg['literals'])
        if 'variants' in tg:
            ex['variants'] = list(tg['variants'])
        if 'values' in tg:
            ex['boundary'] = list(tg['values'])
        if 'duplicate_share' in tg:
            ex['duplicate_share'] = (0.2, 0.5)
        if 'group_sizes' in tg:
            ex['group_sizes'] = (1, 2, 3)
        if 'tie_at_rank' in tg:
            ex['tie'] = True
        if 'equal_and_one_step_from' in tg:
            ex['equal_and_one_step_from'] = tg['equal_and_one_step_from'][0]
        if 'qualifying_rows' in tg:
            ex['rows_with_different_values'] = True
        if tg.get('parent_rows_without_children'):
            ex['unmatched_parent'] = True
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        if t in base['sizes']:
            base['sizes'][t] = int(n)
    return base


def _assemble(pools: dict, null_share: dict, types: dict) -> dict:
    """Attach exceptions and rules to the pools."""
    exceptions = {}
    for k, ex in _EXCEPTIONS.items():
        if k in pools:
            exceptions[k] = dict(ex)
    rules = {k: v for k, v in _RULES.items() if k in pools}
    sizes = {t: _SIZES.get(t, 0) for t in {k[0] for k in pools}}
    return {'pools': pools, 'null_share': null_share, 'types': types,
            'exceptions': exceptions, 'rules': rules, 'sizes': sizes}


def check_rule(spec: dict, table: str, column: str, value) -> bool:
    """SQL three-valued logic: a rule holds when its expression is not FALSE (NULL passes)."""
    if value is None:
        return True
    r = spec['rules'].get(_norm_key(table, column))
    if not r:
        return True
    op = r[0]
    try:
        if op == 'between':
            return r[1] <= value <= r[2]
        if op == 'in':
            return value in r[1]
        if op == 'in_ci':
            return str(value).lower() in {str(x).lower() for x in r[1]}
        if op == 'gt':
            return value > r[1]
    except TypeError:
        return True
    return True


def near_variants(value: str, rng, n: int = 3) -> list:
    """Case variants, one-character edits, prefix/suffix and dropped-character variants."""
    if not isinstance(value, str) or not value:
        return []
    out = [value.lower(), value.upper(), value.capitalize()]
    i = rng.randrange(len(value))
    out.append(value[:i] + value[i + 1:])
    out.append(value[:i] + rng.choice('abcdefghijklmnopqrstuvwxyz') + value[i + 1:])
    out.append(value + ' x')
    out.append(' ' + value)
    out.append(value[:-1] if len(value) > 1 else value)
    out = [v for v in dict.fromkeys(out) if v != value]
    rng.shuffle(out)
    return out[:n]


def like_variants(literals: list, rng) -> list:
    """LIKE patterns without '%' plus near-variants of their bodies."""
    out = []
    for lit in literals:
        body = str(lit).replace('%', '')
        if body:
            out.append(body)
            out.extend(near_variants(body, rng, 2))
    return out


def is_like_match(value, pattern: str) -> bool:
    """Python re-implementation of SQL LIKE (case-insensitive for ASCII)."""
    if value is None:
        return False
    rx = '^' + re.escape(str(pattern)).replace('%', '.*').replace('_', '.') + '$'
    return re.match(rx, str(value), re.IGNORECASE | re.DOTALL) is not None
