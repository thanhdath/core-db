"""Specification loading and per-column sampling plans."""
import json
import os

NAME_POOL = ['Frank Lloyd Wright', 'Frank Gehry', 'Zaha Hadid', 'Mies Van Der Rohe', 'Le Corbusier',
             'Louis Kahn', 'Eero Saarinen', 'Ieoh Ming Pei', 'Norman Foster', 'Renzo Piano']
LOCATION_POOL = ['Guangxi , China', 'Arches National Park , Utah , USA', 'Zion National Park , Utah , USA',
                 'Ennedi Plateau , Chad', 'Negro Bill Canyon , Utah , USA', 'Guizhou , China',
                 'Coswarem', 'Donceel', 'Fexhe-le-haut-Clocher', 'Momalle', 'Othee', 'Pousset']
NOTE_POOL = ['Molenechos (Dutch)']
TYPE_POOL = ['Grondzeiler', 'Bergmolen']
GENDER_POOL = ['male', 'female']
NATIONALITY_POOL = ['American', 'Canadian', 'Iraqi, British', 'German, American', 'Swiss, French']

EXCEPTIONS = {
    ('mill', 'architect_id'): {'group_sizes': [1, 2, 3], 'tie_at_rank': [1]},
    ('architect', 'name'): {'group_sizes': [1, 2, 3], 'tie_at_rank': [1]},
    ('architect', 'nationality'): {'values': ['Canadian', 'canadian', 'American', 'american', 'Aan', 'aan',
                                              'Cn', 'cn', 'ic', 'IC'],
                                   'literals': ['American%', 'American'],
                                   'variants': ['Americao', 'American x', 'american'],
                                   'group_sizes': [1, 2, 3]},
    ('bridge', 'architect_id'): {'group_sizes': [1, 2, 3]},
    ('bridge', 'id'): {'aggregate_values': [2, 3, 4]},
    ('bridge', 'length_meters'): {'tie_at_rank': [1], 'direction': 'DESC',
                                  'rows_with_different_values': True},
    ('architect', 'gender'): {'values': ['female', 'FEMALE']},
    ('mill', 'built_year'): {'values': [1849, 1850, 1851]},
    ('mill', 'name'): {'duplicate_share': (0.2, 0.5)},
    ('mill', 'type'): {'values': TYPE_POOL},
}

FORMULAS = {
    ('bridge', 'length_feet'): ('round_half_up', ('length_meters', 3.28084)),
}
ENUMS = {
    ('architect', 'gender'): GENDER_POOL,
    ('mill', 'type'): TYPE_POOL,
}
YEAR_RANGE = (1700, 2020)
YEAR_BOUNDARY = [1849, 1850, 1851]
POSITIVE_REAL = True


def _spec_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specification.json')


def load_specification():
    """Read specification.json if present; return a plan dict or None."""
    p = _spec_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            raw = json.load(f)
    except Exception:
        return None
    return _plan_from_raw(raw)


def _plan_from_raw(raw: dict) -> dict:
    """Turn the raw specification into {table: {column: plan}}."""
    plan: dict = {}
    for t, cols in (raw.get('columns') or {}).items():
        for c, info in (cols or {}).items():
            plan.setdefault(t, {})[c] = dict(info or {})
    return plan


def spec_from_schema(schema) -> dict:
    """Fallback plan derived from the compact schema (generic rules)."""
    plan: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            plan.setdefault(t, {})[cm.name] = {'type': cm.type_str, 'nullable': not cm.notnull}
    return plan


def column_plan(spec: dict, table: str, column: str) -> dict:
    """Merged plan for one column: specification entry + built-in exception targets."""
    p = dict((spec.get(table) or {}).get(column) or {})
    exc = EXCEPTIONS.get((table, column))
    if exc:
        p.update(exc)
    return p


def enum_values(table: str, column: str):
    """Enumeration for a column, or None."""
    return ENUMS.get((table, column))


def formula(table: str, column: str):
    """Derived-column formula, or None."""
    return FORMULAS.get((table, column))


def length_feet_value(meters):
    """round-half-up(meters * 3.28084) -> float, or None for NULL operand."""
    if meters is None:
        return None
    import math
    x = float(meters) * 3.28084
    return float(math.floor(x + 0.5))
