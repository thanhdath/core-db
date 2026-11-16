"""Specification constants (generation specification, by construction)."""

TABLE_SIZES = {'building': 8, 'Institution': 11, 'protein': 6}

BOUNDARY = {
    ('building', 'Height_feet'): [145, 200],
    ('building', 'Floors'): [10, 12],
    ('Institution', 'Founded'): [1879, 1880, 1881, 1989, 1990, 1991, 1992, 2002, 2003, 2004],
    ('Institution', 'Enrollment'): [825, 826, 827, 999, 1000, 1001],
}

TYPE_VALUES = ['Private', 'Public', 'Tribal', 'private', 'r', 'R']

RANGES = {
    ('building', 'Height_feet'): (1, 2000),
    ('building', 'Floors'): (1, 200),
    ('Institution', 'Founded'): (1800, 2025),
    ('Institution', 'Enrollment'): (0, 5000),
    ('protein', 'divergence_from_human_lineage'): (0.1, 2000.0),
    ('protein', 'sequence_length'): (1.0, 5000.0),
}

NULL_SHARE = {
    ('protein', 'Institution_id'): 0.20,
    ('Institution', 'building_id'): 0.10,
}
DEFAULT_NULL_SHARE = 0.08

NAME_POOL = {
    ('building', 'Name'): ['Citizens Bank Building', 'Tampa City Hall', 'Floridan Hotel',
                           'Franklin Exchange Building', 'Park Tower', 'One Tampa City Center',
                           'Bank of America Tower', '100 North Tampa', 'Park Tower',
                           'Tampa City Hall', 'park tower'],
    ('Institution', 'Institution'): ['Ave Maria University', 'Dakota State University',
                                     'Edward Waters College', 'Haskell Indian Nations University',
                                     'Jamestown College', 'Lindenwood University-Belleville',
                                     'Mayville State University', 'Menlo College',
                                     'Menlo College', 'Jamestown College'],
    ('Institution', 'Team'): ['Gyrenes', 'Trojans', 'Tigers', 'Fighting Indians', 'Jimmies',
                              'Lynx', 'Comets', 'Oaks', 'Trojans', 'Tigers'],
    ('Institution', 'Primary_Conference'): ['The Sun', 'none', 'Gulf Coast (GCAC)', 'MCAC',
                                            'CalPac', 'AAC', 'none'],
    ('Institution', 'Location'): ['Ave Maria, Florida', 'Madison, South Dakota',
                                  'Jacksonville, Florida', 'Lawrence, Kansas',
                                  'Jamestown, North Dakota', 'Belleville, Illinois',
                                  'Mayville, North Dakota', 'Atherton, California'],
    ('protein', 'protein_name'): ['uncharacterized protein C20orf117-like',
                                  'uncharacterized protein LOC578090',
                                  'Centromeric protein E, putative',
                                  'conserved hypothetical protein',
                                  'surface antigen repeat family protein',
                                  'conserved hypothetical protein'],
    ('protein', 'common_name'): ['Tropical Clawed Frog', 'body louse', 'porkworm',
                                 'purple sea urchin', 'southern house mosquito'],
}

STREETS = ['North Franklin Street', 'John F. Kennedy Boulevard', 'Franklin Street',
           'North Tampa Street', 'East Kennedy Boulevard', 'North Tampa Street']

GROUP_SIZE_POOL = {
    ('building', 'Name'): ['Park Tower', 'Tampa City Hall', 'Floridan Hotel'],
    ('Institution', 'Institution'): ['Menlo College', 'Jamestown College', 'Ave Maria University'],
    ('Institution', 'Team'): ['Trojans', 'Tigers', 'Gyrenes'],
    ('Institution', 'Primary_Conference'): ['Gulf Coast (GCAC)', 'The Sun', 'none'],
    ('protein', 'protein_name'): ['Centromeric protein E, putative',
                                  'uncharacterized protein LOC578090',
                                  'conserved hypothetical protein'],
}

TIE_TARGETS = {
    ('building', 'Height_feet'): 579,
    ('building', 'Years_as_tallest'): '1992\u2013present',
    ('protein', 'protein_name'): 'conserved hypothetical protein',
}

FORCE_NOT_NULL = {
    ('protein', 'common_name'), ('protein', 'protein_name'), ('protein', 'accession_number'),
}
