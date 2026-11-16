"""Random instance construction (fuzz/fuzz.py:83-196) plus the specification's by-construction rules."""
import datetime as dt

from .values import _init_sampler

TABLE_SIZES = {'artists': 40, 'albums': 60, 'employees': 12, 'customers': 30, 'genres': 12,
               'media_types': 5, 'tracks': 120, 'invoices': 60, 'invoice_lines': 200,
               'playlists': 10, 'playlist_tracks': 150}

NULL_TARGETS = {'employees.reports_to', 'customers.company', 'customers.state', 'customers.postal_code',
                'customers.phone', 'customers.fax', 'customers.support_rep_id', 'invoices.billing_state',
                'invoices.billing_postal_code', 'tracks.album_id', 'tracks.genre_id', 'tracks.composer',
                'tracks.bytes', 'artists.name', 'genres.name', 'media_types.name', 'playlists.name'}

ENUMS = {('invoice_lines', 'unit_price'): [0.99, 1.99],
         ('tracks', 'unit_price'): [0.99, 1.99]}

BOUNDARY = {
    ('employees', 'last_name'): ['Edwards', 'edwards', 'Johnson', 'johnson'],
    ('employees', 'first_name'): ['Nancy', 'nancy', 'Steve', 'steve'],
    ('employees', 'country'): ['Canada', 'canada'],
    ('customers', 'state'): ['IL', 'il', 'CA', 'ca'],
    ('customers', 'city'): ['Chicago', 'chicago'],
    ('invoices', 'billing_state'): ['IL', 'il'],
    ('invoices', 'billing_city'): ['Chicago', 'chicago'],
    ('media_types', 'name'): ['MPEG audio file', 'mpeg audio file'],
}

LIKE_VARIANTS = {
    ('artists', 'name'): ['Led', 'Led Zeppelin', 'led', 'Led x', 'Lee'],
    ('customers', 'last_name'): ['Almeida', '%Almeida%', 'almeida'],
}

DUPLICATE_SHARE = {('albums', 'title'), ('customers', 'company'), ('tracks', 'composer')}
DUP_SHARE = 0.30

GROUP_SIZES = {('employees', 'first_name'), ('employees', 'reports_to'), ('customers', 'country'),
               ('customers', 'first_name'), ('invoices', 'billing_country'), ('genres', 'name'),
               ('playlists', 'name')}

COPIED = {('invoices', 'billing_address'): ('customers', 'address'),
          ('invoices', 'billing_city'): ('customers', 'city'),
          ('invoices', 'billing_state'): ('customers', 'state'),
          ('invoices', 'billing_country'): ('customers', 'country'),
          ('invoices', 'billing_postal_code'): ('customers', 'postal_code'),
          ('invoice_lines', 'unit_price'): ('tracks', 'unit_price')}

EMPLOYEE_BIRTH = (dt.datetime(1947, 1, 1), dt.datetime(1975, 12, 31))
EMPLOYEE_HIRE = (dt.datetime(2002, 1, 1), dt.datetime(2004, 12, 31))
EMPLOYEE_TITLES = ['General Manager', 'Sales Manager', 'Sales Support Agent', 'IT Manager', 'IT Staff']
EMPLOYEE_CITIES = ['Edmonton', 'Calgary', 'Lethbridge']
EMPLOYEE_STATE = 'AB'
EMPLOYEE_COUNTRY = 'Canada'

TRACK_MS = (60000, 600000)
TRACK_BYTES = (1000000, 20000000)

QUANTITY = 1

AGG_BOUNDARY = (9, 10, 11)

UNMATCHED = {('customers', 'id'): ('invoices', 'customer_id'),
             ('genres', 'id'): ('tracks', 'genre_id'),
             ('tracks', 'id'): ('invoice_lines', 'track_id')}

HIRE_TIE = dt.datetime(2002, 5, 1, 0, 0, 0)
BIRTH_TIE = dt.datetime(1973, 7, 1, 0, 0, 0)
_TS = '%Y-%m-%d %H:%M:%S'

ROOT_EMPLOYEE = 1


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _n_rows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def _null_share(schema, table: str, column: str) -> float:
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    return sum(1 for v in vals if v is None) / len(vals)


def _plant_nulls(schema, table: str, column: str, values: list, rng) -> list:
    """NULL rule: at least one NULL row per nullable column, share follows the compact null_rate."""
    if (table, column) not in NULL_TARGETS or not values:
        return values
    n = len(values)
    share = _null_share(schema, table, column)
    k = max(1, int(round(share * n)))
    k = min(k, n)
    idx = rng.sample(range(n), k)
    out = list(values)
    for i in idx:
        out[i] = None
    return out


def _nonnull_slots(values: list) -> list:
    return [i for i, v in enumerate(values) if v is not None]


def _plant_boundary(table: str, column: str, values: list, rng) -> list:
    """Comparison boundary: literal, case-flipped variant and one value on each side."""
    lits = BOUNDARY.get((table, column))
    if not lits or not values:
        return values
    out = list(values)
    slots = _nonnull_slots(out)
    if not slots:
        return out
    for j, lit in enumerate(lits):
        out[slots[j % len(slots)]] = lit
    return out


def _plant_like(table: str, column: str, values: list, rng) -> list:
    """LIKE near-variant: literal, %literal% and case-flipped variant (non-NULL slots only)."""
    lits = LIKE_VARIANTS.get((table, column))
    if not lits or not values:
        return values
    out = list(values)
    slots = _nonnull_slots(out)
    if not slots:
        return out
    for j, lit in enumerate(lits):
        out[slots[j % len(slots)]] = lit
    return out


def _dup_count(vals: list) -> int:
    seen, dup = set(), 0
    for v in vals:
        if v is None:
            continue
        if v in seen:
            dup += 1
        else:
            seen.add(v)
    return dup


def _plant_duplicates(table: str, column: str, values: list, rng) -> list:
    """Duplicates for DISTINCT: 20-50 % of non-NULL values repeat an earlier value."""
    if (table, column) not in DUPLICATE_SHARE or not values:
        return values
    out = list(values)
    nonnull = _nonnull_slots(out)
    m = len(nonnull)
    if m < 2:
        return out
    lo = max(1, int(round(0.20 * m)))
    hi = max(lo, int(round(0.50 * m)))
    target = max(lo, min(hi, int(round(DUP_SHARE * m))))

    for _ in range(8):
        cand = list(out)
        order = list(nonnull)
        rng.shuffle(order)
        for pos in order[:target]:
            earlier = [j for j in nonnull if j < pos and cand[j] is not None]
            if earlier:
                cand[pos] = cand[rng.choice(earlier)]
        if lo <= _dup_count(cand) <= hi:
            return cand
    cand = list(out)
    base = cand[nonnull[0]]
    for pos in nonnull[1:1 + target]:
        cand[pos] = base
    if not (lo <= _dup_count(cand) <= hi):
        cand = list(out)
        for pos in nonnull[1:1 + target]:
            cand[pos] = base
    return cand


def _plant_group_sizes(table: str, column: str, values: list, rng, valid_pool=None) -> list:
    """Group sizes: at least one value with count 1, one with count 2, one with count >= 3."""
    if (table, column) not in GROUP_SIZES or not values:
        return values
    out = list(values)
    slots = _nonnull_slots(out)
    if len(slots) < 6:
        return out
    if valid_pool is not None:
        pool = sorted({v for v in valid_pool if v is not None})
        if len(pool) < 3:
            return out
    else:
        pool = sorted({str(out[i]) for i in slots})
        if len(pool) < 3:
            pool = pool + ['%s_%d' % (column, k) for k in range(3 - len(pool))]
    a, b, c = pool[0], pool[1], pool[2]
    s = slots[:6]
    out[s[0]] = a
    out[s[1]] = b
    out[s[2]] = b
    out[s[3]] = c
    out[s[4]] = c
    out[s[5]] = c
    return out


def _plant_aggregate_boundary(instance: dict, schema, rng) -> None:
    """albums with exactly 9, 10 and 11 tracks (parent group child counts)."""
    if 'albums' not in instance or 'tracks' not in instance:
        return
    albums = instance['albums']
    tracks = instance['tracks']
    if not albums.get('id') or not tracks.get('album_id'):
        return
    album_ids = albums['id']
    if len(album_ids) < 4:
        return
    chosen = album_ids[:3]
    counts = list(AGG_BOUNDARY)
    new_album = list(tracks['album_id'])
    free = [i for i, v in enumerate(new_album) if v is not None]
    pos = 0
    for aid, cnt in zip(chosen, counts):
        for _ in range(cnt):
            if pos < len(free):
                new_album[free[pos]] = aid
                pos += 1
    others = [a for a in album_ids if a not in chosen]
    if others:
        for i in free[pos:]:
            if new_album[i] in chosen:
                new_album[i] = rng.choice(others)
    tracks['album_id'] = new_album


def _plant_unmatched(instance: dict, schema, rng) -> None:
    """Unmatched joins: at least one parent without children and (if nullable) a child with NULL FK."""
    for (pt, pc), (ct, cc) in UNMATCHED.items():
        if pt not in instance or ct not in instance:
            continue
        parent_ids = instance[pt].get(pc) or []
        child_vals = instance[ct].get(cc)
        if child_vals is None or not parent_ids:
            continue
        used = {v for v in child_vals if v is not None}
        unused = [p for p in parent_ids if p not in used]
        if not unused:
            victim = parent_ids[-1]
            others = [p for p in parent_ids if p != victim]
            if others:
                for i, v in enumerate(child_vals):
                    if v == victim:
                        child_vals[i] = rng.choice(others)
        if (ct, cc) in NULL_TARGETS and child_vals:
            for i, v in enumerate(child_vals):
                if v is not None:
                    child_vals[i] = None
                    break
        instance[ct][cc] = child_vals


def _plant_order_ties(instance: dict, rng) -> None:
    """Order ties: two employees share the hire_date at rank 1 (ASC) and, when the table is large enough, at rank 10;
    two employees share the birth_date at rank 1 (DESC)."""
    emp = instance.get('employees')
    if not emp or not emp.get('id'):
        return
    n = len(emp['id'])
    if n >= 2:
        emp['hire_date'][0] = HIRE_TIE.strftime(_TS)
        emp['hire_date'][1] = HIRE_TIE.strftime(_TS)
        emp['birth_date'][0] = BIRTH_TIE.strftime(_TS)
        emp['birth_date'][1] = BIRTH_TIE.strftime(_TS)
    if n >= 11:
        hires = sorted(emp['hire_date'])
        tenth = hires[9]
        emp['hire_date'][9] = tenth
        emp['hire_date'][10] = tenth


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's generated values with replacement; empty parent -> NULL (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = instance.get(pt, {}).get(pc) or []
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Uniform rand_lin sizes w.p."""
    sizes = {}
    if rng.random() < 0.5:
        for lvl in schema.table_order:
            for t in lvl:
                min_c = 30 * rng.random()
                sizes[t] = int(min_c + int(rng.random() * 200))
    else:
        s = 1 + 30 * rng.random()
        for lvl in schema.table_order:
            for t in lvl:
                sizes[t] = int(min(s, 2500))
            s *= 4
    return sizes


def _pk_start(schema, table: str) -> int:
    """First fresh primary key: one above the compact maximum (keys fresh against compact rows)."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return 1
    col = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _build_employees(schema, rng, n: int) -> dict:
    """Employees: self-reference, hire_date > birth_date, order ties, group sizes, boundary values."""
    start = _pk_start(schema, 'employees')
    ids = list(range(start, start + n))
    cols = {c.name: [] for c in schema.tables['employees'].columns}
    cols['id'] = ids
    reports = []
    for i, eid in enumerate(ids):
        if i == 0:
            reports.append(None)
        elif i == 1:
            reports.append(ids[0])
        elif i == 2:
            reports.append(ids[0])
        elif i == 3:
            reports.append(ids[1])
        else:
            reports.append(rng.choice(ids[:i]))
    cols['reports_to'] = reports
    births, hires = [], []
    for i in range(n):
        b = EMPLOYEE_BIRTH[0] + dt.timedelta(days=rng.randint(0, (EMPLOYEE_BIRTH[1] - EMPLOYEE_BIRTH[0]).days))
        h = EMPLOYEE_HIRE[0] + dt.timedelta(days=rng.randint(0, (EMPLOYEE_HIRE[1] - EMPLOYEE_HIRE[0]).days))
        births.append(b.strftime(_TS))
        hires.append(h.strftime(_TS))
    cols['birth_date'] = births
    cols['hire_date'] = hires
    firsts = ['Nancy', 'nancy', 'Steve', 'steve', 'Andrew', 'Michael', 'Robert', 'Laura']
    lasts = ['Edwards', 'edwards', 'Johnson', 'johnson', 'Adams', 'Peacock', 'Park', 'Mitchell']
    cols['first_name'] = [firsts[i % len(firsts)] for i in range(n)]
    cols['last_name'] = [lasts[i % len(lasts)] for i in range(n)]
    cols['title'] = [EMPLOYEE_TITLES[i % len(EMPLOYEE_TITLES)] for i in range(n)]
    cols['city'] = [EMPLOYEE_CITIES[i % len(EMPLOYEE_CITIES)] for i in range(n)]
    cols['state'] = [EMPLOYEE_STATE] * n
    cols['country'] = ['Canada', 'canada'] * (n // 2) + ['Canada'] * (n % 2)
    cols['address'] = ['%d Jasper Ave NW' % (100 + i) for i in range(n)]
    cols['postal_code'] = ['T5K %dN1' % (i % 10) for i in range(n)]
    cols['phone'] = ['+1 (780) 428-%04d' % (1000 + i) for i in range(n)]
    cols['fax'] = ['+1 (780) 428-%04d' % (2000 + i) for i in range(n)]
    cols['email'] = ['emp%d@chinookcorp.com' % i for i in range(n)]
    cols['reports_to'] = _plant_nulls(schema, 'employees', 'reports_to', cols['reports_to'], rng)
    cols['first_name'] = _plant_boundary('employees', 'first_name', cols['first_name'], rng)
    cols['last_name'] = _plant_boundary('employees', 'last_name', cols['last_name'], rng)
    cols['country'] = _plant_boundary('employees', 'country', cols['country'], rng)
    cols['first_name'] = _plant_group_sizes('employees', 'first_name', cols['first_name'], rng)
    cols['reports_to'] = _plant_group_sizes('employees', 'reports_to', cols['reports_to'], rng,
                                            valid_pool=ids)
    return cols


def _build_customers(schema, rng, n: int, employees: dict) -> dict:
    """Customers: boundary values, group sizes, duplicates, LIKE variants, NULL shares, support_rep FK."""
    start = _pk_start(schema, 'customers')
    ids = list(range(start, start + n))
    cols = {c.name: [] for c in schema.tables['customers'].columns}
    cols['id'] = ids
    firsts = ['Luís', 'Leonie', 'François', 'Bjørn', 'František', 'Helena', 'Astrid', 'Daan']
    lasts = ['Almeida', 'almeida', 'Gonçalves', 'Köhler', 'Tremblay', 'Hansen', 'Wichterlová', 'Holý']
    cols['first_name'] = [firsts[i % len(firsts)] for i in range(n)]
    cols['last_name'] = [lasts[i % len(lasts)] for i in range(n)]
    companies = ['Embraer', 'JetBrains', 'Woodstock Discos', 'Banco do Brasil', 'Riotur', 'Telus']
    cols['company'] = [companies[i % len(companies)] for i in range(n)]
    cols['address'] = ['%d Main Street' % (100 + i) for i in range(n)]
    cities = ['Chicago', 'chicago', 'São José dos Campos', 'Stuttgart', 'Montréal', 'Oslo', 'Prague', 'Vienne']
    cols['city'] = [cities[i % len(cities)] for i in range(n)]
    states = ['IL', 'il', 'CA', 'ca', 'SP', 'QC', 'RJ', 'DF']
    cols['state'] = [states[i % len(states)] for i in range(n)]
    countries = ['Brazil', 'Germany', 'Canada', 'Norway', 'Czech Republic', 'Austria', 'Belgium', 'Denmark']
    cols['country'] = [countries[i % len(countries)] for i in range(n)]
    cols['postal_code'] = ['%05d' % (10000 + i) for i in range(n)]
    cols['phone'] = ['+55 (12) 3923-%04d' % (1000 + i) for i in range(n)]
    cols['fax'] = ['+55 (12) 3923-%04d' % (2000 + i) for i in range(n)]
    cols['email'] = ['cust%d@example.com' % i for i in range(n)]
    emp_ids = employees.get('id') or []
    cols['support_rep_id'] = [rng.choice(emp_ids) if emp_ids else None for _ in range(n)]
    for c in ('company', 'state', 'postal_code', 'phone', 'fax', 'support_rep_id'):
        cols[c] = _plant_nulls(schema, 'customers', c, cols[c], rng)
    cols['company'] = _plant_duplicates('customers', 'company', cols['company'], rng)
    cols['last_name'] = _plant_like('customers', 'last_name', cols['last_name'], rng)
    cols['state'] = _plant_boundary('customers', 'state', cols['state'], rng)
    cols['city'] = _plant_boundary('customers', 'city', cols['city'], rng)
    cols['country'] = _plant_group_sizes('customers', 'country', cols['country'], rng)
    cols['first_name'] = _plant_group_sizes('customers', 'first_name', cols['first_name'], rng)
    return cols


def _build_artists(schema, rng, n: int) -> dict:
    start = _pk_start(schema, 'artists')
    cols = {c.name: [] for c in schema.tables['artists'].columns}
    cols['id'] = list(range(start, start + n))
    names = ['AC/DC', 'Accept', 'Aerosmith', 'Alanis Morissette', 'Alice In Chains', 'Antônio Carlos Jobim',
             'Apocalyptica', 'Audioslave', 'Led', 'Led Zeppelin', 'led', 'Led x', 'Lee']
    cols['name'] = [names[i % len(names)] for i in range(n)]
    cols['name'] = _plant_nulls(schema, 'artists', 'name', cols['name'], rng)
    cols['name'] = _plant_like('artists', 'name', cols['name'], rng)
    return cols


def _build_albums(schema, rng, n: int, artists: dict) -> dict:
    start = _pk_start(schema, 'albums')
    cols = {c.name: [] for c in schema.tables['albums'].columns}
    cols['id'] = list(range(start, start + n))
    titles = ['For Those About To Rock We Salute You', 'Balls to the Wall', 'Restless and Wild',
              'Let There Be Rock', 'Big Ones', 'Jagged Little Pill', 'Facelift', 'Warner 25 Anos']
    cols['title'] = [titles[i % len(titles)] for i in range(n)]
    cols['title'] = _plant_duplicates('albums', 'title', cols['title'], rng)
    artist_ids = artists.get('id') or []
    cols['artist_id'] = [rng.choice(artist_ids) if artist_ids else None for _ in range(n)]
    return cols


def _build_genres(schema, rng, n: int) -> dict:
    start = _pk_start(schema, 'genres')
    cols = {c.name: [] for c in schema.tables['genres'].columns}
    cols['id'] = list(range(start, start + n))
    names = ['Rock', 'Jazz', 'Metal', 'Alternative & Punk', 'Rock And Roll', 'Blues', 'Latin', 'Reggae']
    cols['name'] = [names[i % len(names)] for i in range(n)]
    cols['name'] = _plant_nulls(schema, 'genres', 'name', cols['name'], rng)
    cols['name'] = _plant_group_sizes('genres', 'name', cols['name'], rng)
    return cols


def _build_media_types(schema, rng, n: int) -> dict:
    start = _pk_start(schema, 'media_types')
    cols = {c.name: [] for c in schema.tables['media_types'].columns}
    cols['id'] = list(range(start, start + n))
    names = ['MPEG audio file', 'mpeg audio file', 'Protected AAC audio file',
             'Protected MPEG-4 video file', 'Purchased AAC audio file', 'AAC audio file']
    cols['name'] = [names[i % len(names)] for i in range(n)]
    cols['name'] = _plant_nulls(schema, 'media_types', 'name', cols['name'], rng)
    cols['name'] = _plant_boundary('media_types', 'name', cols['name'], rng)
    return cols


def _build_tracks(schema, rng, n: int, albums: dict, media_types: dict, genres: dict) -> dict:
    start = _pk_start(schema, 'tracks')
    cols = {c.name: [] for c in schema.tables['tracks'].columns}
    cols['id'] = list(range(start, start + n))
    names = ['For Those About To Rock (We Salute You)', 'Balls to the Wall', 'Fast As a Shark',
             'Restless and Wild', 'Princess of the Dawn', 'Put The Finger On You', 'Let\'s Get It Up',
             'Inject The Venom']
    cols['name'] = [names[i % len(names)] for i in range(n)]
    album_ids = albums.get('id') or []
    cols['album_id'] = [rng.choice(album_ids) if album_ids else None for _ in range(n)]
    mt_ids = media_types.get('id') or []
    cols['media_type_id'] = [rng.choice(mt_ids) if mt_ids else None for _ in range(n)]
    genre_ids = genres.get('id') or []
    cols['genre_id'] = [rng.choice(genre_ids) if genre_ids else None for _ in range(n)]
    composers = ['Angus Young, Malcolm Young, Brian Johnson', 'F. Baltes, S. Kaufman, U. Dirkscneider',
                 'AC/DC', 'Steven Tyler, Joe Perry', 'Deaffy & R.A. Smith-Diesel']
    cols['composer'] = [composers[i % len(composers)] for i in range(n)]
    cols['milliseconds'] = [rng.randint(*TRACK_MS) for _ in range(n)]
    cols['bytes'] = [rng.randint(*TRACK_BYTES) for _ in range(n)]
    cols['unit_price'] = [rng.choice(ENUMS[('tracks', 'unit_price')]) for _ in range(n)]
    for c in ('album_id', 'genre_id', 'composer', 'bytes'):
        cols[c] = _plant_nulls(schema, 'tracks', c, cols[c], rng)
    cols['composer'] = _plant_duplicates('tracks', 'composer', cols['composer'], rng)
    return cols


def _build_invoices(schema, rng, n: int, customers: dict) -> dict:
    start = _pk_start(schema, 'invoices')
    cols = {c.name: [] for c in schema.tables['invoices'].columns}
    cols['id'] = list(range(start, start + n))
    cust_ids = customers.get('id') or []
    cols['customer_id'] = [rng.choice(cust_ids) if cust_ids else None for _ in range(n)]
    base = dt.datetime(2007, 1, 1)
    cols['invoice_date'] = [(base + dt.timedelta(days=i)).strftime(_TS) for i in range(n)]
    cust_by_id = {}
    if cust_ids:
        for j, cid in enumerate(cust_ids):
            cust_by_id[cid] = {c: customers[c][j] for c in customers if c != 'id'}
    for child_col, (pt, pc) in COPIED.items():
        if child_col[0] != 'invoices':
            continue
        vals = []
        for cid in cols['customer_id']:
            row = cust_by_id.get(cid)
            vals.append(row.get(pc) if row else None)
        cols[child_col[1]] = vals
    cols['total'] = [0.0] * n
    for c in ('billing_state', 'billing_postal_code'):
        if (('invoices', c) in NULL_TARGETS) and all(v is not None for v in cols[c]):
            cols[c] = _plant_nulls(schema, 'invoices', c, cols[c], rng)
    cols['billing_state'] = _plant_boundary('invoices', 'billing_state', cols['billing_state'], rng)
    cols['billing_city'] = _plant_boundary('invoices', 'billing_city', cols['billing_city'], rng)
    cols['billing_country'] = _plant_group_sizes('invoices', 'billing_country', cols['billing_country'], rng)
    return cols


def _build_invoice_lines(schema, rng, n: int, invoices: dict, tracks: dict) -> dict:
    start = _pk_start(schema, 'invoice_lines')
    cols = {c.name: [] for c in schema.tables['invoice_lines'].columns}
    cols['id'] = list(range(start, start + n))
    inv_ids = invoices.get('id') or []
    cols['invoice_id'] = [rng.choice(inv_ids) if inv_ids else None for _ in range(n)]
    track_ids = tracks.get('id') or []
    cols['track_id'] = [rng.choice(track_ids) if track_ids else None for _ in range(n)]
    track_price = {}
    if track_ids:
        for j, tid in enumerate(track_ids):
            track_price[tid] = tracks['unit_price'][j]
    cols['unit_price'] = [track_price.get(tid, 0.99) for tid in cols['track_id']]
    cols['quantity'] = [QUANTITY] * n
    return cols


def _build_playlists(schema, rng, n: int) -> dict:
    start = _pk_start(schema, 'playlists')
    cols = {c.name: [] for c in schema.tables['playlists'].columns}
    cols['id'] = list(range(start, start + n))
    names = ['Music', 'Movies', 'TV Shows', 'Audiobooks', '90’s Music', 'Music Videos',
             'Brazilian Music', 'Classical']
    cols['name'] = [names[i % len(names)] for i in range(n)]
    cols['name'] = _plant_nulls(schema, 'playlists', 'name', cols['name'], rng)
    cols['name'] = _plant_group_sizes('playlists', 'name', cols['name'], rng)
    return cols


def _build_playlist_tracks(schema, rng, n: int, playlists: dict, tracks: dict) -> dict:
    cols = {c.name: [] for c in schema.tables['playlist_tracks'].columns}
    pl_ids = playlists.get('id') or []
    tr_ids = tracks.get('id') or []
    seen = set()
    attempts = 0
    max_attempts = max(n * 20, 1000)
    while len(cols['playlist_id']) < n and attempts < max_attempts:
        attempts += 1
        if not pl_ids or not tr_ids:
            break
        pid = rng.choice(pl_ids)
        tid = rng.choice(tr_ids)
        if (pid, tid) in seen:
            continue
        seen.add((pid, tid))
        cols['playlist_id'].append(pid)
        cols['track_id'].append(tid)
    if len(cols['playlist_id']) < n and pl_ids and tr_ids:
        for pid in pl_ids:
            for tid in tr_ids:
                if len(cols['playlist_id']) >= n:
                    break
                if (pid, tid) in seen:
                    continue
                seen.add((pid, tid))
                cols['playlist_id'].append(pid)
                cols['track_id'].append(tid)
            if len(cols['playlist_id']) >= n:
                break
    return cols


def _compute_invoice_totals(instance: dict) -> None:
    """invoices.total = SUM(invoice_lines.unit_price * invoice_lines.quantity) GROUP BY invoice_id."""
    inv = instance.get('invoices')
    lines = instance.get('invoice_lines')
    if not inv or not lines or not inv.get('id'):
        return
    totals = {iid: 0.0 for iid in inv['id']}
    for iid, up, q in zip(lines.get('invoice_id', []), lines.get('unit_price', []),
                          lines.get('quantity', [])):
        if iid is None or up is None or q is None:
            continue
        if iid in totals:
            totals[iid] += float(up) * int(q)
    inv['total'] = [round(totals.get(iid, 0.0), 2) for iid in inv['id']]


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification rules by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    _plant_aggregate_boundary(inst, schema, rng)
    _plant_unmatched(inst, schema, rng)
    _plant_order_ties(inst, rng)
    _compute_invoice_totals(inst)
    return {t: inst[t] for t in schema.tables}
