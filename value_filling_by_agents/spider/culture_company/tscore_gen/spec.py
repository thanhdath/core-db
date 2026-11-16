"""Specification model: value domains, ranges, enums, NULL shares, join/group/order targets."""
import re

DEFAULT_SPEC = {
    'table_sizes': {'book_club': 12, 'movie': 10, 'culture_company': 6},
    'columns': {
        'book_club.Year': {'kind': 'int_range', 'min': 1988, 'max': 1990,
                           'boundary': [1988, 1989, 1990]},
        'book_club.Category': {'kind': 'enum', 'values': ['Gay M/SF', 'Lesb. M/SF', 'Gay SF/F']},
        'book_club.Result': {'kind': 'enum', 'values': ['Won [A ]', 'Nom', 'Won', 'Won [B ]']},
        'book_club.Publisher': {'kind': 'text', 'group_sizes': [1, 2, 3],
                                'tie_at_rank': [1], 'tie_on': 'count'},
        'book_club.Author_or_Editor': {'kind': 'text'},
        'book_club.Book_Title': {'kind': 'text'},
        'movie.Year': {'kind': 'int_range', 'min': 1, 'max': 2001,
                       'boundary': [-1, 0, 1, 1999, 2000, 2001, 2002]},
        'movie.Budget_million': {'kind': 'real_range', 'min': 0.1, 'max': 100.0,
                                 'boundary': [-0.1, 0.0, 0.1]},
        'movie.Gross_worldwide': {'kind': 'int_range', 'min': 0, 'max': 200000000,
                                  'tie_at_rank': [1]},
        'movie.Title': {'kind': 'text', 'tie_at_rank': [1]},
        'movie.Director': {'kind': 'text'},
        'culture_company.Type': {'kind': 'enum', 'values': ['Corporate', 'Joint Venture', 'Subsidiary']},
        'culture_company.Incorporated_in': {'kind': 'enum', 'values': ['China', 'Hong Kong']},
        'culture_company.Group_Equity_Shareholding': {'kind': 'real_range', 'min': 0.0, 'max': 100.0},
        'culture_company.Company_name': {'kind': 'text', 'duplicate_share': (0.2, 0.5)},
    },
    'joins': [
        {'left': 'book_club.book_club_id', 'right': 'movie.movie_id',
         'parent_rows_without_children': True, 'child_rows_with_null_fk': False},
    ],
    'group_sizes': {
        'book_club.book_club_id': [1, 2, 3],
        'book_club.Publisher': [1, 2, 3],
    },
    'aggregate_boundary': {
        'book_club.Category': {'aggregate': 'count', 'values': [1, 2, 3]},
    },
    'order_ties': {
        'book_club.Publisher': {'direction': 'desc', 'tie_at_rank': [1], 'tie_on': 'count'},
        'movie.Gross_worldwide': {'direction': 'desc', 'tie_at_rank': [1]},
        'movie.Title': {'direction': 'desc', 'tie_at_rank': [1]},
    },
    'null_columns': [
        'book_club.Year', 'book_club.Author_or_Editor', 'book_club.Book_Title',
        'book_club.Publisher', 'book_club.Category', 'book_club.Result',
        'movie.Title', 'movie.Year', 'movie.Director', 'movie.Budget_million',
        'movie.Gross_worldwide', 'culture_company.Type', 'culture_company.Incorporated_in',
        'culture_company.Group_Equity_Shareholding', 'culture_company.book_club_id',
        'culture_company.movie_id',
    ],
}


def _key(t: str, c: str) -> str:
    return '%s.%s' % (t, c)


def load_specification(raw: dict) -> dict:
    """Normalise a specification.json dict into the internal form (tolerant of missing parts)."""
    spec = {'table_sizes': {}, 'columns': {}, 'joins': [], 'group_sizes': {},
            'aggregate_boundary': {}, 'order_ties': {}, 'null_columns': []}
    if not isinstance(raw, dict):
        return spec
    spec['table_sizes'] = dict(raw.get('table_sizes_per_instance') or {})
    spec['null_columns'] = list(raw.get('null_targets') or [])
    for ex in raw.get('per_column_exceptions') or []:
        t, c = ex.get('table'), ex.get('column')
        if not t or not c:
            continue
        k = _key(t, c)
        pat = ex.get('pattern')
        tg = ex.get('targets') or {}
        col = spec['columns'].setdefault(k, {})
        if pat == 'comparison_boundary':
            vals = [v for v in (tg.get('values') or []) if isinstance(v, (int, float))]
            if vals:
                col['boundary'] = vals
                col.setdefault('kind', 'real_range' if any(isinstance(v, float) for v in vals) else 'int_range')
                col['min'] = min(vals)
                col['max'] = max(vals)
        elif pat == 'group_sizes':
            gs = tg.get('group_sizes')
            if isinstance(gs, str):
                nums = [int(x) for x in re.findall(r'\d+', gs)]
                if nums:
                    col['group_sizes'] = nums
                    spec['group_sizes'][k] = nums
        elif pat == 'ties_for_order_limit':
            col['tie_at_rank'] = list(tg.get('tie_at_rank') or [1])
            spec['order_ties'][k] = {'direction': (tg.get('direction') or 'desc').lower(),
                                     'tie_at_rank': list(tg.get('tie_at_rank') or [1]),
                                     'tie_on': (tg.get('tie_on') or ['value'])[0]}
        elif pat == 'aggregate_boundary':
            spec['aggregate_boundary'][k] = {'aggregate': (tg.get('aggregate') or ['COUNT(*)'])[0],
                                             'values': list(tg.get('values') or [])}
        elif pat == 'duplicates_for_distinct':
            share = tg.get('duplicate_share') or '20-50 %'
            nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(share))]
            if len(nums) >= 2:
                col['duplicate_share'] = (nums[0] / 100.0, nums[1] / 100.0)
            else:
                col['duplicate_share'] = (0.2, 0.5)
        elif pat == 'unmatched_join_rows':
            spec['joins'].append({'left': k, 'right': (tg.get('joins_with') or [None])[0],
                                  'parent_rows_without_children': bool(tg.get('parent_rows_without_children')),
                                  'child_rows_with_null_fk': bool(tg.get('child_rows_with_null_fk'))})
    for r in raw.get('semantic_rules_and_formulas') or []:
        t, c = r.get('table'), r.get('column')
        f = r.get('formula') or ''
        if not t or not c:
            continue
        k = _key(t, c)
        col = spec['columns'].setdefault(k, {})
        m = re.search(r"IN\s*\(([^)]*)\)", f, re.I)
        if m:
            vals = [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]
            if vals:
                col['kind'] = 'enum'
                col['values'] = vals
            continue
        m = re.search(r"BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", f, re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            col['kind'] = 'real_range' if ('.' in m.group(1) or '.' in m.group(2)) else 'int_range'
            col['min'], col['max'] = lo, hi
            continue
        m = re.search(r"([<>]=?)\s*(-?\d+(?:\.\d+)?)", f)
        if m:
            op, v = m.group(1), float(m.group(2))
            col.setdefault('kind', 'real_range' if '.' in m.group(2) else 'int_range')
            if op in ('>', '>='):
                col['min'] = v + (0.1 if col['kind'] == 'real_range' else 1) if op == '>' else v
            else:
                col['max'] = v - (0.1 if col['kind'] == 'real_range' else 1) if op == '<' else v
    return spec


def spec_from_schema(schema) -> dict:
    """Fallback: derive a minimal specification from the compact database's observed values."""
    spec = {'table_sizes': {}, 'columns': {}, 'joins': [], 'group_sizes': {},
            'aggregate_boundary': {}, 'order_ties': {}, 'null_columns': []}
    for t, tm in schema.tables.items():
        spec['table_sizes'][t] = max(1, int(schema.original_sizes.get(t, 0)))
        for cm in tm.columns:
            k = _key(t, cm.name)
            vals = [v for v in schema.original_values.get(k, []) if v is not None]
            if not vals:
                continue
            if not cm.notnull and cm.pk_pos == 0:
                spec['null_columns'].append(k)
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                spec['columns'][k] = {'kind': 'int_range' if all(isinstance(v, int) for v in vals) else 'real_range',
                                      'min': min(vals), 'max': max(vals)}
            elif len(set(vals)) <= 8:
                spec['columns'][k] = {'kind': 'enum', 'values': sorted({str(v) for v in vals})}
            else:
                spec['columns'][k] = {'kind': 'text'}
    return spec
