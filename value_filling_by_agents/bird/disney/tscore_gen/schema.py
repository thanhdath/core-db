"""Schema description for the Disney database."""


class Column:
    def __init__(self, name, ctype, nullable=True):
        self.name = name
        self.ctype = ctype
        self.nullable = nullable


class Table:
    def __init__(self, name, columns, primary_key, foreign_keys=None):
        self.name = name
        self.columns = columns
        self.primary_key = primary_key
        self.foreign_keys = foreign_keys or []


class Schema:
    def __init__(self, tables, order=None):
        self.tables = tables
        self.order = order or list(tables.keys())
        self.fks = {}
        self.ddl = []
        for tname, tm in tables.items():
            for col, rt, rc in tm.foreign_keys:
                self.fks[(tname, col)] = (rt, rc)

    def table_order_flat(self):
        return list(self.order)


def q(name):
    return '"%s"' % name.replace('"', '""')


CHARACTERS = Table(
    "characters",
    [
        Column("movie_title", "TEXT", False),
        Column("release_date", "TEXT", True),
        Column("hero", "TEXT", True),
        Column("villian", "TEXT", True),
        Column("song", "TEXT", True),
    ],
    ["movie_title"],
    [("hero", "voice-actors", "character")],
)

DIRECTOR = Table(
    "director",
    [
        Column("name", "TEXT", False),
        Column("director", "TEXT", True),
    ],
    ["name"],
    [("name", "characters", "movie_title")],
)

MOVIES_TOTAL_GROSS = Table(
    "movies_total_gross",
    [
        Column("movie_title", "TEXT", False),
        Column("release_date", "TEXT", False),
        Column("genre", "TEXT", True),
        Column("MPAA_rating", "TEXT", True),
        Column("total_gross", "TEXT", True),
        Column("inflation_adjusted_gross", "TEXT", True),
    ],
    ["movie_title", "release_date"],
    [("movie_title", "characters", "movie_title")],
)

REVENUE = Table(
    "revenue",
    [
        Column("Year", "INTEGER", False),
        Column("Studio Entertainment[NI 1]", "REAL", True),
        Column("Disney Consumer Products[NI 2]", "REAL", True),
        Column("Disney Interactive[NI 3][Rev 1]", "INTEGER", True),
        Column("Walt Disney Parks and Resorts", "REAL", True),
        Column("Disney Media Networks", "TEXT", True),
        Column("Total", "INTEGER", True),
    ],
    ["Year"],
    [],
)

VOICE_ACTORS = Table(
    "voice-actors",
    [
        Column("character", "TEXT", False),
        Column("voice-actor", "TEXT", True),
        Column("movie", "TEXT", True),
    ],
    ["character"],
    [("movie", "characters", "movie_title")],
)

SCHEMA = Schema(
    {
        "voice-actors": VOICE_ACTORS,
        "characters": CHARACTERS,
        "director": DIRECTOR,
        "movies_total_gross": MOVIES_TOTAL_GROSS,
        "revenue": REVENUE,
    },
    order=["voice-actors", "characters", "director", "movies_total_gross", "revenue"],
)

DDL = [
    'CREATE TABLE IF NOT EXISTS characters (movie_title TEXT primary key, '
    'release_date TEXT, hero TEXT, villian TEXT, song TEXT, '
    'foreign key (hero) references "voice-actors"(character))',
    'CREATE TABLE IF NOT EXISTS director (name TEXT primary key, director TEXT, '
    'foreign key (name) references characters(movie_title))',
    'CREATE TABLE IF NOT EXISTS movies_total_gross (movie_title TEXT, '
    'release_date TEXT, genre TEXT, MPAA_rating TEXT, total_gross TEXT, '
    'inflation_adjusted_gross TEXT, primary key (movie_title, release_date), '
    'foreign key (movie_title) references characters(movie_title))',
    'CREATE TABLE IF NOT EXISTS revenue (Year INTEGER primary key, '
    '"Studio Entertainment[NI 1]" REAL, "Disney Consumer Products[NI 2]" REAL, '
    '"Disney Interactive[NI 3][Rev 1]" INTEGER, "Walt Disney Parks and Resorts" REAL, '
    '"Disney Media Networks" TEXT, Total INTEGER)',
    'CREATE TABLE IF NOT EXISTS "voice-actors" (character TEXT primary key, '
    '"voice-actor" TEXT, movie TEXT, foreign key (movie) references characters(movie_title))',
]
SCHEMA.ddl = DDL
