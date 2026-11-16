"""Specification constants (generation specification, per-column exceptions)."""

DOCUMENT_TYPES = ['Book', 'Paper', 'Advertisement', 'CV']
ROLE_CODES = ['DBA', 'PROJ-MGR']
ROLE_DESCRIPTIONS = {'DBA': 'Database Administrator', 'PROJ-MGR': 'Project Manager'}
FUNCTIONAL_AREA_DESCRIPTIONS = ['Signature', 'Acknowledgement', 'Keep blank']

DOC_NAME_VARIANTS = ['David CV', 'CV', 'CV x', 'x CV', 'cv', 'CW', 'CV report']

USER_LOGIN_VALUES = ['0', '1', '2']

ACCESS_COUNT_MIN = 0
ACCESS_COUNT_MAX = 10000
ACCESS_SUM_TARGETS = [10000, 10001, 10002]

TABLE_SIZES = {
    'Roles': 2,
    'Users': 15,
    'Document_Structures': 5,
    'Functional_Areas': 3,
    'Images': 15,
    'Documents': 15,
    'Document_Functional_Areas': 15,
    'Document_Sections': 15,
    'Document_Sections_Images': 20,
}

GROUP_SIZE_TARGETS = [1, 2, 3]

DUP_SHARE_LO = 0.20
DUP_SHARE_HI = 0.50

NULL_SHARE = 0.10

STRUCTURE_CODES = ['1', '5', '6', '8', '9']
STRUCTURE_DESCRIPTIONS = ['Header', 'Main section', 'Bib', 'Image section', 'Author section']
FUNCTIONAL_AREA_CODES = ['1', '8', '9']
SECTION_TITLES = ['after', 'before', 'intro', 'appendix', 'summary', 'overview',
                  'notes', 'example', 'method', 'results', 'history', 'glossary',
                  'preface', 'conclusion', 'abstract', 'references']
IMAGE_NAMES = ['top1', 'top2', 'top3', 'top4', 'chapter1', 'chapter2', 'chapter3',
               'chapter4', 'figure1', 'figure2', 'figure3', 'figure4', 'thumb1',
               'thumb2', 'thumb3', 'thumb4']
IMAGE_ALTS = ['Lea', 'Arden', 'Mohamed', 'Chaya', 'Percival', 'Lincoln', 'Camylle', 'Ashtyn']
IMAGE_HOSTS = ['www.rempelnader.com', 'connellykertzmann.org', 'www.bernierconnelly.com',
               'abernathyboehm.com', 'gaylord.info', 'www.hellerreinger.com',
               'faycummerata.net', 'haleychamplin.net']
USER_NAMES = ['dickens.elta', 'tremblay.raheem', 'lynn.haley', 'ycremin', 'larson.vesta',
              'amelie53', 'jacklyn.schmitt', 'joanne.deckow']
DOC_NAMES = ['Learning English', 'Research about Art history', 'Learning Database',
             'Summer Sails', 'Learning Japanese', 'David CV', 'How to cook pasta',
             'Humanity: a fact']


def distinct_count_for_share(n: int, lo: float = DUP_SHARE_LO, hi: float = DUP_SHARE_HI) -> int:
    """Number of distinct values so that duplicate share (n-d)/n falls in [lo, hi]."""
    if n <= 1:
        return max(1, n)
    d_hi = int(n * (1.0 - lo))
    d_lo = int(n * (1.0 - hi)) + 1
    d_lo = max(1, d_lo)
    d_hi = max(d_lo, min(n, d_hi))
    d_mid = int(round(n * 0.7))
    return max(d_lo, min(d_hi, d_mid))


def url_pool(size: int) -> list:
    """Build `size` distinct URLs from the host pool (cycle host x path)."""
    out = []
    for i in range(size):
        host = IMAGE_HOSTS[i % len(IMAGE_HOSTS)]
        out.append('http://%s/%d.jpg' % (host, i // len(IMAGE_HOSTS) + 1))
    return out
