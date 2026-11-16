"""Specification loading and the built-in (round-1) specification."""
import json

CITY_POOL = ['Los Angeles', 'Chicago', 'Washington D.C.', 'Dallas', 'Boston', 'Sydney',
             'Tokyo', 'Honolulu', 'New York', 'Seattle', 'Denver', 'Miami']
AIRCRAFT_POOL = ['Boeing 747-400', 'Boeing 737-800', 'Airbus A340-300',
                 'British Aerospace Jetstream 41', 'Embraer ERJ-145', 'SAAB 340',
                 'Piper Archer III', 'Tupolev 154', 'Airbus A320-200', 'Boeing 767-300',
                 'Boeing 777-200', 'Airbus A330-300', 'Cessna 172', 'Bombardier CRJ-200',
                 'McDonnell Douglas MD-80', 'Fokker 100']
FIRST_NAMES = ['James', 'Mary', 'John', 'Lisa', 'Larry', 'Karen', 'Lawrence', 'Michael',
               'Patricia', 'Robert', 'Linda', 'William', 'Elizabeth', 'David', 'Barbara',
               'Richard', 'Susan', 'Joseph', 'Jessica', 'Thomas', 'Sarah', 'Charles',
               'Nancy', 'Christopher', 'Betty', 'Daniel', 'Margaret', 'Matthew', 'Sandra']
LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Walker', 'West', 'Scott', 'Sperry', 'Miller',
              'Brown', 'Davis', 'Jones', 'Garcia', 'Rodriguez', 'Wilson', 'Martinez',
              'Anderson', 'Taylor', 'Thomas', 'Hernandez', 'Moore', 'Martin', 'Jackson',
              'Thompson', 'White', 'Lopez', 'Lee', 'Gonzalez', 'Harris', 'Clark', 'Lewis']


def default_specification() -> dict:
    """The round-1 specification, expressed as data for the samplers."""
    return {
        'table_sizes': {'aircraft': 16, 'employee': 31, 'flight': 10, 'certificate': 69},
        'pools': {
            'city': CITY_POOL,
            'aircraft_name': AIRCRAFT_POOL,
            'first_name': FIRST_NAMES,
            'last_name': LAST_NAMES,
        },
        'ranges': {
            'integer_quantity': [1, 10000],
            'integer_distance': [100, 9000],
            'decimal_price': [50.00, 2000.00],
            'decimal_salary': [30000.00, 300000.00],
        },
        'date_range': ['2005-01-01', '2005-12-31'],
        'date_format': '%m/%d/%Y %H:%M',
        'distinct_share': [0.20, 0.50],
        'group_sizes': [1, 2, 3],
        'null_share': 0.05,
        'per_column_exceptions': [
            {'column': 'aircraft.name', 'pattern': 'comparison_boundary',
             'targets': ['Airbus A340-300', 'airbus a340-300', 'Boeing 737-800', 'boeing 737-800']},
            {'column': 'aircraft.name', 'pattern': 'group_sizes', 'targets': ['1, 2 and >= 3']},
            {'column': 'aircraft.name', 'pattern': 'duplicates_for_distinct', 'targets': ['20-50 %']},
            {'column': 'aircraft.name', 'pattern': 'aggregate_boundary', 'targets': ['COUNT(*) values 1,2,3']},
            {'column': 'aircraft.aid', 'pattern': 'unmatched_join_rows',
             'targets': ['parent_rows_without_children', 'child_rows_with_null_fk']},
            {'column': 'flight.aid', 'pattern': 'group_sizes', 'targets': ['1, 2 and >= 3']},
            {'column': 'flight.aid', 'pattern': 'unmatched_join_rows',
             'targets': ['parent_rows_without_children', 'child_rows_with_null_fk']},
            {'column': 'flight.aid', 'pattern': 'aggregate_boundary',
             'targets': ['COUNT(*) and COUNT(flight.aid) values 1,2,3']},
            {'column': 'employee.eid', 'pattern': 'unmatched_join_rows', 'targets': ['parent_rows_without_children']},
            {'column': 'employee.eid', 'pattern': 'ties_for_order_limit', 'targets': ['tie_at_rank 1 on COUNT(*)']},
            {'column': 'certificate.aid', 'pattern': 'group_sizes', 'targets': ['1, 2 and >= 3']},
            {'column': 'certificate.aid', 'pattern': 'unmatched_join_rows', 'targets': ['parent_rows_without_children']},
            {'column': 'certificate.aid', 'pattern': 'ties_for_order_limit', 'targets': ['tie_at_rank 1']},
            {'column': 'certificate.eid', 'pattern': 'unmatched_join_rows', 'targets': ['parent_rows_without_children']},
            {'column': 'certificate.eid', 'pattern': 'ties_for_order_limit', 'targets': ['tie_at_rank 1 on COUNT(*)']},
            {'column': 'employee.salary', 'pattern': 'comparison_boundary',
             'targets': ['99999', '100000', '100001', '100002', '199999', '200000', '200001']},
            {'column': 'employee.salary', 'pattern': 'group_sizes', 'targets': ['1, 2 and >= 3']},
            {'column': 'flight.flno', 'pattern': 'duplicates_for_distinct', 'targets': ['20-50 %']},
            {'column': 'flight.price', 'pattern': 'rows_with_different_values',
             'targets': ['>= 2 per group with different values']},
            {'column': 'aircraft.distance', 'pattern': 'rows_with_different_values',
             'targets': ['>= 2 per group with different values']},
            {'column': 'employee.name', 'pattern': 'group_sizes', 'targets': ['1, 2 and >= 3']},
            {'column': 'flight.origin', 'pattern': 'duplicates_for_distinct', 'targets': ['20-50 %']},
            {'column': 'flight.destination', 'pattern': 'literal_pool', 'targets': ['Honolulu']},
            {'column': 'flight.distance', 'pattern': 'literal_pool', 'targets': ['2000']},
        ],
        'null_targets': ['flight.aid'],
        'formulas': [
            {'table': 'flight', 'column': 'distance', 'kind': 'gt', 'value': 0},
            {'table': 'flight', 'column': 'price', 'kind': 'ge', 'value': 0},
            {'table': 'flight', 'column': 'arrival_date', 'kind': 'ge_column', 'other': 'departure_date'},
            {'table': 'aircraft', 'column': 'distance', 'kind': 'gt', 'value': 0},
            {'table': 'employee', 'column': 'salary', 'kind': 'ge', 'value': 0},
        ],
    }


def load_specification(path: str) -> dict:
    """Load a specification JSON and merge it over the built-in defaults."""
    with open(path) as f:
        raw = json.load(f)
    spec = default_specification()
    if not isinstance(raw, dict):
        return spec
    for k in ('table_sizes', 'pools', 'ranges', 'null_targets'):
        if isinstance(raw.get(k), dict if k != 'null_targets' else list):
            spec[k] = raw[k]
    for k in ('date_range', 'date_format', 'distinct_share', 'group_sizes', 'null_share'):
        if k in raw:
            spec[k] = raw[k]
    if isinstance(raw.get('per_column_exceptions'), list):
        spec['per_column_exceptions'] = raw['per_column_exceptions']
    if isinstance(raw.get('formulas'), list):
        spec['formulas'] = raw['formulas']
    return spec


def exceptions_for(spec: dict, table: str, column: str) -> list:
    """All per-column exceptions whose column matches table.column (case-insensitive)."""
    key = ('%s.%s' % (table, column)).lower()
    out = []
    for e in spec.get('per_column_exceptions', []):
        if str(e.get('column', '')).lower() == key:
            out.append(e)
    return out
