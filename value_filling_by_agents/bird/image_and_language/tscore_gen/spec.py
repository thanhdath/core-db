"""Specification helpers: per-column exceptions, enum pools, sizes/ties/duplicates, NULL rule, sequential keys for
appended PKs, and near-variant string/int pools."""
import re

ENUM_LABELS = {
    'ATT_CLASSES': {
        'ATT_CLASS': ['building s', 'indoors', 'cluttered', 'park', 'two story', 'very large',
                      'bike', 'cast', 'white', 'WHITE', 'electrical', 'ELECTRICAL', 'blue', 'BLUE',
                      'scattered'],
        'ATT_CLASS_ID': list(range(0, 8)),
    },
    'OBJ_CLASSES': {
        'OBJ_CLASS': ['awning', 'goggles', 'dot', 'kitchen', 'KITCHEN', 'wall', 'WALL',
                      'feathers', 'beak', 'column', 'surface', 'man', 'MAN'],
        'OBJ_CLASS_ID': list(range(0, 300)),
    },
    'PRED_CLASSES': {
        'PRED_CLASS': ['playing on', 'looking a', 'to left of', 'beyond', 'covers', 'are',
                       'reading', 'enjoying', 'parked on', 'PARKED ON'],
        'PRED_CLASS_ID': list(range(0, 8)),
    },
}

BOUNDARY_STRINGS = {
    ('ATT_CLASSES', 'ATT_CLASS'): ['white', 'WHITE', 'electrical', 'ELECTRICAL', 'blue', 'BLUE'],
    ('OBJ_CLASSES', 'OBJ_CLASS'): ['man', 'MAN', 'kitchen', 'KITCHEN', 'wall', 'WALL'],
    ('PRED_CLASSES', 'PRED_CLASS'): ['parked on', 'PARKED ON'],
}

BOUNDARY_INTS = {
    ('IMG_OBJ', 'IMG_ID'): [0, 1, 2, 19, 20, 21],
    ('IMG_OBJ', 'OBJ_CLASS_ID'): [9, 10, 11],
    ('IMG_OBJ_ATT', 'IMG_ID'): [19, 20, 21],
    ('IMG_REL', 'IMG_ID'): [4, 5, 6],
    ('IMG_REL', 'OBJ1_SAMPLE_ID'): [14, 15, 16],
    ('IMG_REL', 'OBJ2_SAMPLE_ID'): [17, 18, 19],
}

MEASURE_RANGE = {'X': (0, 1000), 'Y': (0, 1000), 'W': (0, 1000), 'H': (0, 1000)}

GROUP_SIZE_TARGETS = [1, 2, 3]
TIE_AT_RANK = 1
DUPLICATE_SHARE = 0.35
PARENT_WITHOUT_CHILDREN = True
CHILD_WITH_NULL_FK = True

NULL_SHARE = {
    ('IMG_OBJ', 'OBJ_CLASS_ID'): 0.05,
    ('IMG_OBJ', 'X'): 0.05,
    ('IMG_OBJ', 'Y'): 0.05,
    ('IMG_OBJ', 'W'): 0.05,
    ('IMG_OBJ', 'H'): 0.05,
}

BASE_TABLE_ROWS = {'ATT_CLASSES': 8, 'OBJ_CLASSES': 8, 'PRED_CLASSES': 8,
                   'IMG_OBJ': 40, 'IMG_OBJ_ATT': 40, 'IMG_REL': 40}
TABLE_ROW_CAP = 2500


def _lookup(entries: list, table: str, column: str):
    for e in entries or []:
        if str(e.get('table', '')).lower() == table.lower() and \
                str(e.get('column', '')).lower() == column.lower():
            return e
    return None


def column_exception(spec: dict, table: str, column: str) -> dict:
    return dict(_lookup(spec.get('per_column_exceptions', []), table, column) or {})


def enum_pool(table: str, column: str) -> list:
    return list(ENUM_LABELS.get(table, {}).get(column, []))


def boundary_strings(table: str, column: str, spec: dict) -> list:
    vals = list(BOUNDARY_STRINGS.get((table, column), []))
    ex = column_exception(spec, table, column)
    if ex and ex.get('pattern') == 'comparison_boundary':
        tg = ex.get('targets') or []
        if isinstance(tg, list):
            vals += [str(x) for x in tg]
    return vals


def boundary_ints(table: str, column: str, spec: dict) -> list:
    vals = list(BOUNDARY_INTS.get((table, column), []))
    ex = column_exception(spec, table, column)
    if ex and ex.get('pattern') == 'comparison_boundary':
        tg = (ex.get('targets') or {})
        if isinstance(tg, dict):
            vals += [int(x) for x in tg.get('values', [])]
    return sorted({int(v) for v in vals})


def measure_range(table: str, column: str):
    return MEASURE_RANGE.get((table, column)) or MEASURE_RANGE.get(column)


def null_share(table: str, column: str, compact_share: float, nullable: bool) -> float:
    if not nullable:
        return 0.0
    if (table, column) in NULL_SHARE:
        return NULL_SHARE[(table, column)]
    return float(compact_share)


def table_rows(schema, table: str, rng) -> int:
    """Exact base size from table_sizes_per_instance (no randomization)."""
    base = BASE_TABLE_ROWS.get(table)
    if base is None:
        lvl = 0
        for i, level in enumerate(schema.table_order):
            if table in level:
                lvl = i
                break
        base = 4 * (lvl + 1)
    return min(TABLE_ROW_CAP, base)


def group_size_plan(n: int, rng) -> list:
    plan: list = []
    for s in GROUP_SIZE_TARGETS:
        if n >= s:
            plan.append(s)
            n -= s
    while n > 0:
        s = min(n, rng.choice([1, 2, 3, 4]))
        plan.append(s)
        n -= s
    return plan


def tie_target() -> int:
    return TIE_AT_RANK


def duplicate_share() -> float:
    return DUPLICATE_SHARE


def fresh_key_int(base: int, seen: set, rng, span=2) -> int:
    for d in (1, 2, -1, -2, 3, -3, 4, -4):
        v = base + d
        if v not in seen:
            return v
    v = abs(base) + span + 1
    while v in seen:
        v += 1
    return v


def perturb_string(base: str, rng, excluded: set = None) -> str:
    """Near-variant of `base`; if `excluded` is given, retry until the result is not in it."""
    excluded = excluded or set()
    if not base:
        return base
    for _ in range(20):
        r = rng.random()
        if r < 0.25:
            v = base + rng.choice(['s', 'x', '1', ' '])
        elif r < 0.5:
            v = rng.choice(['s', 'x', '1', ' ']) + base
        elif r < 0.75 and len(base) > 1:
            v = base[:-1]
        elif len(base) > 1:
            v = base[1:]
        else:
            v = base
        if v not in excluded:
            return v
    k = 0
    v = base
    while v in excluded:
        k += 1
        v = base + str(k)
    return v


def like_pattern(base: str) -> str:
    return re.sub(r'[%_]', '', base)
