"""Specification of the target database, implemented by construction."""

TABLE_SIZES = {'host': 10, 'party': 8, 'party_host': 6}

HOST_NAMES = ['Austin Daye', 'Lloyd Daniels', 'Kornel David', 'Antonio Davis',
              'Ed Davis', 'Hubert Davis', 'Carlos Delfino', 'Justin Dentmon',
              'Marcus Lee', 'Tomas Novak']
NATIONALITIES = ['United States', 'Hungary', 'Argentina']
PARTY_THEMES = ['Spring', 'Club Q-BASE', 'Hardcore Resurrection', 'Teqnology',
                'Qlubtempo', 'QrimeTime', 'In Qontrol', 'Houseqlassics']
LOCATIONS = ['Hemkade 48 Zaandam', 'Various locations',
             'Heineken Music Hall Amsterdam',
             'Hemkade 48 Zaandam, Heineken Music Hall Amsterdam', 'RAI Amsterdam']

AGE_MIN, AGE_MAX = 18, 60
AGE_BOUNDARY = [34, 35, 36, 44, 45, 46]
YEAR_MIN, YEAR_MAX = 1990, 2020
HOSTS_MIN, HOSTS_MAX = 1, 50

DUP_SHARE = 0.30

NULL_SHARE = 0.10
NOT_NULL_COLUMNS = {('party_host', 'Party_ID'), ('party_host', 'Host_ID'),
                    ('host', 'Host_ID'), ('party', 'Party_ID')}

def age_ok(v):
    return v is None or (AGE_MIN <= int(v) <= AGE_MAX)


def year_ok(v):
    return v is None or (YEAR_MIN <= int(v) <= YEAR_MAX)


def last_ge_first(first, last):
    """Last_year >= First_year, evaluated only on non-NULL operands (3-valued logic)."""
    if first is None or last is None:
        return True
    return int(last) >= int(first)


def hosts_positive(v):
    return v is None or int(v) > 0


def bool_ok(v):
    return v is None or v in (0, 1, True, False, 'T', 'F')
