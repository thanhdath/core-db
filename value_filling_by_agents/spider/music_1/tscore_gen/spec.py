"""The generation specification, encoded as data (no SQL is ever evaluated)."""

GENRES = ['blues', 'folk', 'modern', 'nazrul', 'pop', 'tagore']
GENRE_CASE_VARIANTS = {'blues': ['BLUES'], 'modern': ['MODERN']}
COUNTRIES = ['India', 'Bangladesh', 'USA', 'UK']
COUNTRY_CASE_VARIANTS = {'India': ['india'], 'Bangladesh': ['bangladesh'], 'UK': ['uk']}
LANGUAGES = ['bangla', 'english']
LANGUAGE_CASE_VARIANTS = {'english': ['ENGLISH']}
FORMATS = ['mp3', 'mp4']
FORMAT_CASE_VARIANTS = {'mp3': ['MP3'], 'mp4': ['MP4']}
GENDERS = ['Male', 'Female']
RESOLUTIONS = [320, 512, 720, 1080]
RESOLUTION_BOUNDARIES = [498, 499, 500, 501, 799, 800, 801, 999, 1000, 1001]
RATING_BOUNDARIES = [6, 7, 8, 9]
DURATION_VARIANTS = ['3:', '4:', '3: x', '5:', '4: x']
DURATION_LITERALS = ['3:45', '3:%', '%4:%', '4:%']

TABLE_SIZES = {'genre': 6, 'artist': 6, 'files': 6, 'song': 6}

NULL_TARGETS = [
    'artist.country', 'artist.gender', 'artist.preferred_genre',
    'files.artist_name', 'files.file_size', 'files.duration', 'files.formats',
    'genre.rating', 'genre.most_popular_in',
    'song.artist_name', 'song.country', 'song.f_id', 'song.genre_is',
    'song.rating', 'song.languages', 'song.releasedate',
]

DUPLICATE_SHARE = {
    'artist.artist_name': 0.30,
    'artist.country': 0.30,
    'files.formats': 0.30,
    'files.file_size': 0.30,
    'song.artist_name': 0.30,
    'song.song_name': 0.30,
}

GROUP_TARGETS = ['artist.artist_name', 'song.artist_name', 'song.languages',
                 'files.formats', 'song.f_id', 'song.resolution']

TIE_TARGETS = ['artist.artist_name', 'song.artist_name', 'files.formats',
               'files.duration', 'song.rating', 'song.resolution']

BOUNDARY_VALUES = {
    'song.rating': RATING_BOUNDARIES,
    'song.resolution': RESOLUTION_BOUNDARIES,
    'song.genre_is': ['blues', 'BLUES', 'modern', 'MODERN'],
    'genre.g_name': ['blues', 'BLUES', 'modern', 'MODERN'],
    'song.languages': ['english', 'ENGLISH'],
    'artist.country': ['Bangladesh', 'bangladesh', 'UK', 'uk', 'India', 'india'],
    'files.formats': ['mp3', 'MP3', 'mp4', 'MP4'],
}

DEPENDENCIES = [
    ('artist', 'preferred_genre', 'genre', 'g_name'),
    ('files', 'artist_name', 'artist', 'artist_name'),
    ('song', 'artist_name', 'artist', 'artist_name'),
    ('song', 'f_id', 'files', 'f_id'),
    ('song', 'genre_is', 'genre', 'g_name'),
]

RATING_MIN, RATING_MAX = 1, 10
RESOLUTION_MIN = 1
F_ID_MIN = 1


def case_variants(value: str) -> list:
    """Return the case variants declared for an enumerated value (may be empty)."""
    for table in (GENRE_CASE_VARIANTS, COUNTRY_CASE_VARIANTS, LANGUAGE_CASE_VARIANTS,
                  FORMAT_CASE_VARIANTS):
        if value in table:
            return list(table[value])
    return []


def enum_for(column: str):
    """Return the enumerated domain for a column key, or None."""
    return {
        'genre.g_name': GENRES,
        'artist.preferred_genre': GENRES,
        'song.genre_is': GENRES,
        'artist.country': COUNTRIES,
        'song.country': COUNTRIES,
        'song.languages': LANGUAGES,
        'files.formats': FORMATS,
        'artist.gender': GENDERS,
    }.get(column)
