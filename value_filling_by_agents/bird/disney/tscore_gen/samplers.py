"""Row samplers."""
import random

from . import pools


def _fresh(used, key_cols, candidate):
    key = tuple(candidate[c] for c in key_cols)
    if key in used:
        return None
    used.add(key)
    return candidate


def _fmt_money(v):
    return "$%s" % format(int(v), ",")


def _fmt_date(month, day, year):
    return "%s %d, %d" % (month, day, year)


def _perturb_str(rng, s):
    """String perturbation: prefix / suffix / dropped-character / case variant."""
    if not s:
        return s
    u = rng.random()
    if u < 0.2:
        return s + rng.choice(" x")
    if u < 0.4:
        return rng.choice(" x") + s
    if u < 0.6 and len(s) > 1:
        i = rng.randrange(len(s))
        return s[:i] + s[i + 1:]
    if u < 0.8:
        return s.lower() if s != s.lower() else s.upper()
    return s


def _pick(rng, pool, boundary, dup_share=0.35):
    """Draw from pool with duplicate share and occasional boundary/near-variant."""
    r = rng.random()
    if boundary and r < 0.15:
        return rng.choice(boundary)
    if r < 0.15 + dup_share:
        return rng.choice(pool)
    return _perturb_str(rng, rng.choice(pool))


def _pick_fk(rng, parent_pool):
    """FK value: always a real parent key (no orphans; schema has real FKs)."""
    if not parent_pool:
        return None
    return rng.choice(parent_pool)


def _null_branch(rng, share):
    """True if this row should carry a NULL in a nullable column."""
    return rng.random() < share


def _uniquify(used, base, key_cols=("x",), max_tries=200):
    """Return a fresh primary-key string based on `base`."""
    cand = base
    if (cand,) not in used:
        return cand
    for k in range(1, max_tries + 1):
        cand = "%s %d" % (base, k)
        if (cand,) not in used:
            return cand
    return None


def sample_voice_actors(schema, compact, used, rng, n, pool_values):
    """Independent key pool; movie FK references characters.movie_title."""
    compact_movies = [r["movie_title"] for r in compact.get("characters", [])]
    pool_movies = list(pool_values.get(("characters", "MOVIE_TITLE"), []))
    parent_movies = set(compact_movies) | set(pool_movies)
    parent_list = compact_movies + [t for t in pool_movies if t not in set(compact_movies)]

    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 20:
        attempts += 1
        base = rng.choice(pools.CHARACTERS)
        char = _uniquify(used, base)
        if char is None:
            continue
        used.add((char,))
        r = rng.random()
        if r < 0.10:
            movie = None
        else:
            movie = _pick_fk(rng, parent_list)
        va = None if rng.random() < 0.05 else rng.choice(pools.VOICE_ACTORS)
        rows.append({"character": char, "voice-actor": va, "movie": movie})
    return rows


def sample_characters(schema, compact, used, rng, n, voice_rows, pool_values):
    """movie_title PK; hero FK -> voice-actors.character (compact + generated)."""
    hero_pool = [r["character"] for r in compact.get("voice-actors", [])]
    hero_pool += [r["character"] for r in voice_rows]

    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 20:
        attempts += 1
        base = rng.choice(pools.MOVIE_TITLES)
        title = _uniquify(used, base)
        if title is None:
            continue
        used.add((title,))

        if rng.random() < 0.15:
            yy = rng.choice(pools.CHAR_YEAR_BOUNDARY)
        else:
            yy = rng.randint(30, 99)
        month = rng.choice(pools.MONTHS)
        day = rng.randint(1, 28)
        release_date = "%d-%s-%02d" % (day, month, yy)

        r = rng.random()
        if r < 0.071:
            hero = None
        else:
            hero = _pick_fk(rng, hero_pool)

        if _null_branch(rng, 0.179):
            villian = None
        else:
            villian = _pick(rng, pools.VILLAINS, pools.VILLAIN_BOUNDARY)

        if _null_branch(rng, 0.161):
            song = None
        else:
            song = _pick(rng, pools.SONGS, None)

        rows.append({
            "movie_title": title,
            "release_date": release_date,
            "hero": hero,
            "villian": villian,
            "song": song,
        })
    return rows


def sample_director(schema, compact, used, rng, n, character_rows, pool_values):
    """name PK is a FK to characters.movie_title (compact + generated)."""
    title_pool = [r["movie_title"] for r in compact.get("characters", [])]
    title_pool += [r["movie_title"] for r in character_rows]

    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 20:
        attempts += 1
        name = _pick_fk(rng, title_pool)
        if name is None or (name,) in used:
            continue
        used.add((name,))

        if _null_branch(rng, 0.03):
            director = None
        else:
            director = _pick(rng, pools.DIRECTORS, None)
        rows.append({"name": name, "director": director})
    return rows


def sample_movies_total_gross(schema, compact, used, rng, n, character_rows, pool_values):
    """(movie_title, release_date) PK; movie_title FK -> characters.movie_title."""
    title_pool = [r["movie_title"] for r in compact.get("characters", [])]
    title_pool += [r["movie_title"] for r in character_rows]

    tie_total_min = pools.TIE_TOTAL_MIN
    tie_total_max = pools.TIE_TOTAL_MAX
    tie_infl_max = pools.TIE_INFL_MAX

    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 20:
        attempts += 1
        title = _pick_fk(rng, title_pool)
        if title is None:
            continue

        r = rng.random()
        if r < 0.10:
            release_date = rng.choice(pools.RELEASE_LIKE_VARIANTS)
        elif r < 0.25:
            year = rng.choice(pools.RELEASE_YEAR_BOUNDARY)
            release_date = _fmt_date(rng.choice(pools.MONTHS), rng.randint(1, 28), year)
        else:
            year = rng.randint(1930, 2020)
            release_date = _fmt_date(rng.choice(pools.MONTHS), rng.randint(1, 28), year)

        key = (title, release_date)
        if key in used:
            continue
        used.add(key)

        u = rng.random()
        if u < 0.10:
            total = tie_total_min
        elif u < 0.20:
            total = tie_total_max
        elif u < 0.30:
            total = rng.choice(pools.TOTAL_GROSS_BOUNDARY)
        else:
            total = rng.randint(*pools.TOTAL_GROSS_RANGE)

        if rng.random() < 0.15:
            infl = tie_infl_max
        else:
            infl = rng.randint(*pools.INFLATION_GROSS_RANGE)

        genre = None if rng.random() < 0.05 else rng.choice(pools.GENRES)
        mpaa = None if rng.random() < 0.05 else rng.choice(pools.MPAA_RATINGS)
        total_gross = None if rng.random() < 0.05 else _fmt_money(total)
        infl_gross = None if rng.random() < 0.05 else _fmt_money(infl)
        rows.append({
            "movie_title": title,
            "release_date": release_date,
            "genre": genre,
            "MPAA_rating": mpaa,
            "total_gross": total_gross,
            "inflation_adjusted_gross": infl_gross,
        })
    return rows


def sample_revenue(schema, compact, used, rng, n, pool_values):
    years = [r["Year"] for r in compact.get("revenue", [])]
    candidates = [y for y in pools.REVENUE_YEARS if y not in set(years)]
    rng.shuffle(candidates)
    rows = []
    for y in candidates[:n]:
        if (y,) in used:
            continue
        studio = None if rng.random() < 0.038 else round(rng.uniform(*pools.STUDIO_ENT_RANGE), 1)
        consumer = None if rng.random() < 0.077 else round(rng.uniform(*pools.CONSUMER_PROD_RANGE), 1)
        interactive = None if rng.random() < 0.538 else rng.randint(*pools.INTERACTIVE_RANGE)
        parks = round(rng.uniform(*pools.PARKS_RANGE), 1)
        media = None if rng.random() < 0.115 else "%.0f" % rng.uniform(*pools.MEDIA_NETWORKS_RANGE)
        total = rng.randint(*pools.TOTAL_RANGE)
        rows.append({
            "Year": y,
            "Studio Entertainment[NI 1]": studio,
            "Disney Consumer Products[NI 2]": consumer,
            "Disney Interactive[NI 3][Rev 1]": interactive,
            "Walt Disney Parks and Resorts": parks,
            "Disney Media Networks": media,
            "Total": total,
        })
        used.add((y,))
    return rows


def _jitter(rng, base):
    """Minor per-instance jitter centred on the specified size."""
    lo = max(0, base - max(2, base // 10))
    hi = base + max(2, base // 10)
    return rng.randint(lo, hi)


def generate_all(schema, compact, used, rng, pool_values=None):
    """Generate rows for every table in dependency order."""
    pool_values = pool_values or {}
    sizes = {t: _jitter(rng, pools.TABLE_SIZES[t]) for t in pools.TABLE_SIZES}
    sizes["revenue"] = min(sizes["revenue"], len(pools.REVENUE_YEARS))

    voice_rows = sample_voice_actors(
        schema, compact, used["voice-actors"], rng, sizes["voice-actors"], pool_values)
    character_rows = sample_characters(
        schema, compact, used["characters"], rng, sizes["characters"], voice_rows, pool_values)
    director_rows = sample_director(
        schema, compact, used["director"], rng, sizes["director"], character_rows, pool_values)
    gross_rows = sample_movies_total_gross(
        schema, compact, used["movies_total_gross"], rng,
        sizes["movies_total_gross"], character_rows, pool_values)
    revenue_rows = sample_revenue(
        schema, compact, used["revenue"], rng, sizes["revenue"], pool_values)

    return {
        "voice-actors": voice_rows,
        "characters": character_rows,
        "director": director_rows,
        "movies_total_gross": gross_rows,
        "revenue": revenue_rows,
    }
