"""Specification model: value domains, enums, ranges, NULL shares, table sizes."""
import json
import re

_DEFAULT_ENUMS = {
    ('Albums', 'Type'): ['Studio', 'Live', 'Compilation', 'EP', 'Single'],
    ('Vocals', 'Type'): ['lead', 'shared', 'backing', 'drums'],
    ('Instruments', 'Instrument'): ['drums', 'guitar', 'bass', 'keyboard', 'vocals', 'violin'],
    ('Performance', 'StagePosition'): ['left', 'center', 'right', 'front', 'back'],
}
_DEFAULT_SIZES = {'Songs': 40, 'Albums': 20, 'Band': 15, 'Instruments': 60,
                  'Performance': 50, 'Tracklists': 60, 'Vocals': 40}
_DEFAULT_NULL_SHARE = {
    ('Albums', 'Title'): 0.20, ('Albums', 'Year'): 0.10, ('Albums', 'Label'): 0.10,
    ('Albums', 'Type'): 0.10, ('Band', 'Firstname'): 0.10, ('Band', 'Lastname'): 0.10,
    ('Songs', 'Title'): 0.10, ('Performance', 'StagePosition'): 0.10,
    ('Tracklists', 'SongId'): 0.10, ('Vocals', 'Type'): 0.10, ('Vocals', 'Bandmate'): 0.10,
}
_DEFAULT_BOUNDARY = {
    ('Songs', 'Title'): ['Le Pop', 'le pop', 'Demon Kitty Rag', 'demon kitty rag', 'Badlands',
                         'badlands', 'Flash', 'flash', ' Kitty ', ' kitty '],
    ('Vocals', 'Type'): ['shared', 'SHARED', 'lead', 'LEAD', 'drums', 'DRUMS', 'sared', 'SARED'],
    ('Instruments', 'Instrument'): ['drums', 'DRUMS', 'drms', 'DRMS', 'dru', 'DRU'],
    ('Band', 'Lastname'): ['Heilo', 'heilo', 'Heio', 'heio', 'lo', 'LO', 'BLANK', 'blank'],
    ('Band', 'Firstname'): ['Heil', 'heil'],
    ('Albums', 'Type'): ['Studio', 'studio', '%Studio', '%studio', 'o', 'O', 'STUDIO'],
}
_DEFAULT_RANGES = {
    ('Albums', 'Year'): (1900, 2100),
    ('Songs', 'SongId'): (1, None), ('Albums', 'AId'): (1, None), ('Band', 'Id'): (1, None),
    ('Tracklists', 'Position'): (1, None),
}
_DEFAULT_DUP = {('Songs', 'Title'), ('Vocals', 'SongId'), ('Vocals', 'Type'),
                ('Instruments', 'Instrument'), ('Band', 'Id'), ('Instruments', 'BandmateId')}


class Specification:
    """Plain-data view of the generation specification."""

    def __init__(self, enums=None, sizes=None, null_share=None, boundary=None, ranges=None,
                 dup=None, fresh_share=0.10):
        self.enums = dict(enums or {})
        self.sizes = dict(sizes or {})
        self.null_share = dict(null_share or {})
        self.boundary = dict(boundary or {})
        self.ranges = dict(ranges or {})
        self.dup = set(dup or ())
        self.fresh_share = fresh_share

    def to_dict(self) -> dict:
        return {'enums': {('%s.%s' % k): v for k, v in self.enums.items()},
                'sizes': self.sizes,
                'null_share': {('%s.%s' % k): v for k, v in self.null_share.items()},
                'boundary': {('%s.%s' % k): v for k, v in self.boundary.items()},
                'ranges': {('%s.%s' % k): list(v) for k, v in self.ranges.items()},
                'dup': sorted('%s.%s' % k for k in self.dup),
                'fresh_share': self.fresh_share}


def _key(s: str) -> tuple:
    parts = str(s).split('.')
    return (parts[0], parts[1]) if len(parts) == 2 else (None, None)


def spec_from_dict(d: dict) -> Specification:
    """Rebuild a Specification from its JSON form (worker side)."""
    if not d:
        return default_specification()
    return Specification(
        enums={_key(k): list(v) for k, v in (d.get('enums') or {}).items()},
        sizes=dict(d.get('sizes') or {}),
        null_share={_key(k): float(v) for k, v in (d.get('null_share') or {}).items()},
        boundary={_key(k): list(v) for k, v in (d.get('boundary') or {}).items()},
        ranges={_key(k): tuple(v) for k, v in (d.get('ranges') or {}).items()},
        dup={_key(k) for k in (d.get('dup') or [])},
        fresh_share=float(d.get('fresh_share', 0.10)))


def default_specification() -> Specification:
    """Specification derived from the atomic summary when no file is present."""
    return Specification(enums=_DEFAULT_ENUMS, sizes=_DEFAULT_SIZES, null_share=_DEFAULT_NULL_SHARE,
                         boundary=_DEFAULT_BOUNDARY, ranges=_DEFAULT_RANGES, dup=_DEFAULT_DUP)


def _parse_enum_formula(f: str):
    """'Type IS NULL OR Type IN ('a', 'b')' -> ['a', 'b']."""
    m = re.search(r'\bIN\s*\(([^)]*)\)', f, re.I)
    if not m:
        return None
    return [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]


def _parse_range_formula(f: str):
    """'Year IS NULL OR Year BETWEEN 1900 AND 2100' -> (1900, 2100)."""
    m = re.search(r'BETWEEN\s+(-?\d+)\s+AND\s+(-?\d+)', f, re.I)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r'>\s*(-?\d+)', f)
    if m:
        return (int(m.group(1)) + 1, None)
    return None


def load_specification(path: str) -> Specification:
    """Load specification.json; fall back to the atomic-summary defaults."""
    spec = default_specification()
    if not path or not path.endswith('.json'):
        return spec
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return spec
    if not isinstance(d, dict):
        return spec
    sizes = d.get('table_sizes_per_instance') or {}
    for t, n in sizes.items():
        try:
            spec.sizes[t] = int(n)
        except (TypeError, ValueError):
            pass
    for r in d.get('semantic_rules_and_formulas') or []:
        t, c, f = r.get('table'), r.get('column'), str(r.get('formula') or '')
        if not t or not c:
            continue
        vals = _parse_enum_formula(f)
        if vals:
            spec.enums[(t, c)] = vals
            continue
        rng = _parse_range_formula(f)
        if rng:
            spec.ranges[(t, c)] = rng
    for e in d.get('per_column_exceptions') or []:
        col = str(e.get('column') or '')
        if '.' not in col:
            continue
        t, c = col.split('.', 1)
        pat = e.get('pattern')
        tg = e.get('targets') or {}
        if pat == 'comparison_boundary' and tg.get('values'):
            spec.boundary[(t, c)] = [str(v) for v in tg['values']]
        elif pat == 'null_rows':
            share = str(tg.get('null_share') or '')
            m = re.search(r'(\d+)\s*-\s*(\d+)\s*%', share)
            if m:
                spec.null_share[(t, c)] = (int(m.group(1)) + int(m.group(2))) / 200.0
            else:
                try:
                    spec.null_share[(t, c)] = float(share)
                except (TypeError, ValueError):
                    if 'small' in share.lower():
                        spec.null_share[(t, c)] = 0.05
        elif pat == 'duplicates_for_distinct':
            if tg.get('applicable', True) is False:
                spec.dup.discard((t, c))
            else:
                spec.dup.add((t, c))
    for col in d.get('null_targets') or []:
        if '.' in col:
            t, c = col.split('.', 1)
            spec.null_share.setdefault((t, c), 0.10)
    return spec
