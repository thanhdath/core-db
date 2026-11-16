"""Generation specification, encoded as data (no SQL evaluation anywhere)."""

ENUMS = {
    ('regions', 'REGION_ID'): [1, 2, 3, 4],
    ('regions', 'REGION_NAME'): ['Europe', 'Americas', 'Asia', 'Middle East and Africa'],
    ('countries', 'COUNTRY_ID'): ['AR', 'AU', 'BE', 'BR', 'CA', 'CH', 'CN', 'DE', 'IT', 'JP', 'US', 'IN',
                                  'SG', 'FR', 'GB', 'ES', 'MX', 'NL', 'SE', 'NO', 'PL', 'PT', 'ZA', 'EG', 'TR'],
    ('countries', 'REGION_ID'): [1, 2, 3, 4],
}

BOUNDARY_NUM = {
    ('departments', 'DEPARTMENT_ID'): [39, 40, 41, 69, 70, 71, 89, 90, 91],
    ('jobs', 'MAX_SALARY'): [11998, 11999, 12000, 17999, 18000, 18001],
    ('employees', 'DEPARTMENT_ID'): [39, 40, 41, 69, 70, 71],
    ('employees', 'SALARY'): [7999, 8000, 8001, 11999, 12000, 12001],
}
BOUNDARY_DATE = {
    ('employees', 'HIRE_DATE'): ['2002-06-20', '2002-06-21', '2002-06-22'],
}
NEAR_TEXT = {
    ('employees', 'FIRST_NAME'): ['Payam', 'payam', 'Clara', 'clara'],
    ('locations', 'CITY'): ['London', 'london'],
}
TIE_ORDER = {('locations', 'STATE_PROVINCE'): 'ASC'}
DUP_DISTINCT = {
    ('jobs', 'JOB_TITLE'): (0.20, 0.50, 'title'),
    ('employees', 'LAST_NAME'): (0.20, 0.50, 'name'),
    ('employees', 'PHONE_NUMBER'): (0.20, 0.50, 'phone'),
}

GROUP_SIZES = {
    ('departments', 'DEPARTMENT_NAME'): [1, 2, 3],
}
JOB_HISTORY_GROUP_SIZES = [1, 2, 3]
UNMATCHED_PARENT = {'departments', 'jobs', 'employees'}
NULL_FK_CHILD = {('employees', 'DEPARTMENT_ID')}

NULL_SHARE = {('employees', 'MANAGER_ID'): (0.05, 0.30)}
DEFAULT_NULL_SHARE = (0.05, 0.20)

TABLE_META: dict = {}
RESERVED_UNMATCHED: dict = {}

def _f_regions_region_id(v):
    return v in (1, 2, 3, 4)


def _f_countries_region_id(v):
    return v in (1, 2, 3, 4)


def _f_departments_department_id(v):
    return v is None or v > 0


def _f_jobs_min_salary(v):
    return v is None or v >= 0


def _f_jobs_max_salary(v, row):
    mn = row.get('MIN_SALARY')
    return v is None or mn is None or v >= mn


def _f_employees_salary(v):
    return v is None or v >= 0


def _f_employees_commission(v):
    return v is None or 0 <= v <= 1


def _f_employees_hire_date(v):
    return v is None or ('1980-01-01' <= v <= '2010-12-31')


def _f_job_history_end_date(v, row):
    s = row.get('START_DATE')
    return v is None or s is None or v >= s


def _f_job_history_start_date(v):
    return v is None or ('1980-01-01' <= v <= '2010-12-31')


def _f_locations_location_id(v):
    return v is None or v > 0


FORMULAS = {
    ('regions', 'REGION_ID'): _f_regions_region_id,
    ('countries', 'REGION_ID'): _f_countries_region_id,
    ('departments', 'DEPARTMENT_ID'): _f_departments_department_id,
    ('jobs', 'MIN_SALARY'): _f_jobs_min_salary,
    ('jobs', 'MAX_SALARY'): _f_jobs_max_salary,
    ('employees', 'SALARY'): _f_employees_salary,
    ('employees', 'COMMISSION_PCT'): _f_employees_commission,
    ('employees', 'HIRE_DATE'): _f_employees_hire_date,
    ('job_history', 'END_DATE'): _f_job_history_end_date,
    ('job_history', 'START_DATE'): _f_job_history_start_date,
    ('locations', 'LOCATION_ID'): _f_locations_location_id,
}

TABLE_SIZES = {'regions': 4, 'countries': 25, 'locations': 23, 'jobs': 19,
               'departments': 27, 'employees': 107, 'job_history': 11}
