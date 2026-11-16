"""Specification handling: value domains, ranges, enums, NULL shares, table sizes."""
import re

from .values import is_time_string, time_to_sec as _time_to_sec, sec_to_time as _sec_to_time

_TIME_RE = re.compile(r'^\d{1,3}:\d{2}\.\d{2}$')
_YEAR_RE = re.compile(r'^(19|20)\d{2}$')


def _is_time(v) -> bool:
    return is_time_string(v)


def _is_year(v) -> bool:
    return isinstance(v, str) and bool(_YEAR_RE.match(v.strip()))


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _col_kind(column, values: list) -> str:
    """Classify a column into a value domain used by the samplers."""
    t = (column.type_str or '').lower()
    vals = [v for v in values if v is not None]
    if column.pk_pos > 0:
        return 'pk'
    if 'int' in t:
        return 'int'
    if any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number')):
        return 'real'
    if vals and all(_is_time(v) for v in vals):
        return 'time'
    if vals and all(_is_year(v) for v in vals):
        return 'year'
    return 'text'


def spec_from_compact(schema) -> dict:
    """Derive the specification data from the compact database (fallback path)."""
    spec = {'tables': {}, 'null_share': {}, 'enums': {}, 'ranges': {}, 'time_ladders': {},
            'table_sizes': {}, 'unique_tuples': [], 'literal_pool': {}, 'year_text': set()}
    for t, tm in schema.tables.items():
        cols = {}
        for cm in tm.columns:
            vals = schema.original_values.get((t, cm.name), [])
            kind = _col_kind(cm, vals)
            cols[cm.name] = {'kind': kind, 'notnull': cm.notnull or cm.pk_pos > 0,
                             'pk': cm.pk_pos > 0, 'unique': cm.unique}
            nn = [v for v in vals if v is not None]
            share = 0.0 if not vals else (len(vals) - len(nn)) / float(len(vals))
            spec['null_share']['%s.%s' % (t, cm.name)] = share
            if kind == 'int' and nn:
                spec['ranges']['%s.%s' % (t, cm.name)] = [min(nn), max(nn)]
            if kind == 'real' and nn:
                spec['ranges']['%s.%s' % (t, cm.name)] = [min(nn), max(nn)]
            if kind == 'year':
                spec['year_text'].add('%s.%s' % (t, cm.name))
                spec['ranges'].setdefault('%s.%s' % (t, cm.name), [1900, 2030])
            if kind == 'text' and nn:
                distinct = sorted({str(v) for v in nn})
                if len(distinct) <= 12:
                    spec['enums']['%s.%s' % (t, cm.name)] = distinct
        spec['tables'][t] = cols
        spec['table_sizes'][t] = max(1, schema.original_sizes.get(t, 0))
    for t, tm in schema.tables.items():
        ladder = [c.name for c in tm.columns if re.match(r'(?i)^meter_\d+$', c.name)]
        if ladder:
            ladder.sort(key=lambda n: int(re.findall(r'\d+', n)[0]))
            tail = [c.name for c in tm.columns if c.name.lower() == 'time']
            spec['time_ladders'][t] = ladder + tail
    for t, tm in schema.tables.items():
        if len(tm.primary_key) > 1:
            spec['unique_tuples'].append([t, list(tm.primary_key)])
    return spec


def load_specification(js: dict, schema) -> dict:
    """Merge a specification.json into the compact-derived defaults."""
    spec = spec_from_compact(schema)
    if not isinstance(js, dict):
        return spec
    for t, size in (js.get('table_sizes_per_instance') or {}).items():
        if t in spec['tables']:
            spec['table_sizes'][t] = int(size)
    for ex in js.get('per_column_exceptions') or []:
        col = ex.get('column')
        if not col or '.' not in col:
            continue
        t, c = col.split('.', 1)
        if t not in spec['tables'] or c not in spec['tables'][t]:
            continue
        pat = (ex.get('pattern') or '').lower()
        tgt = (ex.get('targets') or '').lower()
        if 'comparison_boundary' in pat:
            m = re.search(r'boundary at (\d+)', tgt)
            if m:
                spec.setdefault('boundaries', {})[col] = int(m.group(1))
        if 'literal_pool' in pat:
            nums = [int(x) for x in re.findall(r'\b(\d{4})\b', tgt)]
            if nums:
                spec.setdefault('literal_pool', {})[col] = nums
        if 'ties_for_order_limit' in pat and 'tie at rank 1' in tgt:
            spec.setdefault('tie_rank1', set()).add(col)
        if 'duplicates_for_distinct' in pat:
            spec.setdefault('dup_share', {})[col] = (0.2, 0.5)
        if 'group_sizes' in pat:
            spec.setdefault('group_sizes', set()).add(col)
        if 'unmatched_join_rows' in pat:
            spec.setdefault('unmatched', set()).add(col)
        if 'null_rows' in pat:
            spec.setdefault('null_rows', set()).add(col)
    for rule in js.get('semantic_rules_and_formulas') or []:
        t, c = rule.get('table'), rule.get('column')
        f = (rule.get('formula') or '')
        if not t or not c:
            continue
        col = '%s.%s' % (t, c)
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m:
            vals = re.findall(r"'([^']*)'", m.group(1))
            if vals:
                spec['enums'][col] = vals
        m = re.search(r"BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)", f, re.I)
        if m:
            spec['ranges'][col] = [int(m.group(1)), int(m.group(2))]
            if 'CAST' in f.upper() and 'YEAR' in c.upper():
                spec['year_text'].add(col)
        m = re.search(r">\s*'?(\d+(?:\.\d+)?)'?", f)
        if m and 'IS NULL OR' in f.upper():
            spec.setdefault('min_positive', {})[col] = float(m.group(1))
    for nt in js.get('null_targets') or []:
        if '.' in nt:
            t, c = nt.split('.', 1)
            tm = schema.tables.get(t)
            if tm is not None and c in tm.primary_key:
                continue
        spec.setdefault('null_rows', set()).add(nt)
    return spec


def time_ladder_ok(spec: dict, table: str, row: dict) -> bool:
    """Hard monotone-increasing check for the meter_100..700/Time ladder (in-memory, no SQL)."""
    ladder = spec.get('time_ladders', {}).get(table)
    if not ladder:
        return True
    prev = None
    for c in ladder:
        v = row.get(c)
        if v is None:
            continue
        if not is_time_string(v):
            return False
        x = _time_to_sec(v)
        if prev is not None and x < prev:
            return False
        prev = x
    return True


def sec_to_time(x: float) -> str:
    """Delegate to values.sec_to_time (never self-recursive)."""
    return _sec_to_time(x)


def time_to_sec(v: str) -> float:
    """Delegate to values.time_to_sec (never self-recursive)."""
    return _time_to_sec(v)
