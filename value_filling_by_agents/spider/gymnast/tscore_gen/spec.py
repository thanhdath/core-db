"""Specification constants (generation specification, round 1)."""

SCORE_RANGE = (8.5, 10.0)
SCORE_STEP = 0.001
MEASURE_STEP = 0.01
TOTAL_RANGE = (50.0, 60.0)
AGE_RANGE = (15.0, 40.0)
HEIGHT_RANGE = (1.55, 2.05)
NULL_SHARE = 0.10

NULL_TARGETS: dict = {}

NAME_POOL = [
    'Paul Hamm', 'Lorraine Su\u00e1arez Carmona', 'Ashley P\u00e9rez Cabrera',
    'Elizabeth Qui\u00f1\u00f3nez Aroyo', 'Eve Tatiana Cruz Oviedo', 'Nadia Caba Rodr\u00edguez',
    'Clary Sermina Delgado Cid', 'Marina Castro Medina', 'Carlos Diaz Pena',
    'Ana Maria Lopez', 'Jose Rodriguez', 'Maria Gonzalez', 'Luis Martinez',
    'Sofia Hernandez', 'Diego Torres', 'Valentina Ramirez', 'Andres Flores',
]
NAME_VARIANTS = {
    'Lorraine Su\u00e1arez Carmona': ['Lorraine Suarez Carmona', 'lorraine su\u00e1arez carmona'],
    'Ashley P\u00e9rez Cabrera': ['Ashley Perez Cabrera', 'ashley p\u00e9rez cabrera'],
    'Elizabeth Qui\u00f1\u00f3nez Aroyo': ['Elizabeth Quinonez Aroyo', 'elizabeth qui\u00f1\u00f3nez aroyo'],
    'Nadia Caba Rodr\u00edguez': ['Nadia Caba Rodriguez', 'nadia caba rodr\u00edguez'],
    'Clary Sermina Delgado Cid': ['clary sermina delgado cid', 'CLARY SERMINA DELGADO CID'],
}
PLACE_POOL = ['Santo Domingo', 'Bonao', 'Miami', 'Santiago de los Caballeros',
              'La Romana', 'Los Alcarrizos']
PLACE_VARIANTS = {'Santo Domingo': ['santo domingo', 'SANTO DOMINGO']}
HOMETOWN_BOUNDARY = ['Santo Domingo', 'santo domingo']

AGE_BOUNDARY = [19.0, 20.0, 21.0, 22.0]

TOTAL_POINTS_LITERALS = [57.4, 57.5, 57.6]

HOMETOWN_GROUP_SIZES = [0, 1, 2, 3]
NAME_DUPLICATE_GROUPS = 3

TABLE_SIZES = {'people': 10, 'gymnast': 7}
MIN_UNMATCHED_PEOPLE = 2

SCORE_COLUMNS = ['Floor_Exercise_Points', 'Pommel_Horse_Points', 'Rings_Points',
                 'Vault_Points', 'Parallel_Bars_Points', 'Horizontal_Bar_Points']
