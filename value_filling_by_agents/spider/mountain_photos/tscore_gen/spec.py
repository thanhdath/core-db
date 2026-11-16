"""Specification model: value domains, ranges, enumerations, NULL targets, table sizes."""

_EMBEDDED = {
    'table_sizes': {'camera_lens': 11, 'mountain': 23, 'photos': 10},
    'null_targets': ['photos.camera_lens_id', 'photos.mountain_id'],
    'domains': {
        'camera_lens.brand': ['Olympus', 'Panasonic', 'Schneider Kreuznach', 'Sigma'],
        'camera_lens.name': ['Olympus 15mm f/8.0 Body Cap',
                             'Olympus M.Zuiko Digital ED 45mm f/1.8',
                             'Olympus M.Zuiko Digital ED 75mm f/1.8',
                             'Panasonic Leica DG Summilux 25mm f /1.4 Asph.',
                             'Panasonic Leica DG Nocticron 42.5mm f /1.2',
                             'Panasonic Lumix G 150mm f /2.8',
                             'Schneider Kreuznach Super Angulon 14mm f /2.0',
                             'Schneider Kreuznach Xenon 30mm f /1.4'],
        'mountain.name': ['Abune Yosef / Guliba Amba', 'Ioll / Yoll', 'Bada', 'Kaka / Kecha / Chiqe',
                          'Jbel Toubkal', 'Muhavura', 'Hey / Hay', 'Guna'],
        'mountain.Range': ['Lasta Massif', 'Kollo Massif', 'Arsi Mountains', 'Toubkal Atlas',
                           'Virunga Mountains', 'Semien Mountains', 'Guna Massif', 'Choqa Mountains'],
        'mountain.Country': ['Ethiopia', 'Morocco', 'Rwanda Uganda', 'Cameroon', 'Kenya'],
        'photos.color': ['RBG', 'Black/White'],
        'photos.name': ['monkey', 'rabbits', 'deers', 'grass', 'cloud', 'sunset', 'river', 'wolfs'],
    },
    'ranges': {
        'mountain.Height': (4120.0, 4260.0),
        'mountain.Prominence': (350.0, 3755.0),
        'camera_lens.focal_length_mm': (14.0, 150.0),
        'camera_lens.max_aperture': (1.2, 8.0),
    },
    'formulas': {
        'mountain.Height': 'Height > 0',
        'mountain.Prominence': 'Prominence >= 0',
        'camera_lens.focal_length_mm': 'focal_length_mm > 0',
        'camera_lens.max_aperture': 'max_aperture > 0',
        'photos.color': "color IN ('RBG', 'Black/White')",
    },
    'literal_pool': {'camera_lens.focal_length_mm': [15.0]},
    'comparison_boundary': {
        'mountain.Range': ['Lasta Massif', 'lasta massif', 'Toubkal Atlas', 'toubkal atlas'],
        'mountain.Country': ['Ethiopia', 'ethiopia'],
    },
    'duplicate_share': 0.35,
    'group_size_mix': True,
    'tie_order': True,
}


def load_specification(obj: dict) -> dict:
    """Normalise a specification dict (from JSON) into the internal form."""
    spec = dict(_EMBEDDED)
    if not isinstance(obj, dict):
        return spec
    for k in ('table_sizes', 'null_targets', 'domains', 'ranges', 'formulas', 'literal_pool',
              'comparison_boundary', 'duplicate_share', 'group_size_mix', 'tie_order'):
        if k in obj and obj[k] is not None:
            spec[k] = obj[k]
    for exc in obj.get('per_column_exceptions', []) or []:
        key = '%s.%s' % (exc.get('table'), exc.get('column'))
        tgt = exc.get('targets') or ''
        if 'Include' in tgt:
            vals = []
            for part in tgt.replace('Include', '').split(','):
                part = part.strip().strip("'\".")
                if part:
                    vals.append(part)
            if vals:
                spec.setdefault('comparison_boundary', {})[key] = vals
    for rule in obj.get('semantic_rules_and_formulas', []) or []:
        key = '%s.%s' % (rule.get('table'), rule.get('column'))
        if rule.get('formula'):
            spec.setdefault('formulas', {})[key] = rule['formula']
    spec['null_targets'] = [k for k in spec.get('null_targets', []) if not k.endswith('.id')]
    return spec


def spec_from_columns() -> dict:
    """Fallback: the embedded specification."""
    return dict(_EMBEDDED)


def domain(spec: dict, table: str, column: str) -> list:
    """Enumeration domain for a column (empty list if none)."""
    return list(spec.get('domains', {}).get('%s.%s' % (table, column), []))


def value_range(spec: dict, table: str, column: str):
    """(lo, hi) observed range for a numeric column, or None."""
    return spec.get('ranges', {}).get('%s.%s' % (table, column))


def literal_pool(spec: dict, table: str, column: str) -> list:
    """Extra literals that must appear in the column's value pool."""
    return list(spec.get('literal_pool', {}).get('%s.%s' % (table, column), []))


def boundary_values(spec: dict, table: str, column: str) -> list:
    """Comparison-boundary variants (case changes) for a text column."""
    return list(spec.get('comparison_boundary', {}).get('%s.%s' % (table, column), []))


def is_null_target(spec: dict, table: str, column: str) -> bool:
    return '%s.%s' % (table, column) in set(spec.get('null_targets', []))


def table_size(spec: dict, table: str, rng) -> int:
    """Rows to append for a table: the specified size, jittered by +-1 (>= 0)."""
    base = int(spec.get('table_sizes', {}).get(table, 0))
    if base <= 0:
        return 0
    return max(0, base + rng.choice((-1, 0, 0, 1)))
