"""Specification-driven samplers: value domains, ranges, dupes, ties, NULLs by construction."""
import datetime as dt
import random
import re
import string
import zlib

CHARSET = string.ascii_letters + string.digits + ' '
_TS_FMT = '%Y-%m-%d %H:%M:%S.0'
_TS_LO = dt.datetime(2005, 1, 1)
_TS_HI = dt.datetime(2006, 2, 15)


def _is_int_type(t: str) -> bool:
    return 'int' in (t or '').lower()


def _is_real_type(t: str) -> bool:
    return any(k in (t or '').lower() for k in ('real', 'float', 'double', 'decimal', 'numeric'))


def _is_datetime_type(t: str) -> bool:
    return any(k in (t or '').lower() for k in ('datetime', 'timestamp', 'date', 'time'))


def _is_blob_type(t: str) -> bool:
    return 'blob' in (t or '').lower()


def parse_num(v):
    """Parse a numeric literal from a pool string; None if not numeric."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_ts(v):
    """Parse a compact-db timestamp string to datetime (best effort)."""
    s = str(v).strip()
    for f in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def stable_hash(*parts) -> int:
    """Deterministic hash independent of PYTHONHASHSEED (crc32 of the repr)."""
    return zlib.crc32(repr(parts).encode('utf-8')) & 0xFFFFFFFF


class ValuePool:
    """Typed value pool for one column: observed values + routed literals + exceptions + perturbations."""

    def __init__(self, col_type, observed, literals, exceptions, rng):
        self.type = col_type or ''
        self.rng = rng
        self.int_v = [int(x) for x in observed if _is_int_type(col_type) and _try_int(x) is not None]
        self.real_v = [float(x) for x in observed if _is_real_type(col_type) and parse_num(x) is not None]
        self.text_v = [str(x) for x in observed if x is not None and not _is_int_type(col_type)
                       and not _is_real_type(col_type) and not _is_datetime_type(col_type)]
        self.ts_v = [str(x) for x in observed if _is_datetime_type(col_type) and x is not None]
        self.exc = list(exceptions or [])
        self.lit = list(literals or [])
        self.num_pert = []
        if _is_int_type(col_type):
            for v in self.int_v + [int(l) for l in self.lit if _try_int(l) is not None]:
                self.num_pert += [v - 2, v - 1, v + 1, v + 2]
        if _is_real_type(col_type):
            for v in self.real_v + [parse_num(l) for l in self.lit if parse_num(l) is not None]:
                self.num_pert += [round(v - 0.01, 2), round(v + 0.01, 2),
                                  round(v - 0.02, 2), round(v + 0.02, 2)]
        self.str_pert = []
        for v in self.text_v + [str(l) for l in self.lit if parse_num(l) is None]:
            if v:
                self.str_pert += [v[:-1], v[1:], v + 'x', 'x' + v]
            if '%' in v:
                self.str_pert.append(v.replace('%', ''))
        self.ts_pert = []
        for v in self.ts_v:
            d = parse_ts(v)
            if d is not None:
                self.ts_pert += [(d - dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S.0'),
                                 (d + dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S.0')]

    def _cat(self) -> list:
        if _is_int_type(self.type):
            base = self.int_v or [1]
            return base + [int(l) for l in self.lit if _try_int(l) is not None] + self.num_pert + self.exc
        if _is_real_type(self.type):
            base = self.real_v or [1.0]
            return base + [parse_num(l) for l in self.lit if parse_num(l) is not None] + self.num_pert + self.exc
        if _is_datetime_type(self.type):
            return self.ts_v + self.ts_pert + [str(x) for x in self.exc]
        return self.text_v + [str(x) for x in self.lit] + self.str_pert + [str(x) for x in self.exc]

    def draw(self, in_range):
        """Draw one non-NULL value; in_range is a callable filter on the raw value (or None)."""
        r = self.rng
        if r.random() < 0.35:
            try:
                v = _fresh(self.type, r)
            except Exception:
                v = None
        else:
            v = None
        if v is None:
            cand = self._cat()
            cand = [c for c in cand if _ok_type(self.type, c)]
            if cand and in_range is not None:
                filt = [c for c in cand if in_range(c)]
                cand = filt or cand
            v = r.choice(cand) if cand else _fresh(self.type, r)
        return v


def _ok_type(t, v) -> bool:
    if v is None:
        return False
    if _is_int_type(t):
        return isinstance(v, int) or _try_int(v) is not None
    if _is_real_type(t):
        return parse_num(v) is not None
    return True


def _try_int(x):
    try:
        if isinstance(x, bool):
            return None
        f = float(x)
        if f.is_integer():
            return int(f)
        return None
    except (TypeError, ValueError):
        return None


def _fresh(t, r):
    """Fresh value by declared type: bounded numbers, short strings, timestamps."""
    if _is_int_type(t):
        return r.randint(1, 500)
    if _is_real_type(t):
        return round(r.uniform(0.0, 30.0), 2)
    if _is_datetime_type(t):
        d = _TS_LO + dt.timedelta(seconds=r.randint(0, int((_TS_HI - _TS_LO).total_seconds())))
        s = d.strftime(_TS_FMT)
        return re.sub(r'(^|[- :])0(\d)', r'\1\2', s)
    if _is_blob_type(t):
        return None
    n = r.randint(3, 12)
    return ''.join(r.choice(CHARSET) for _ in range(n))
