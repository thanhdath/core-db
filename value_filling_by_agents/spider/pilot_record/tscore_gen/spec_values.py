"""Sampling value pools for a spec (specification.json + compact values + pool literals)."""
import datetime as dt
import random

from . import spec as specmod


def _norm(spec: dict, table: str, column: str) -> dict:
    return specmod.column_spec(spec, table, column)


def _int_pool(spec: dict, table: str, column: str, observed: list, rng) -> list:
    """Integer pool for an int_range / int_boundary column."""
    rng_ = specmod.int_range(spec, table, column)
    vals = set()
    for v in observed:
        if isinstance(v, bool):
            continue
        try:
            vals.add(int(v))
        except (TypeError, ValueError):
            pass
    for b in specmod.int_boundaries(spec, table, column):
        for d in (-1, 0, 1):
            vals.add(b + d)
    if rng_ is not None:
        lo, hi = rng_
        vals.add(lo)
        vals.add(hi)
        vals.add(lo + 1)
        vals.add(hi - 1)
        vals.add((lo + hi) // 2)
    return sorted(vals)


def _enum_pool(spec: dict, table: str, column: str, observed: list) -> list:
    """Enum pool: spec values + observed values + near variants."""
    vals = []
    for v in specmod.enum_values(spec, table, column):
        vals.append(v)
    for v in observed:
        if isinstance(v, str) and v not in vals:
            vals.append(v)
    for v in specmod.near_variants(spec, table, column):
        if v not in vals:
            vals.append(v)
    return vals


def _text_pool(spec: dict, table: str, column: str, observed: list, rng: random.Random) -> list:
    """Text pool for a distinct_duplicates column: observed values + fresh variants."""
    vals = []
    for v in observed:
        if isinstance(v, str) and v not in vals:
            vals.append(v)
    for v in list(vals):
        for cand in (v.lower(), v.upper(), v + ' ', v[:-1] if len(v) > 1 else v):
            if cand and cand not in vals:
                vals.append(cand)
    return vals


def _date_pool(spec: dict, table: str, column: str, observed: list, rng) -> list:
    """Date pool: observed dates + one day before/after each literal."""
    fmt = specmod.date_format(spec, table, column)
    vals = []
    for v in observed:
        if isinstance(v, str) and v not in vals:
            vals.append(v)
    for v in list(vals):
        try:
            d = dt.datetime.strptime(v, fmt)
        except (TypeError, ValueError):
            continue
        for delta in (-1, 1):
            s = (d + dt.timedelta(days=delta)).strftime(fmt)
            if s not in vals:
                vals.append(s)
    return vals


def build_pool(spec: dict, table: str, column: str, observed: list, literal_pool: list,
               rng: random.Random) -> dict:
    """Build a value pool for one column: {'kind': ..., 'values': [...]}."""
    ex = _norm(spec, table, column)
    pat = ex.get('pattern')
    obs = [v for v in observed if v is not None]
    lit = [v for v in literal_pool if v is not None]
    if pat == 'int_range' or pat == 'int_boundary':
        return {'kind': 'int', 'values': _int_pool(spec, table, column, obs + lit, rng)}
    if pat == 'text_enum':
        return {'kind': 'text', 'values': _enum_pool(spec, table, column, obs + lit)}
    if pat == 'text_date':
        return {'kind': 'date', 'values': _date_pool(spec, table, column, obs + lit, rng)}
    if pat == 'distinct_duplicates':
        return {'kind': 'text', 'values': _text_pool(spec, table, column, obs + lit, rng)}
    if pat == 'primary_key' or pat == 'int_primary_key':
        return {'kind': 'int', 'values': []}
    if pat == 'int_fk':
        return {'kind': 'fk', 'values': []}
    return {'kind': 'text', 'values': [str(v) for v in obs + lit]}
