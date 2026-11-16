"""Specification -> per-column sampling plan (built by construction, no SQL evaluation)."""
from .schema import q

TABLE_SIZES = {'Author': 60, 'Conference': 30, 'Journal': 30, 'Paper': 150, 'PaperAuthor': 300}

BOUNDARY = {
    ('Paper', 'Id'): [4, 5, 6, 105, 106, 107],
    ('Paper', 'JournalId'): [199, 200, 201, 299, 300, 301],
    ('Paper', 'ConferenceId'): [-1, 0, 1, 186, 187, 188],
    ('Paper', 'Year'): [-1, 0, 1, 1999, 2000, 2001],
    ('PaperAuthor', 'PaperId'): [4, 5, 6, 100, 101, 102],
}
TEXT_BOUNDARY = {
    ('Paper', 'Title'): ['', 'x'],
    ('Paper', 'Keyword'): ['Turbulent Fluids', 'turbulent fluids', 'nt F', 'nt f',
                           'urbulent F', 'urbulent f'],
    ('Journal', 'FullName'): ['Physics of Fluids', 'physics of fluids',
                              'Iet Software/iee Proceedings - Software',
                              'iet software/iee proceedings - software'],
    ('Conference', 'FullName'): [
        'International Conference on Thermoelectrics',
        'international conference on thermoelectrics',
        'International Conference on Wireless Networks, Communications and Mobile Computing',
        'international conference on wireless networks, communications and mobile computing'],
    ('Author', 'Affiliation'): ['Stanford University', 'stanford university',
                                'Massachusetts Institute of Technology',
                                'massachusetts institute of technology',
                                'MaInstitute of Technology', 'mainstitute of technology'],
}
LIKE_LITS = {
    ('Paper', 'Title'): ['145 GROWTH HORMONE RECEPTORS AND THE ONSET OF HYPERINSULINEMIA IN THE OBESE ZUCKER RAT',
                         'Testing timed automata'],
    ('Paper', 'Keyword'): ['Turbulent Fluids', 'Turbulent Fluidt', 'Turbulent Fluids x'],
}
NULL_SHARE = {
    ('Author', 'Name'): 0.10,
    ('Author', 'Affiliation'): 0.30,
    ('Paper', 'Title'): 0.07,
    ('Paper', 'Keyword'): 0.76,
    ('Paper', 'ConferenceId'): 0.15,
    ('Paper', 'JournalId'): 0.15,
    ('PaperAuthor', 'Name'): 0.10,
    ('PaperAuthor', 'Affiliation'): 0.30,
    ('PaperAuthor', 'PaperId'): 0.10,
    ('PaperAuthor', 'AuthorId'): 0.10,
}
DUP_SHARE = {
    ('Paper', 'Title'): 0.30, ('Paper', 'Year'): 0.30,
    ('Journal', 'FullName'): 0.30, ('Conference', 'FullName'): 0.30,
    ('PaperAuthor', 'Name'): 0.30, ('PaperAuthor', 'AuthorId'): 0.30,
}
RANGES = {
    ('Paper', 'Year'): (1900, 2025),
}
VOCAB = {
    ('Author', 'Name'): ['Ernest Jordan', 'K. MORIBE', 'D. Jakominich', 'William H. Nailon',
                         'P. B. Littlewood', 'A. Kuroiwa', 'Jose Pereira', 'Buzz Aldrin',
                         'Thomas Wiegand', 'ADAM G. JONES', 'Kazuo Iwama'],
    ('Author', 'Affiliation'): ['Cavendish Laboratory|Cambridge University',
                                'Purdue University, West Lafayette, Indiana 47907-2023',
                                'Univ . of California at Berkeley',
                                'Rijksuniversiteit.Utrecht',
                                'NASA Langley Research Center',
                                'Birkbeck University of London'],
    ('Paper', 'Title'): ['Stitching videos streamed by mobile phones in real-time',
                         'A nonlocal convection-diffusion equation',
                         'Area Effects in Cepaea',
                         'Complexity of Finding Short Resolution Proofs',
                         'Testing timed automata',
                         'Natural History of the Psychoneuroses'],
    ('Paper', 'Keyword'): ['mobile video capturing|real-time|video stitching',
                           'Nonlocal diffusion; Convection-diffusion; Asymptotic behaviour',
                           'Turbulent Fluids', 'turbulent fluids',
                           'Computational model; X-machine; Ants'],
    ('Conference', 'ShortName'): ['IADIS', 'IADT', 'ICOMP', 'ICAC', 'IC-AI', 'ICAIL', 'ICALP'],
    ('Conference', 'FullName'): ['International Association for Development of the Information Society',
                                 'International Conference on Internet Computing',
                                 'International Conference on Artificial Intelligence',
                                 'International Conference on Thermoelectrics'],
    ('Conference', 'HomePage'): ['http://example.org/conf', ''],
    ('Journal', 'ShortName'): ['ICOM', 'AEPIA', 'IBMRD', 'IBMSJ', 'TCBB', 'TON', 'ANNALS'],
    ('Journal', 'FullName'): ['Zeitschrift Fuer Interaktive Und Kooperative Medien',
                              'Ibm Journal of Research and Development',
                              'IEEE/ACM Transactions on Networking',
                              'Physics of Fluids'],
    ('Journal', 'HomePage'): ['http://example.org/journal', ''],
    ('PaperAuthor', 'Name'): ['ADAM G. JONES', 'Kazuo Iwama', 'Asgeir Finnseth',
                              'M. H. Friedman', 'Patrick Durand', 'S. LOPEZ'],
    ('PaperAuthor', 'Affiliation'): ['Kyushu University 812 Fukuoka Japan',
                                     'Microsoft', 'Nanjing University',
                                     'Office of Naval Research'],
}


def _kind(table, col, type_str):
    t = (type_str or '').lower()
    if col == 'Year':
        return 'year'
    if 'int' in t:
        return 'int'
    if col == 'HomePage':
        return 'url'
    if col == 'Keyword':
        return 'keyword'
    if col == 'Title':
        return 'title'
    if col == 'Name':
        return 'name'
    if col == 'Affiliation':
        return 'affiliation'
    return 'text'


def build_spec(schema):
    """Return {(table, column): plan} for every column of every table."""
    spec = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            key = (t, cm.name)
            is_pk = cm.pk_pos > 0
            nullable = not cm.notnull and not is_pk
            ns = NULL_SHARE.get(key, 0.0) if nullable else 0.0
            plan = {
                'kind': _kind(t, cm.name, cm.type_str),
                'null_share': ns,
                'pool': list(TEXT_BOUNDARY.get(key, [])),
                'lo': None, 'hi': None,
                'dup_share': DUP_SHARE.get(key, 0.0),
                'like_lits': list(LIKE_LITS.get(key, [])),
                'enum': None,
                'boundary': list(BOUNDARY.get(key, [])),
                'vocab': list(VOCAB.get(key, [])),
            }
            if key in RANGES:
                plan['lo'], plan['hi'] = RANGES[key]
            if plan['kind'] == 'int' and plan['lo'] is None:
                plan['lo'], plan['hi'] = 0, 1000
            if plan['kind'] == 'year' and plan['lo'] is None:
                plan['lo'], plan['hi'] = 1900, 2025
            spec[key] = plan
    return spec


def table_size(table, rng):
    """Table size per instance: spec size with +-20% jitter, at least 1."""
    base = TABLE_SIZES.get(table, 30)
    lo = max(1, int(base * 0.8))
    hi = max(lo, int(base * 1.2))
    return rng.randint(lo, hi)
