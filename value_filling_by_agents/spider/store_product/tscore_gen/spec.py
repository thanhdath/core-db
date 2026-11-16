"""Specification loading: turns the generation-specification JSON into a plain dict the samplers consume."""
import copy

_DEFAULT = {
    'sizes': {},
    'null_targets': [],
    'null_share': {},
    'group_sizes': {},
    'dup_share': {},
    'ties': {},
    'boundaries': {},
    'enums': {},
    'ranges': {},
    'unmatched': {},
    'different': {},
    'fresh_share': 0.3,
}


def _norm_table(t: str) -> str:
    return str(t).strip().strip('"`').lower()


def _norm_col(c: str) -> str:
    return str(c).strip().strip('"`').split('.')[-1].lower()


def _split_key(k: str):
    """'table.column' -> (table, column); bare column -> (None, column)."""
    parts = str(k).split('.')
    if len(parts) >= 2:
        return _norm_table(parts[-2]), _norm_col(parts[-1])
    return None, _norm_col(parts[0])


def _put(d: dict, t, c, v) -> None:
    d.setdefault(t, {})[c] = v


def load_specification(raw: dict) -> dict:
    """Translate the pipeline's specification JSON into the sampler dict."""
    spec = copy.deepcopy(_DEFAULT)
    if not isinstance(raw, dict):
        return spec
    for t, n in (raw.get('table_sizes_per_instance') or {}).items():
        try:
            spec['sizes'][_norm_table(t)] = int(n)
        except (TypeError, ValueError):
            pass
    for k in raw.get('null_targets') or []:
        t, c = _split_key(k)
        if t is not None:
            spec['null_targets'].append((t, c))
    for r in raw.get('semantic_rules_and_formulas') or []:
        t, c = _norm_table(r.get('table', '')), _norm_col(r.get('column', ''))
        f = str(r.get('formula', ''))
        if not t or not c:
            continue
        if ' IN (' in f.upper():
            body = f[f.index('(') + 1:f.rindex(')')]
            vals = [x.strip().strip("'\"") for x in body.split(',') if x.strip()]
            if vals:
                _put(spec['enums'], t, c, vals)
        elif '>' in f:
            try:
                lo = float(f.split('>')[-1].strip())
            except ValueError:
                continue
            _put(spec['ranges'], t, c, (lo, None))
    for ex in raw.get('per_column_exceptions') or []:
        pat = ex.get('pattern')
        tg = ex.get('targets') or {}
        for k in ex.get('columns') or []:
            t, c = _split_key(k)
            if t is None:
                continue
            if pat == 'group_sizes':
                _put(spec['group_sizes'], t, c, [1, 2, 3])
            elif pat == 'duplicates_for_distinct':
                share = str(tg.get('duplicate_share', '20-50 %')).replace('%', '').strip()
                try:
                    lo, hi = [float(x) for x in share.split('-')]
                except ValueError:
                    lo, hi = 20.0, 50.0
                _put(spec['dup_share'], t, c, (lo / 100.0, hi / 100.0))
            elif pat == 'ties_for_order_limit':
                ranks = [int(x) for x in (tg.get('tie_at_rank') or [1]) if int(x) <= 2500]
                direction = str(tg.get('direction', 'ASC'))
                _put(spec['ties'], t, c, {'ranks': ranks, 'direction': direction})
            elif pat == 'comparison_boundary':
                vals = tg.get('values') or []
                if vals:
                    _put(spec['boundaries'], t, c, list(vals))
            elif pat == 'rows_with_different_values':
                _put(spec['different'], t, c, True)
            elif pat == 'unmatched_join_rows':
                _put(spec['unmatched'], t, c, True)
    g = raw.get('generic_sampling_rules') or {}
    if 'fresh_values' in g:
        try:
            spec['fresh_share'] = float(str(g['fresh_values']).split('%')[0].strip('~ ')) / 100.0
        except ValueError:
            pass
    return spec


def default_specification() -> dict:
    """Built-in default used when no specification.json is present."""
    return copy.deepcopy(_DEFAULT)
