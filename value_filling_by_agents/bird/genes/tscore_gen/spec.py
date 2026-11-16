"""Specification implemented by construction: value pools, ranges, boundary literals, targets."""

ENUM_POOLS = {
    ('Classification', 'Localization'): [
        'cytoplasm', 'cytoskeleton', 'nucleus', 'plasma membrane',
        'mitochondria', 'vacuole', 'ER', 'golgi',
    ],
    ('Genes', 'Essential'): ['Essential', 'Non-Essential', '?', 'Ambiguous-Essential'],
    ('Genes', 'Class'): [
        'GTP/GDP-exchange factors (GEFs)', 'ATPases', 'Molecular chaperones', 'Motorproteins',
        'Cyclins', 'Transcription factors', 'Protein Kinases',
        'Major facilitator superfamily proteins (MFS)',
    ],
    ('Genes', 'Complex'): [
        'Translation complexes', '?', 'Cytoskeleton',
        'Cyclin-CDK (Cyclin-dependent kinases) complexes',
        'Transcription complexes/Transcriptosome', 'Respiration chain complexes',
        'Nucleosomal protein complex', 'Intracellular transport complexes',
    ],
    ('Genes', 'Phenotype'): [
        '?', 'Mating and sporulation defects', 'Cell cycle defects',
        'Cell morphology and organelle mutants', 'Conditional phenotypes',
        'Stress response defects', 'Carbohydrate and lipid biosynthesis defects',
        'Nucleic acid metabolism defects',
    ],
    ('Genes', 'Function'): [
        'CELLULAR ORGANIZATION (proteins are localized to the corresponding organelle)',
        'PROTEIN SYNTHESIS', 'CELL RESCUE, DEFENSE, CELL DEATH AND AGEING',
        'CELLULAR TRANSPORT AND TRANSPORTMECHANISMS', 'PROTEIN DESTINATION',
        'CELL GROWTH, CELL DIVISION AND DNA SYNTHESIS',
        'CELLULAR COMMUNICATION/SIGNAL TRANSDUCTION', 'METABOLISM',
    ],
    ('Genes', 'Localization'): [
        'cytoplasm', 'cytoskeleton', 'nucleus', 'plasma membrane',
        'mitochondria', 'vacuole', 'ER', 'golgi',
    ],
    ('Interactions', 'Type'): ['Genetic-Physical', 'Genetic', 'Physical'],
}

BOUNDARY_LITERALS = {
    ('Genes', 'Phenotype'): ['Nucleic acid metabolism defects'],
    ('Genes', 'Function'): ['METABOLISM'],
    ('Genes', 'Essential'): ['Non-Essential'],
    ('Genes', 'Localization'): ['nucleus', 'cytoplasm'],
    ('Classification', 'Localization'): ['nucleus', 'plasma membrane', 'vacuole'],
    ('Interactions', 'Type'): ['Physical', 'Genetic-Physical'],
}

NEAR_VARIANT_CANDIDATES = {
    ('Genes', 'Phenotype'): ['Nucleic acid cts', 'Nucleic acid metefects', 'ec', 'metabolism defec'],
    ('Classification', 'Localization'): ['asma', 'sm'],
    ('Genes', 'Function'): ['TRANSCRIPTION', 'transcription', 'TIPTION', 'tiption'],
}

FUNCTION_EXCLUDED = ['TRANSCRIPTION', 'transcription', 'TIPTION', 'tiption']

DROPPED_BOUNDARY_COLUMNS = [('Genes', 'GeneID'), ('Genes', 'Chromosome')]

NUMERIC_RANGES = {
    ('Genes', 'Chromosome'): (1, 17),
    ('Interactions', 'Expression_Corr'): (0.0, 1.0),
}

ID_FORMAT = {'prefix': 'G', 'digits': 6}

DUP_SHARE = 0.35

NULL_SHARE = {('Genes', 'Complex'): 0.02}

GROUP_SIZE_TARGETS = [('Genes', 'Localization'), ('Classification', 'Localization')]

TIE_TARGETS = [('Genes', 'Localization'), ('Genes', 'Chromosome'), ('Interactions', 'Expression_Corr')]

DIFFERENT_VALUE_TARGETS = [('Interactions', 'Expression_Corr')]


def _filter_boundary_to_pool(table: str, col: str, pool: list) -> list:
    """Return boundary literals that are in the pool, plus one case-change variant each."""
    if (table, col) in DROPPED_BOUNDARY_COLUMNS:
        return []
    poolset = set(pool)
    out = []
    for b in BOUNDARY_LITERALS.get((table, col), []):
        if b in poolset:
            out.append(b)
            for v in (b.upper(), b.lower(), b.title()):
                if v != b and v not in out:
                    out.append(v)
    for b in NEAR_VARIANT_CANDIDATES.get((table, col), []):
        if b in poolset and b not in out:
            out.append(b)
    return out


def _enum_pool(table: str, col: str, observed: list) -> list:
    """Declared pool merged with observed values (declared first, deduped)."""
    declared = ENUM_POOLS.get((table, col), [])
    merged = list(dict.fromkeys([str(v) for v in declared] + [str(v) for v in observed if v is not None]))
    return merged


def _rng_range(table: str, col: str):
    return NUMERIC_RANGES.get((table, col))


def _dup_share(table: str, col: str) -> float:
    return DUP_SHARE


def _null_share(table: str, col: str, observed: list) -> float:
    """Observed NULL share of a nullable column in the compact database."""
    if not observed:
        return NULL_SHARE.get((table, col), 0.0)
    return sum(1 for v in observed if v is None) / float(len(observed))


def spec_from_columns(schema) -> dict:
    """Derive a spec dict from observed columns when specification.json is absent."""
    spec = {'enum_pools': {}, 'boundary': {}, 'ranges': {}, 'dup_share': {}, 'null_share': {},
            'group_size_targets': GROUP_SIZE_TARGETS, 'tie_targets': TIE_TARGETS,
            'different_value_targets': DIFFERENT_VALUE_TARGETS, 'id_format': ID_FORMAT}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            observed = list(schema.original_values.get(key, []))
            if key in ENUM_POOLS:
                spec['enum_pools'][key] = _enum_pool(t, cm.name, observed)
                spec['boundary'][key] = _filter_boundary_to_pool(t, cm.name, spec['enum_pools'][key])
            if key in NUMERIC_RANGES:
                spec['ranges'][key] = NUMERIC_RANGES[key]
            spec['dup_share'][key] = _dup_share(t, cm.name)
            spec['null_share'][key] = _null_share(t, cm.name, observed)
    return spec


def load_specification(raw: dict, schema) -> dict:
    """Load a specification.json dict and merge with the built-in pools/ranges."""
    spec = spec_from_columns(schema)
    if not isinstance(raw, dict):
        return spec
    for k in ('enum_pools', 'boundary', 'ranges', 'dup_share', 'null_share'):
        if k in raw and isinstance(raw[k], dict):
            for kk, vv in raw[k].items():
                key = tuple(kk) if isinstance(kk, (list, tuple)) else kk
                spec[k][key] = vv
    for k in ('group_size_targets', 'tie_targets', 'different_value_targets'):
        if k in raw and isinstance(raw[k], list):
            spec[k] = [tuple(x) if isinstance(x, (list, tuple)) else x for x in raw[k]]
    return spec
