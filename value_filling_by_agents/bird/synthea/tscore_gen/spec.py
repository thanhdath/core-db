"""The generation specification, as data (no SQL is ever evaluated from it)."""
import json
import os

TABLE_SIZES = {
    'all_prevalences': 40, 'patients': 60, 'encounters': 200, 'allergies': 30,
    'careplans': 120, 'conditions': 150, 'immunizations': 100, 'medications': 80,
    'observations': 300, 'procedures': 90, 'claims': 200,
}

ENUM_POOLS = {
    ('patients', 'gender'): ['F', 'M'],
    ('patients', 'race'): ['black', 'white', 'hispanic', 'asian'],
    ('patients', 'marital'): ['S', 'M'],
    ('patients', 'prefix'): ['Mr.', 'Mrs.', 'Ms.'],
    ('patients', 'suffix'): ['PhD', 'JD', 'MD'],
    ('all_prevalences', 'POPULATION TYPE'): ['LIVING'],
}

BOUNDARY_VALUES = {
    ('patients', 'last'): ['Homenick', 'homenick', 'Simonis', 'simonis', 'BERGE', 'berge'],
    ('patients', 'first'): ['Elly', 'elly', 'NORMAN', 'norman', 'Norman'],
    ('patients', 'gender'): ['F', 'f', 'M', 'm'],
    ('patients', 'prefix'): ['Mrs.', 'mrs.', 'Mr.', 'mr.', 'Ms.', 'ms.'],
    ('patients', 'birthdate'): ['1934-12-31', '1935-01-01', '1935-12-31', '1936-01-01'],
    ('conditions', 'DESCRIPTION'): ['Hypertension', 'hypertension', 'stroke', 'STROKE', 'Stroke'],
    ('conditions', 'START'): ['1987-12-31', '1988-01-01', '1988-12-31', '1989-01-01'],
    ('allergies', 'DESCRIPTION'): ['Allergy to grass pollen', 'allergy to grass pollen',
                                   'Allergy to eggs', 'allergy to eggs'],
    ('observations', 'UNITS'): ['kg', 'KG', 'cm', 'CM', 'kg/m2', 'KG/M2'],
    ('observations', 'VALUE'): [-0.0001, 0, 0.0001, 99.9999, 100, 100.0001],
}

LIKE_VARIANTS = {
    ('medications', 'DESCRIPTION'): ['Acetaminophen', 'Acetaminopheo', 'Acetaminophen x', 'acetaminophen'],
}

NULL_TARGETS = {
    ('patients', 'deathdate'): 0.687, ('patients', 'drivers'): 0.182,
    ('patients', 'passport'): 0.232, ('patients', 'prefix'): 0.202,
    ('patients', 'suffix'): 0.969, ('patients', 'maiden'): 0.724,
    ('patients', 'marital'): 0.293,
    ('careplans', 'STOP'): 0.46, ('careplans', 'REASONCODE'): 0.092,
    ('careplans', 'REASONDESCRIPTION'): 0.092, ('careplans', 'PATIENT'): 0.10,
    ('conditions', 'STOP'): 0.438,
    ('encounters', 'REASONCODE'): 0.718, ('encounters', 'REASONDESCRIPTION'): 0.718,
    ('medications', 'STOP'): 0.444, ('medications', 'REASONCODE'): 0.406,
    ('medications', 'REASONDESCRIPTION'): 0.406,
    ('observations', 'ENCOUNTER'): 0.037, ('observations', 'VALUE'): 0.006,
    ('observations', 'UNITS'): 0.006,
    ('procedures', 'REASONCODE'): 0.749, ('procedures', 'REASONDESCRIPTION'): 0.749,
    ('allergies', 'STOP'): 0.972, ('claims', 'DIAGNOSIS'): 1.0,
}

UNMATCHED_CHILD = {
    ('conditions', 'PATIENT'): True,
    ('allergies', 'PATIENT'): False,
}

FORMULAS = {
    'prevalence_percentage': True,
    'death_after_birth': True,
    'encounter_after_birth': True,
    'stop_after_start': [('careplans', 'START', 'STOP'), ('conditions', 'START', 'STOP'),
                         ('medications', 'START', 'STOP')],
    'non_negative': [('all_prevalences', 'OCCURRENCES'), ('claims', 'TOTAL')],
    'value_range': ('observations', 'VALUE', -1000.0, 1000.0),
}

DEPENDENCIES = {
    ('encounters', 'PATIENT'): ('patients', 'patient'),
    ('allergies', 'PATIENT'): ('patients', 'patient'),
    ('allergies', 'ENCOUNTER'): ('encounters', 'ID'),
    ('careplans', 'PATIENT'): ('patients', 'patient'),
    ('careplans', 'ENCOUNTER'): ('encounters', 'ID'),
    ('conditions', 'PATIENT'): ('patients', 'patient'),
    ('conditions', 'ENCOUNTER'): ('encounters', 'ID'),
    ('conditions', 'DESCRIPTION'): ('all_prevalences', 'ITEM'),
    ('immunizations', 'PATIENT'): ('patients', 'patient'),
    ('immunizations', 'ENCOUNTER'): ('encounters', 'ID'),
    ('medications', 'PATIENT'): ('patients', 'patient'),
    ('medications', 'ENCOUNTER'): ('encounters', 'ID'),
    ('observations', 'PATIENT'): ('patients', 'patient'),
    ('observations', 'ENCOUNTER'): ('encounters', 'ID'),
    ('procedures', 'PATIENT'): ('patients', 'patient'),
    ('procedures', 'ENCOUNTER'): ('encounters', 'ID'),
    ('claims', 'PATIENT'): ('patients', 'patient'),
    ('claims', 'ENCOUNTER'): ('encounters', 'ID'),
}


def load_specification() -> dict:
    """Return the specification dict (optionally overridden by specification.json)."""
    spec = {
        'table_sizes': dict(TABLE_SIZES),
        'enum_pools': {('%s.%s' % k): v for k, v in ENUM_POOLS.items()},
        'boundary_values': {('%s.%s' % k): v for k, v in BOUNDARY_VALUES.items()},
        'like_variants': {('%s.%s' % k): v for k, v in LIKE_VARIANTS.items()},
        'null_targets': {('%s.%s' % k): v for k, v in NULL_TARGETS.items()},
        'unmatched_child': {('%s.%s' % k): v for k, v in UNMATCHED_CHILD.items()},
        'formulas': FORMULAS,
        'dependencies': {('%s.%s' % k): v for k, v in DEPENDENCIES.items()},
    }
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, 'specification.json')
    if os.path.exists(p):
        try:
            with open(p) as f:
                extra = json.load(f)
            if isinstance(extra, dict):
                spec.update(extra)
        except Exception:
            pass
    return spec
