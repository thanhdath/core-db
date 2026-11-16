"""Per-type value generators with enum/range/boundary pools from the specification."""
import datetime as dt
import random
import re
import string

CHARSET = string.ascii_letters + ' ' + string.digits + '()'
_SPEC = {}


def set_spec(spec: dict) -> None:
    """Install the compiled specification for the samplers of this process."""
    _SPEC.clear()
    _SPEC.update(spec or {})


def spec() -> dict:
    return _SPEC


def _rng_variant_text(v: str, rng) -> str:
    """One near-variant: case flip, one-char typo, prefix/suffix/dropped char, LIKE without '%'."""
    if not isinstance(v, str) or not v:
        return v
    u = rng.random()
    if u < 0.2:
        return v.upper() if rng.random() < 0.5 else v.lower()
    if u < 0.45 and len(v) >= 2:
        i = rng.randrange(len(v))
        return v[:i] + rng.choice(CHARSET) + v[i + 1:]
    if u < 0.6:
        return v[:-1]
    if u < 0.72:
        return v[1:]
    if u < 0.84:
        return v + ''.join(rng.choice(CHARSET) for _ in range(rng.randint(1, 3)))
    if u < 0.92:
        return ''.join(rng.choice(CHARSET) for _ in range(rng.randint(1, 3))) + v
    if '%' in v:
        return v.replace('%', '')
    return v


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_int(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        return float(x) == int(float(x))
    except (TypeError, ValueError):
        return False


_INT_RANGE = (-1000, 1000)
_REAL_RANGE = (-100.0, 100.0)


def _parse_date(s: str):
    s = str(s).strip()
    for t in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%Y%m%d', '%Y-%m'):
        try:
            return t, dt.datetime.strptime(s, t)
        except ValueError:
            pass
    return None, None


def sample_scalar(table: str, column: str, type_str: str, original_values: list, pool_literals: list,
                  rng, *, n_rows: int = 1) -> list:
    """Draw n_rows independent values for a non-FK, non-derived column."""
    key = '%s.%s' % (table, column)
    sp = spec()
    enums = sp.get('enums', {}).get(key)
    bounds = sp.get('boundary_values', {}).get(key, [])
    ranges = sp.get('ranges', {}).get(key)
    nonneg = key in sp.get('nonneg_columns', [])
    orig = [v for v in original_values if v is not None]
    lits = list(pool_literals or [])
    out = []
    for _ in range(n_rows):
        u = rng.random()
        if enums and u < 0.90:
            v = rng.choice(enums)
            if rng.random() < 0.03:
                v = _rng_variant_text(v, rng)
            out.append(v)
            continue
        if ranges and u < 0.85:
            lo, hi = ranges
            if rng.random() < 0.05:
                v = rng.choice([lo, hi])
            elif hi >= lo and float(hi) == int(hi) and float(lo) == int(lo):
                v = rng.randint(int(lo), int(hi))
            else:
                v = round(rng.uniform(float(lo), float(hi)), 1)
            out.append(v)
            continue
        if bounds and u < 0.06:
            v = rng.choice(bounds)
            if rng.random() < 0.5 and isinstance(v, str):
                v = _rng_variant_text(v, rng)
            out.append(v)
            continue
        v = _draw_typed(type_str, orig, lits, rng, nonneg)
        if bounds and rng.random() < 0.05:
            cand = rng.choice(bounds)
            if _compatible(type_str, cand):
                v = cand
        if rng.random() < sp.get('fresh_values_share', 0.15) and isinstance(v, str) and orig:
            v = _rng_variant_text(rng.choice(orig) if orig else v, rng)
        out.append(v)
    return out


def _compatible(type_str: str, v) -> bool:
    t = (type_str or '').lower()
    if isinstance(v, str):
        return any(k in t for k in ('char', 'text', 'blob', 'date', '')) or t == ''
    return True


def _draw_typed(type_str: str, orig: list, lits: list, rng, nonneg: bool = False):
    """Declared-type sampler over observed values / pool literals / ranges (sunny/rainy share)."""
    t = (type_str or '').lower().strip()
    p_reuse = 0.25
    cand = orig + lits
    if cand and rng.random() < p_reuse:
        v = rng.choice(cand)
        if isinstance(v, str) and rng.random() < 0.1:
            v = _rng_variant_text(v, rng)
        return v
    if 'date' in t or 'timestamp' in t:
        lo, hi = dt.date(1930, 1, 1), dt.date(2015, 12, 31)
        if orig and rng.random() < 0.5:
            parsed = [_parse_date(str(o))[1] for o in orig]
            parsed = [d for d in parsed if d is not None]
            if parsed and rng.random() < 0.5:
                return rng.choice(orig)
        d = lo + dt.timedelta(days=rng.randint(0, (hi - lo).days))
        if rng.random() < 0.05:
            d = rng.choice([lo, hi])
        return d.strftime('%Y-%m-%d')
    if 'time' in t and 'stamp' not in t:
        return '%02d:%02d:%02d' % (rng.randrange(24), rng.randrange(60), rng.randrange(60))
    if any(k in t for k in ('int', 'year', 'bit', 'bool')):
        lo, hi = (0, 200) if nonneg else _INT_RANGE
        if 'year' in t:
            lo, hi = 1930, 2015
        if rng.random() < 0.05:
            return rng.choice([lo, hi])
        return rng.randint(lo, hi)
    if any(k in t for k in ('float', 'double', 'decimal', 'numeric', 'number', 'real')):
        lo, hi = (0.0, 100.0) if nonneg else _REAL_RANGE
        if rng.random() < 0.05:
            return rng.choice([lo, hi])
        return round(rng.uniform(lo, hi), 1)
    if orig and rng.random() < 0.6:
        base = rng.choice([str(x) for x in orig])
        return _rng_variant_text(base, rng) if rng.random() < 0.05 else base
    if lits and rng.random() < 0.5:
        return str(rng.choice(lits))
    n = rng.randint(3, 12)
    return ''.join(rng.choice(CHARSET) for _ in range(n)).strip() or 'x'


def make_id(table: str, column: str, rng, existing: set, prefix: str = '') -> str:
    """A short identifier not colliding with `existing` (stringified set)."""
    for _ in range(1000):
        n = rng.randint(3, 8)
        s = prefix + ''.join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(n))
        if s not in existing:
            return s
    s = prefix + str(rng.randint(10 ** 8, 10 ** 10))
    return s
