"""The generation specification, encoded as data (no SQL is ever evaluated)."""
import datetime as dt

TABLE_SIZES = {'businesses': 230, 'inspections': 230, 'violations': 230}

NULL_RATE = {
    ('businesses', 'city'): 0.259,
    ('businesses', 'postal_code'): 0.035,
    ('businesses', 'latitude'): 0.429,
    ('businesses', 'longitude'): 0.429,
    ('businesses', 'phone_number'): 0.722,
    ('businesses', 'tax_code'): 0.20,
    ('businesses', 'application_date'): 0.19,
    ('businesses', 'address'): 0.05,
    ('businesses', 'owner_address'): 0.05,
    ('businesses', 'owner_city'): 0.05,
    ('businesses', 'owner_state'): 0.20,
    ('businesses', 'owner_zip'): 0.05,
    ('inspections', 'score'): 0.20,
}

INSPECTION_TYPES = ['Routine - Unscheduled', 'Reinspection/Followup',
                    'Complaint Reinspection/Followup', 'Non-inspection site visit',
                    'Complaint', 'New Construction', 'Foodborne Illness Investigation',
                    'New Ownership']
RISK_CATEGORIES = ['Low Risk', 'Moderate Risk', 'High Risk']

NAME_BOUNDARY = ['Tiramisu Kitchen', 'tiramisu kitchen',
                 'OMNI S.F. Hotel - 2nd Floor Pantry', 'omni s.f. hotel - 2nd floor pantry',
                 'Hotel - 2nd F', 'hotel - 2nd f']
INSPECTION_DATE_BOUNDARY = ['2012-12-31', '2013-01-01', '2013-12-31', '2014-01-01',
                            '2016-01-31', '2016-02-01', '2016-02-29', '2016-03-01',
                            '2016-09-26']
INSPECTION_DATE_LIKE = ['2016-02%', '2013%', '%2016%', '2016-09-26%']
VIOLATION_DATE_BOUNDARY = ['2012-12-31', '2013-01-01', '2013-12-31', '2014-01-01']
SCORE_BOUNDARY = [94, 95, 96, 99, 100, 101]
APPLICATION_DATE_BOUNDARY = ['2011-12-31', '2012-01-01', '2012-01-02',
                             '2012-12-30', '2012-12-31', '2013-01-01']
CERTIFICATE_BOUNDARY = [304976, 304977, 304978]
DESCRIPTION_BOUNDARY = ['Permit license or inspection report not posted',
                        'permit license or inspection report not posted']
TYPE_BOUNDARY = ['Routine - Unscheduled', 'routine - unscheduled']
RISK_BOUNDARY = ['Low Risk', 'low risk', 'Moderate Risk', 'moderate risk',
                 'High Risk', 'high risk']

def business_id_ok(v):
    return v is not None and v > 0


def certificate_ok(v):
    return v is not None and v > 0


def latitude_ok(v):
    return v is None or -90.0 <= v <= 90.0


def longitude_ok(v):
    return v is None or -180.0 <= v <= 180.0


def application_date_ok(v):
    return v is None or '1900-01-01' <= v <= '2016-12-31'


def score_ok(v):
    return v is None or 0 <= v <= 100


def inspection_date_ok(v):
    return v is not None and '2012-01-01' <= v <= '2016-12-31'


def violation_date_ok(v):
    return v is not None and '2012-01-01' <= v <= '2016-12-31'


def inspection_type_ok(v):
    return v is not None and str(v).lower() in {t.lower() for t in INSPECTION_TYPES}


def risk_category_ok(v):
    return v is not None and str(v).lower() in {t.lower() for t in RISK_CATEGORIES}


DATE_LO = dt.date(2012, 1, 1)
DATE_HI = dt.date(2016, 12, 31)


def random_date(rng):
    """Uniform ISO date in [2012-01-01, 2016-12-31]."""
    span = (DATE_HI - DATE_LO).days
    return (DATE_LO + dt.timedelta(days=rng.randint(0, span))).isoformat()


def date_shift(iso, days):
    """Shift an ISO date by +/- days, clamped to the allowed window."""
    d = dt.date.fromisoformat(iso) + dt.timedelta(days=days)
    if d < DATE_LO:
        d = DATE_LO
    if d > DATE_HI:
        d = DATE_HI
    return d.isoformat()
