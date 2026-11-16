"""Semantic rules, enumerations, literal pools and NULL rule, applied by construction in Python."""
import re

ENUMS = {
    ('player', 'bats'): ['R', 'L', 'B', ''],
    ('player', 'throws'): ['R', 'L', ''],
    ('team', 'div_win'): ['Y', 'N', ''],
    ('team', 'wc_win'): ['Y', 'N', ''],
    ('team', 'lg_win'): ['Y', 'N', ''],
    ('team', 'ws_win'): ['Y', 'N', ''],
    ('park', 'country'): ['US', 'MX', 'CA', 'PR', 'AU', 'JP'],
    ('all_star', 'league_id'): ['AL', 'NL'],
    ('all_star', 'gp'): [0, 1],
    ('hall_of_fame', 'inducted'): ['Y', 'N'],
    ('hall_of_fame', 'category'): ['Player', 'Manager', 'Pioneer/Executive', 'Umpire'],
    ('player_award', 'tie'): ['Y', ''],
    ('manager_award', 'tie'): ['Y', ''],
    ('manager', 'plyr_mgr'): ['Y', 'N'],
    ('fielding', 'pos'): ['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF', 'DH'],
    ('fielding_postseason', 'pos'): ['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF', 'DH'],
    ('team_half', 'half'): [1, 2],
    ('manager_half', 'half'): [1, 2],
    ('team_franchise', 'active'): ['Y', 'N', ''],
    ('college', 'country'): ['USA'],
}

LITERAL_POOLS = {
    ('all_star', 'year'): [1998],
    ('park', 'park_name'): ['Columbia Park'],
    ('postseason', 'year'): [1885],
    ('team', 'name'): ['Boston Red Stockings'],
    ('team_franchise', 'active'): ['Y'],
    ('college', 'college_id'): ['yale', 'YALE'],
    ('college', 'name_full'): ['Yale University', 'yale university'],
}

BOUNDARY_VALUES = {
    ('home_game', 'year'): [2013, 2014, 2015],
    ('team', 'year'): [1997, 1998, 1999, 2013, 2014, 2015],
    ('salary', 'year'): [1984, 1985, 1986, 1989, 1990, 1991, 2001, 2010],
    ('postseason', 'ties'): [0, 1, 2],
    ('manager', 'rank'): [2, 3, 4],
}

INT_RANGES = {
    ('player', 'birth_year'): (1800, 2000),
    ('player', 'birth_month'): (1, 12),
    ('player', 'birth_day'): (1, 31),
    ('player', 'weight'): (100, 300),
    ('player', 'height'): (60, 90),
    ('team', 'year'): (1871, 2015),
    ('team', 'rank'): (1, 12),
    ('home_game', 'year'): (1871, 2015),
    ('salary', 'year'): (1984, 2015),
    ('manager', 'rank'): (1, 12),
    ('all_star', 'year'): (1933, 2015),
    ('all_star', 'game_num'): (0, 2),
    ('all_star', 'starting_pos'): (1, 9),
    ('team_half', 'rank'): (1, 12),
    ('manager_half', 'rank'): (1, 12),
    ('player_college', 'year'): (1871, 2015),
}

NONNEG = {
    ('team', 'w'), ('team', 'l'), ('team', 'attendance'),
    ('home_game', 'games'), ('home_game', 'openings'), ('home_game', 'attendance'),
    ('salary', 'salary'),
    ('postseason', 'ties'), ('postseason', 'wins'), ('postseason', 'losses'),
    ('manager', 'g'), ('manager', 'w'), ('manager', 'l'),
    ('hall_of_fame', 'votes'), ('hall_of_fame', 'ballots'), ('hall_of_fame', 'needed'),
    ('player_award_vote', 'points_won'), ('player_award_vote', 'votes_first'),
    ('manager_award_vote', 'points_won'), ('manager_award_vote', 'votes_first'),
    ('batting', 'g'), ('batting', 'ab'), ('batting', 'h'), ('batting', 'double'), ('batting', 'triple'),
    ('batting', 'hr'), ('batting', 'rbi'), ('batting', 'sb'), ('batting', 'cs'), ('batting', 'bb'),
    ('batting', 'so'),
    ('pitching', 'w'), ('pitching', 'l'), ('pitching', 'g'), ('pitching', 'gs'), ('pitching', 'cg'),
    ('pitching', 'sho'), ('pitching', 'sv'), ('pitching', 'ipouts'), ('pitching', 'h'), ('pitching', 'er'),
    ('pitching', 'hr'), ('pitching', 'bb'), ('pitching', 'so'), ('pitching', 'era'),
    ('fielding', 'g'), ('fielding', 'gs'), ('fielding', 'inn_outs'), ('fielding', 'po'), ('fielding', 'a'),
    ('fielding', 'e'), ('fielding', 'dp'),
    ('appearances', 'g_all'), ('appearances', 'gs'), ('appearances', 'g_batting'),
    ('appearances', 'g_defense'), ('appearances', 'g_p'), ('appearances', 'g_c'),
    ('appearances', 'g_1b'), ('appearances', 'g_2b'), ('appearances', 'g_3b'), ('appearances', 'g_ss'),
    ('appearances', 'g_lf'), ('appearances', 'g_cf'), ('appearances', 'g_rf'), ('appearances', 'g_of'),
    ('appearances', 'g_dh'), ('appearances', 'g_ph'), ('appearances', 'g_pr'),
    ('batting_postseason', 'g'), ('batting_postseason', 'ab'), ('batting_postseason', 'h'),
    ('pitching_postseason', 'w'), ('pitching_postseason', 'l'), ('pitching_postseason', 'g'),
    ('pitching_postseason', 'gs'), ('pitching_postseason', 'ipouts'), ('pitching_postseason', 'era'),
    ('fielding_postseason', 'g'), ('fielding_postseason', 'gs'), ('fielding_postseason', 'inn_outs'),
    ('fielding_outfield', 'glf'), ('fielding_outfield', 'gcf'), ('fielding_outfield', 'grf'),
    ('team_half', 'g'), ('team_half', 'w'), ('team_half', 'l'),
    ('manager_half', 'g'), ('manager_half', 'w'), ('manager_half', 'l'),
}

POSITIVE = {
    ('player_award_vote', 'points_max'),
    ('manager_award_vote', 'points_max'),
    ('team', 'g'),
}

RATE = {('team', 'fp')}

DATE_RANGES = {
    ('player', 'debut'): ('1871-01-01', '2015-12-31'),
    ('player', 'final_game'): ('1871-01-01', '2015-12-31'),
    ('home_game', 'span_first'): ('1871-01-01', '2015-12-31'),
    ('home_game', 'span_last'): ('1871-01-01', '2015-12-31'),
}

def _le(a, b):
    """a <= b under SQL three-valued logic (NULL operand -> not FALSE -> True)."""
    if a is None or b is None:
        return True
    try:
        return a <= b
    except TypeError:
        return True


def _sum_le(a, b, c):
    if a is None or b is None or c is None:
        return True
    try:
        return a + b <= c
    except TypeError:
        return True


CROSS_RULES = {
    ('player', ('debut', 'final_game')): lambda r: _le(r.get('debut'), r.get('final_game')),
    ('team', ('w', 'l', 'g')): lambda r: _sum_le(r.get('w'), r.get('l'), r.get('g')),
    ('batting', ('h', 'ab')): lambda r: _le(r.get('h'), r.get('ab')),
    ('batting_postseason', ('h', 'ab')): lambda r: _le(r.get('h'), r.get('ab')),
    ('pitching', ('gs', 'g')): lambda r: _le(r.get('gs'), r.get('g')),
    ('pitching_postseason', ('gs', 'g')): lambda r: _le(r.get('gs'), r.get('g')),
    ('home_game', ('span_first', 'span_last')): lambda r: _le(r.get('span_first'), r.get('span_last')),
    ('manager', ('w', 'l', 'g')): lambda r: _sum_le(r.get('w'), r.get('l'), r.get('g')),
    ('team_half', ('w', 'l', 'g')): lambda r: _sum_le(r.get('w'), r.get('l'), r.get('g')),
    ('manager_half', ('w', 'l', 'g')): lambda r: _sum_le(r.get('w'), r.get('l'), r.get('g')),
}

def _in_enum(table, col, v):
    if v is None:
        return True
    pool = ENUMS.get((table, col))
    if pool is None:
        return True
    return v in pool


def _in_range(table, col, v):
    if v is None:
        return True
    rng = INT_RANGES.get((table, col))
    if rng is None:
        return True
    try:
        return rng[0] <= v <= rng[1]
    except TypeError:
        return True


def _nonneg(table, col, v):
    if v is None:
        return True
    if (table, col) not in NONNEG:
        return True
    try:
        return v >= 0
    except TypeError:
        return True


def _positive(table, col, v):
    if v is None:
        return True
    if (table, col) not in POSITIVE:
        return True
    try:
        return v > 0
    except TypeError:
        return True


def _rate(table, col, v):
    if v is None:
        return True
    if (table, col) not in RATE:
        return True
    try:
        return 0 <= v <= 1
    except TypeError:
        return True


def _player_id_len(table, col, v):
    if table == 'player' and col == 'player_id' and v is not None:
        return 6 <= len(str(v)) <= 10
    return True


def _date_range(table, col, v):
    if v is None:
        return True
    rng = DATE_RANGES.get((table, col))
    if rng is None:
        return True
    s = str(v)
    return rng[0] <= s <= rng[1]


def value_ok(table, col, v):
    """All single-column rules for one value."""
    return (_in_enum(table, col, v) and _in_range(table, col, v) and _nonneg(table, col, v)
            and _positive(table, col, v) and _rate(table, col, v) and _player_id_len(table, col, v)
            and _date_range(table, col, v))


def row_ok(table, row):
    """All cross-column rules for one row dict."""
    for (t, cols), pred in CROSS_RULES.items():
        if t != table:
            continue
        try:
            if not pred(row):
                return False
        except Exception:
            return False
    return True


def null_share(schema, table, col):
    """Compact database's NULL share for a column (0.0 if none observed)."""
    vals = schema.original_values.get((table, col), [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / float(len(vals))


def is_nullable(schema, table, col):
    """A column is nullable unless it is NOT NULL or part of the primary key."""
    tm = schema.tables.get(table)
    if tm is None:
        return False
    for cm in tm.columns:
        if cm.name == col:
            if cm.notnull or cm.pk_pos > 0:
                return False
            return True
    return False


def perturb_number(v, rng):
    """+-1 / +-2 perturbation of a numeric value."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return v
    d = rng.choice([-2, -1, 1, 2])
    y = x + d
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return int(round(y))
    return y


def perturb_string(v, rng):
    """Prefix / suffix / dropped-character variants and LIKE patterns without '%'."""
    s = str(v)
    if not s:
        return s
    u = rng.random()
    if u < 0.2:
        return s + rng.choice('abcdefghijklmnopqrstuvwxyz0123456789')
    if u < 0.4:
        return rng.choice('abcdefghijklmnopqrstuvwxyz0123456789') + s
    if u < 0.6 and len(s) > 1:
        i = rng.randrange(len(s))
        return s[:i] + s[i + 1:]
    if u < 0.8:
        return s.upper() if s != s.upper() else s.lower()
    return s


def near_variant(v, rng):
    """~5% share near-variants (case changes, one-char edits)."""
    if v is None:
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return perturb_number(v, rng)
    return perturb_string(v, rng)


def like_pattern(v):
    """LIKE pattern without '%' (exact match)."""
    return str(v).replace('%', '')
