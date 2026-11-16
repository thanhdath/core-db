"""Specification-driven construction: value pools, NULL rates, derived rules, table sizes."""
import datetime as dt
import re

SIZES = {
    'Artist': 40, 'Album': 60, 'Genre': 12, 'MediaType': 5, 'Playlist': 8, 'Employee': 8,
    'Customer': 30, 'Track': 120, 'Invoice': 60, 'InvoiceLine': 200, 'PlaylistTrack': 150,
}

ENUM_POOLS = {
    ('Track', 'UnitPrice'): ['0.99', '1.99'],
    ('InvoiceLine', 'UnitPrice'): ['0.99', '1.99'],
    ('Genre', 'Name'): ['Rock', 'Pop', 'Jazz', 'Metal', 'Alternative & Punk', 'Rock And Roll',
                        'Blues', 'Latin', 'Reggae', 'Classical', 'Pop', 'Rock', 'Rock'],
    ('MediaType', 'Name'): ['MPEG audio file', 'Protected AAC audio file', 'Protected MPEG-4 video file',
                            'Purchased AAC audio file', 'AAC audio file'],
    ('Playlist', 'Name'): ['Music', 'Movies', 'TV Shows', 'Audiobooks', '90s Music', 'Music Videos',
                           'Brazilian Music', 'Classical'],
    ('Employee', 'Title'): ['General Manager', 'Sales Manager', 'Sales Support Agent', 'IT Manager',
                            'IT Staff'],
    ('Employee', 'City'): ['Edmonton', 'Calgary', 'Lethbridge'],
    ('Employee', 'Country'): ['Canada'],
    ('Employee', 'State'): ['AB'],
    ('Customer', 'Country'): ['Brazil', 'Germany', 'Canada', 'Norway', 'Czech Republic', 'Austria',
                              'Belgium', 'Denmark', 'Germany', 'USA', 'France', 'Germany'],
    ('Customer', 'City'): ['Sao Jose dos Campos', 'Stuttgart', 'Montreal', 'Oslo', 'Prague', 'Vienna',
                           'Brussels', 'Copenhagen', 'Berlin', 'Paris'],
    ('Customer', 'State'): ['SP', 'QC', 'RJ', 'DF', 'AB', 'BC', 'CA', 'WA'],
    ('Customer', 'Company'): ['Embraer - Empresa Brasileira de Aeronautica S.A.', 'JetBrains s.r.o.',
                              'Woodstock Discos', 'Banco do Brasil S.A.', 'Riotur', 'Telus',
                              'Rogers Canada', 'Google Inc.'],
    ('Invoice', 'BillingCountry'): ['Germany', 'Norway', 'Belgium', 'Canada', 'USA', 'France',
                                    'Ireland', 'United Kingdom', 'Brazil', 'Brazil'],
    ('Invoice', 'BillingCity'): ['Stuttgart', 'Oslo', 'Brussels', 'Edmonton', 'Boston', 'Frankfurt',
                                 'Berlin', 'Paris'],
    ('Invoice', 'BillingState'): ['AB', 'MA', 'QC', 'CA', 'WA', 'NV', 'WI', 'NS'],
    ('Invoice', 'BillingPostalCode'): ['70174', '0171', '1000', 'T6G 2C7', '2113', '60316', '10779',
                                       '75002'],
    ('Customer', 'PostalCode'): ['70173', '70174', '70175', '12227-000', '0171', 'H2G 1A7',
                                 '14700', '14300', '1010', '1000'],
    ('Customer', 'Email'): ['luisg@embraer.com.br', 'leonekohler@surfeu.de', 'ftremblay@gmail.com',
                            'bjorn.hansen@yahoo.no', 'frantisekw@jetbrains.com', 'hholy@gmail.com',
                            'astrid.gruber@apple.at', 'daan_peeters@apple.be',
                            'test@gmail.com', 'user@gmail.com', 'x@gmail.com', 'x@gmail.com',
                            'GMAIL.COM', 'gmail.con'],
    ('Artist', 'Name'): ['AC/DC', 'Accept', 'Aerosmith', 'Alanis Morissette', 'Alice In Chains',
                         'Antonio Carlos Jobim', 'Apocalyptica', 'Audioslave', 'AC/DC', 'Accept'],
    ('Album', 'Title'): ['For Those About To Rock We Salute You', 'Balls to the Wall',
                         'Restless and Wild', 'Let There Be Rock', 'Big Ones', 'Jagged Little Pill',
                         'Facelift', 'Warner 25 Anos', 'For Those About To Rock We Salute You',
                         'Balls to the Wall'],
    ('Track', 'Name'): ['For Those About To Rock (We Salute You)', 'Balls to the Wall',
                        'Fast As a Shark', 'Restless and Wild', 'Princess of the Dawn',
                        'Put The Finger On You', "Let's Get It Up", 'Inject The Venom',
                        'Balls to the Wall', 'For Those About To Rock (We Salute You)'],
    ('Customer', 'FirstName'): ['Luis', 'Leonie', 'Francois', 'Bjorn', 'Frantisek', 'Helena',
                                'Astrid', 'Daan', 'Maria', 'John'],
    ('Customer', 'LastName'): ['Goncalves', 'Kohler', 'Tremblay', 'Hansen', 'Wichterlova', 'Holy',
                               'Gruber', 'Peeters', 'Goncalves', 'Kohler'],
    ('Customer', 'Address'): ['Av. Brigadeiro Faria Lima, 2170', 'Theodor-Heuss-Strasse 34',
                                '1498 rue Belanger', 'Ullevalsveien 14', 'Klanova 9/506',
                                'Rilska 3174/6', 'Rotenturmstrasse 4, 1010 Innere Stadt',
                                'Gretrystraat 63', 'Theodor-Heuss-Strasse 34'],
    ('Customer', 'Phone'): ['+55 (12) 3923-5555', '+49 0711 2842222', '+1 (514) 721-4711',
                            '+47 22 44 22 22', '+420 2 4172 5555', '+420 2 4177 0449',
                            '+43 01 5134505', '+32 02 219 03 03'],
    ('Customer', 'Fax'): ['+55 (12) 3923-5566', '+420 2 4172 5555', '+55 (11) 3033-4564',
                          '+55 (11) 3055-8131', '+55 (21) 2271-7070', '+55 (61) 3363-7855',
                          '+1 (780) 434-5565', '+1 (604) 688-8756'],
    ('Employee', 'LastName'): ['Adams', 'Edwards', 'Peacock', 'Park', 'Johnson', 'Mitchell',
                               'King', 'Callahan'],
    ('Employee', 'FirstName'): ['Andrew', 'Nancy', 'Jane', 'Margaret', 'Steve', 'Michael', 'Robert',
                                'Laura'],
    ('Employee', 'Address'): ['11120 Jasper Ave NW', '825 8 Ave SW', '1111 6 Ave SW',
                              '683 10 Street SW', '7727B 41 Ave', '5827 Bowness Road NW',
                              '590 Columbia Boulevard West', '923 7 ST NW'],
    ('Employee', 'PostalCode'): ['T5K 2N1', 'T2P 2T3', 'T2P 5M5', 'T2P 5G3', 'T3B 1Y7', 'T3B 0C5',
                                 'T1K 5N8', 'T1H 1Y8'],
    ('Employee', 'Phone'): ['+1 (780) 428-9482', '+1 (403) 262-3443', '+1 (403) 262-4423',
                            '1 (780) 836-9987', '+1 (403) 246-9887', '+1 (403) 456-9986',
                            '+1 (403) 467-3351'],
    ('Employee', 'Fax'): ['+1 (780) 428-3457', '+1 (403) 262-3322', '+1 (403) 262-6712',
                          '+1 (403) 263-4289', '1 (780) 836-9543', '+1 (403) 246-9899',
                          '+1 (403) 456-8485', '+1 (403) 467-8772'],
    ('Invoice', 'BillingAddress'): ['Theodor-Heuss-Strasse 34', 'Ullevalsveien 14',
                                  'Gretrystraat 63', '8210 111 ST NW', '69 Salem Street',
                                  'Berger Strasse 10', 'Barbarossastrasse 19', '8, Rue Hanovre'],
}

BOUNDARY_VALUES = {
    ('Customer', 'PostalCode'): ['70173', '70174', '70175'],
    ('Invoice', 'Total'): ['19.99', '20.00', '20.01'],
    ('Invoice', 'BillingCountry'): ['Brazil', 'brazil'],
    ('Customer', 'Country'): ['Germany', 'germany'],
    ('Genre', 'Name'): ['Rock', 'rock', 'ROCK', 'Reggae', 'reggae'],
    ('MediaType', 'Name'): ['AAC audio file', 'aac audio file'],
}

LIKE_VARIANTS = {
    ('Customer', 'Email'): ['%gmail.com', '%gmail.com%', 'gmail.com', 'GMAIL.COM', 'gmail.con'],
}

NULL_RATES = {
    ('Customer', 'Company'): 0.831, ('Customer', 'State'): 0.492, ('Customer', 'PostalCode'): 0.068,
    ('Customer', 'Phone'): 0.017, ('Customer', 'Fax'): 0.797, ('Customer', 'SupportRepId'): 0.0,
    ('Employee', 'ReportsTo'): 0.125, ('Employee', 'BirthDate'): 0.0, ('Employee', 'HireDate'): 0.0,
    ('Employee', 'Title'): 0.0, ('Employee', 'Address'): 0.0, ('Employee', 'City'): 0.0,
    ('Employee', 'State'): 0.0, ('Employee', 'Country'): 0.0, ('Employee', 'PostalCode'): 0.0,
    ('Employee', 'Phone'): 0.0, ('Employee', 'Fax'): 0.0, ('Employee', 'Email'): 0.0,
    ('Track', 'Composer'): 0.279, ('Track', 'Bytes'): 0.0, ('Track', 'AlbumId'): 0.0,
    ('Track', 'GenreId'): 0.0,
    ('Invoice', 'BillingState'): 0.49, ('Invoice', 'BillingPostalCode'): 0.068,
    ('Album', 'Title'): 0.0, ('Artist', 'Name'): 0.0, ('Genre', 'Name'): 0.0,
    ('MediaType', 'Name'): 0.0, ('Playlist', 'Name'): 0.0,
}

DUP_TARGETS = {
    ('Album', 'Title'): 0.2, ('Album', 'ArtistId'): 0.2, ('Artist', 'Name'): 0.2,
    ('Customer', 'Address'): 0.2, ('Customer', 'LastName'): 0.2, ('Employee', 'City'): 0.2,
    ('Invoice', 'InvoiceDate'): 0.2, ('Track', 'Name'): 0.2, ('Genre', 'Name'): 0.2,
}

GROUP_TARGETS = {
    ('Track', 'GenreId'): ('Genre', 'GenreId'), ('Artist', 'ArtistId'): ('Artist', 'ArtistId'),
    ('Artist', 'Name'): ('Artist', 'Name'), ('Album', 'AlbumId'): ('Album', 'AlbumId'),
    ('Track', 'AlbumId'): ('Album', 'AlbumId'), ('MediaType', 'MediaTypeId'): ('MediaType', 'MediaTypeId'),
    ('Genre', 'GenreId'): ('Genre', 'GenreId'),
}

UNMATCHED = {
    ('Customer', 'CustomerId'): 'Invoice', ('Employee', 'EmployeeId'): 'Customer',
    ('Invoice', 'CustomerId'): 'Invoice', ('Genre', 'GenreId'): 'Track',
    ('Track', 'GenreId'): 'Track', ('Artist', 'ArtistId'): 'Album',
    ('Customer', 'SupportRepId'): 'Customer',
}

COPY_DEPENDENCIES = {
    ('Invoice', 'BillingAddress'): ('Customer', 'Address'),
    ('Invoice', 'BillingCity'): ('Customer', 'City'),
    ('Invoice', 'BillingState'): ('Customer', 'State'),
    ('Invoice', 'BillingCountry'): ('Customer', 'Country'),
    ('Invoice', 'BillingPostalCode'): ('Customer', 'PostalCode'),
    ('InvoiceLine', 'UnitPrice'): ('Track', 'UnitPrice'),
}


def pool_for(table, column):
    """Return the pool for a column (explicit enum, boundary, or observed)."""
    vals = []
    for key in (ENUM_POOLS.get((table, column)), BOUNDARY_VALUES.get((table, column)),
                LIKE_VARIANTS.get((table, column))):
        if key:
            vals.extend(key)
    return vals


def null_rate(table, column):
    return NULL_RATES.get((table, column), 0.0)


def is_nullable(table, column):
    return (table, column) in NULL_RATES


def is_copied(table, column):
    """True if the column is a copied (dependent) column: NULLs are inherited, never planted."""
    return (table, column) in COPY_DEPENDENCIES


def _is_float(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _cast(v, type_str):
    if v is None:
        return None
    t = (type_str or '').lower()
    if 'int' in t:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return v
    if 'decimal' in t or 'numeric' in t or 'real' in t or 'float' in t or 'double' in t:
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return v
    return v


def _perturb(v, rng, type_str):
    """Return a perturbed value (numeric +-1, or string variant)."""
    t = (type_str or '').lower()
    if 'int' in t or 'decimal' in t or 'numeric' in t or 'real' in t or 'float' in t:
        try:
            f = float(v)
            if 'int' in t:
                return int(f + rng.choice([-2, -1, 1, 2]))
            return round(f + rng.choice([-0.01, 0.01, -0.02, 0.02]), 2)
        except (TypeError, ValueError):
            return v
    if isinstance(v, str):
        if v:
            u = rng.random()
            if u < 0.2:
                return v + rng.choice('abc')
            if u < 0.4:
                return rng.choice('abc') + v
            if u < 0.6:
                return v[:-1]
            if u < 0.8:
                return v[1:]
            return v.upper()
    return v


def _pick(pool, rng, type_str):
    """Pick a value from the pool, cast to type_str."""
    if not pool:
        return None
    return _cast(rng.choice(pool), type_str)


def _datetime_in_range(rng, lo='2009-01-01 00:00:00', hi='2009-12-31 23:59:59'):
    a = dt.datetime.strptime(lo, '%Y-%m-%d %H:%M:%S')
    b = dt.datetime.strptime(hi, '%Y-%m-%d %H:%M:%S')
    d = a + dt.timedelta(seconds=rng.randint(0, int((b - a).total_seconds())))
    return d.strftime('%Y-%m-%d %H:%M:%S')


def derive_invoice_total(line_cols: dict, invoice_ids: list) -> list:
    """Return SUM(InvoiceLine.UnitPrice * Quantity) per InvoiceId (row-aligned zip)."""
    sums: dict = {}
    iids = line_cols.get('InvoiceId', [])
    prices = line_cols.get('UnitPrice', [])
    qtys = line_cols.get('Quantity', [])
    for iid, up, q in zip(iids, prices, qtys):
        if iid is None:
            continue
        sums[iid] = sums.get(iid, 0.0) + float(up or 0) * float(q or 0)
    return [round(sums.get(iid, 0.0), 2) for iid in invoice_ids]


def derive_invoice_billing(customer_cols: dict, cust_id_to_idx: dict, invoice_customer_ids: list) -> dict:
    """Copy the customer's fields from the parent row (exact copy, NULL propagation)."""
    out = {}
    for child_col, parent_col in (('BillingAddress', 'Address'), ('BillingCity', 'City'),
                                  ('BillingState', 'State'), ('BillingCountry', 'Country'),
                                  ('BillingPostalCode', 'PostalCode')):
        pvals = customer_cols.get(parent_col, [])
        col = []
        for cid in invoice_customer_ids:
            ci = cust_id_to_idx.get(cid)
            col.append(pvals[ci] if ci is not None and ci < len(pvals) else None)
        out[child_col] = col
    return out


def derive_invoice_line_unit_price(track_cols: dict, track_id_to_idx: dict, line_track_ids: list) -> list:
    """Copy Track.UnitPrice to InvoiceLine.UnitPrice (exact copy, NULL propagation)."""
    pvals = track_cols.get('UnitPrice', [])
    out = []
    for tid in line_track_ids:
        ti = track_id_to_idx.get(tid)
        out.append(pvals[ti] if ti is not None and ti < len(pvals) else None)
    return out


def derive_employee_hire_date(birth_date, rng):
    """HireDate >= BirthDate (spec)."""
    if not birth_date:
        return _datetime_in_range(rng)
    try:
        b = dt.datetime.strptime(str(birth_date), '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return _datetime_in_range(rng)
    lo = b + dt.timedelta(days=1)
    hi = lo + dt.timedelta(days=365 * 30)
    if lo > hi:
        return _datetime_in_range(rng)
    d = lo + dt.timedelta(seconds=rng.randint(0, int((hi - lo).total_seconds())))
    return d.strftime('%Y-%m-%d %H:%M:%S')


def derive_employee_reports_to(employee_id, rng, existing_ids):
    """ReportsTo IS NULL OR ReportsTo < EmployeeId (acyclic, spec evidence)."""
    if not existing_ids:
        return None
    if rng.random() < 0.1:
        return None
    cand = [e for e in existing_ids if e is not None and e < employee_id]
    if not cand:
        return None
    return rng.choice(cand)


def derive_customer_email(email, rng):
    """Email LIKE '%@%'."""
    if email and '@' in email:
        return email
    return 'user@example.com'


def derive_customer_support_rep(support_rep, employee_ids, rng):
    """SupportRepId IS NULL OR SupportRepId IN (SELECT EmployeeId FROM Employee)."""
    if support_rep is None:
        return None
    if support_rep in employee_ids:
        return support_rep
    return rng.choice(employee_ids) if employee_ids else None


def derive_track_name(name, rng):
    """Name non-empty (NOT NULL)."""
    if name:
        return name
    return 'track_%d' % rng.randint(0, 9999)


def derive_track_milliseconds(ms, rng):
    """Milliseconds > 0 (spec range 50000..900000)."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        ms = rng.randint(50000, 900000)
    if ms <= 0:
        ms = rng.randint(50000, 900000)
    return ms


def derive_track_bytes(b, rng):
    """Bytes IS NULL OR Bytes > 0 (spec range 1000000..50000000)."""
    if b is None:
        return None
    try:
        b = int(b)
    except (TypeError, ValueError):
        b = rng.randint(1000000, 50000000)
    if b <= 0:
        b = rng.randint(1000000, 50000000)
    return b


def derive_invoice_line_quantity(q, rng):
    """Quantity > 0 (spec: Quantity=1)."""
    try:
        q = int(q)
    except (TypeError, ValueError):
        q = 1
    if q <= 0:
        q = 1
    return q


def derive_invoice_line_unit_price_nonneg(u, rng):
    """UnitPrice >= 0."""
    try:
        u = float(u)
    except (TypeError, ValueError):
        u = 0.99
    if u < 0:
        u = 0.99
    return round(u, 2)


def derive_invoice_total_nonneg(total, rng):
    """Total >= 0."""
    try:
        total = float(total)
    except (TypeError, ValueError):
        total = 0.0
    if total < 0:
        total = 0.0
    return round(total, 2)


def derive_artist_name(name, rng):
    """Artist.Name IS NULL OR length > 0."""
    if name is None:
        return None
    if not name:
        return 'artist_%d' % rng.randint(0, 9999)
    return name


def derive_genre_name(name, rng):
    """Genre.Name IS NULL OR length > 0."""
    if name is None:
        return None
    if not name:
        return 'genre_%d' % rng.randint(0, 9999)
    return name


def derive_mediatype_name(name, rng):
    """MediaType.Name IS NULL OR length > 0."""
    if name is None:
        return None
    if not name:
        return 'mediatype_%d' % rng.randint(0, 9999)
    return name


def derive_playlist_name(name, rng):
    """Playlist.Name IS NULL OR length > 0."""
    if name is None:
        return None
    if not name:
        return 'playlist_%d' % rng.randint(0, 9999)
    return name


def derive_album_title(title, rng):
    """Album.Title IS NULL OR length > 0."""
    if title is None:
        return None
    if not title:
        return 'album_%d' % rng.randint(0, 9999)
    return title
