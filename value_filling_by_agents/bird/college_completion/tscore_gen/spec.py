"""The generation specification, encoded as data (no SQL is ever evaluated)."""
import re

LEVELS = ['2-year', '4-year']
CONTROLS = ['Public', 'Private not-for-profit', 'Private for-profit']
RACES = ['A', 'Ai', 'B', 'H', 'W', 'X']
GENDERS = ['B', 'F', 'M']
COHORTS = ['2y all', '4y bach', '4y other']
FLAGS = ['X', None]

STATES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware',
    'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
    'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
    'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico',
    'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania',
    'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont',
    'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
    'Puerto Rico',
]
STATE_ABBR = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS',
    'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY',
    'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY', 'DC', 'PR',
]
STATE_POST = STATE_ABBR

BOUNDARY = {
    ('institution_details', 'chronname'): [
        'Harvard University', 'harvard university', 'Brown University', 'brown university',
        'Columbia University', 'columbia university'],
    ('institution_details', 'state'): [
        'Connecticut', 'connecticut', 'Utah', 'utah', 'Pennsylvania', 'pennsylvania'],
    ('institution_grads', 'gender'): ['M', 'm', 'F', 'f', 'B', 'b'],
    ('institution_grads', 'year'): [2010, 2011, 2012, 2013],
    ('state_sector_details', 'schools_count'): [19, 20, 21],
    ('state_sector_grads', 'race'): ['Ai', 'ai', 'B', 'b', 'A', 'a'],
    ('state_sector_grads', 'state_abbr'): ['PA', 'pa', 'UT', 'ut', 'NJ', 'nj'],
    ('institution_grads', 'grad_100'): ['99', '100', '101'],
    ('institution_grads', 'grad_150'): ['19', '20', '21'],
    ('institution_grads', 'race'): ['H', 'h', 'Ai', 'ai', 'W', 'w'],
    ('state_sector_details', 'control'): ['Public', 'public'],
    ('state_sector_grads', 'year'): [2006, 2007, 2008, 2010, 2011, 2012],
    ('institution_details', 'level'): ['4-year', '4-YEAR'],
    ('institution_details', 'student_count'): [499, 500, 501, 999, 1000, 1001],
    ('institution_grads', 'cohort'): ['2y all', '2Y ALL'],
    ('state_sector_details', 'state_appr_value'): ['', 'x'],
}

RULES = {
    ('institution_details', 'unitid'): ('min', 1),
    ('institution_details', 'level'): ('enum', LEVELS),
    ('institution_details', 'control'): ('enum', CONTROLS),
    ('institution_details', 'hbcu'): ('flag',),
    ('institution_details', 'flagship'): ('flag',),
    ('institution_details', 'student_count'): ('min', 0),
    ('institution_details', 'ft_pct'): ('range', 0.0, 100.0),
    ('institution_details', 'exp_award_percentile'): ('range', 0, 100),
    ('institution_details', 'fte_percentile'): ('range', 0, 100),
    ('institution_details', 'aid_percentile'): ('range', 0, 100),
    ('institution_details', 'grad_100_value'): ('range', 0.0, 100.0),
    ('institution_details', 'grad_100_percentile'): ('range', 0, 100),
    ('institution_details', 'grad_150_value'): ('range', 0.0, 100.0),
    ('institution_details', 'grad_150_percentile'): ('range', 0, 100),
    ('institution_details', 'pell_value'): ('range', 0.0, 100.0),
    ('institution_details', 'pell_percentile'): ('range', 0, 100),
    ('institution_details', 'retain_value'): ('range', 0.0, 100.0),
    ('institution_details', 'retain_percentile'): ('range', 0, 100),
    ('institution_details', 'ft_fac_value'): ('range', 0.0, 100.0),
    ('institution_details', 'ft_fac_percentile'): ('range', 0, 100),
    ('institution_details', 'cohort_size'): ('min', 0),
    ('institution_grads', 'year'): ('range', 2002, 2013),
    ('institution_grads', 'gender'): ('enum', GENDERS),
    ('institution_grads', 'race'): ('enum', RACES),
    ('institution_grads', 'cohort'): ('enum', COHORTS),
    ('institution_grads', 'grad_100_rate'): ('range', 0.0, 100.0),
    ('institution_grads', 'grad_150_rate'): ('range', 0.0, 100.0),
    ('state_sector_details', 'level'): ('enum', LEVELS),
    ('state_sector_details', 'control'): ('enum', CONTROLS),
    ('state_sector_details', 'schools_count'): ('min', 0),
    ('state_sector_grads', 'year'): ('range', 2002, 2013),
    ('state_sector_grads', 'gender'): ('enum', GENDERS),
    ('state_sector_grads', 'race'): ('enum', RACES),
    ('state_sector_grads', 'cohort'): ('enum', COHORTS),
    ('state_sector_grads', 'grad_100_rate'): ('range', 0.0, 100.0),
    ('state_sector_grads', 'grad_150_rate'): ('range', 0.0, 100.0),
    ('state_sector_grads', 'grad_cohort_ct'): ('min', 0),
}

KIND = {
    ('institution_details', 'unitid'): 'int_pk',
    ('institution_details', 'chronname'): 'name',
    ('institution_details', 'city'): 'name',
    ('institution_details', 'state'): 'state',
    ('institution_details', 'level'): 'level',
    ('institution_details', 'control'): 'control',
    ('institution_details', 'basic'): 'name',
    ('institution_details', 'hbcu'): 'flag',
    ('institution_details', 'flagship'): 'flag',
    ('institution_details', 'long_x'): 'coord_x',
    ('institution_details', 'lat_y'): 'coord_y',
    ('institution_details', 'site'): 'url',
    ('institution_details', 'student_count'): 'quantity',
    ('institution_details', 'awards_per_value'): 'rate',
    ('institution_details', 'awards_per_state_value'): 'rate',
    ('institution_details', 'awards_per_natl_value'): 'rate',
    ('institution_details', 'exp_award_value'): 'quantity',
    ('institution_details', 'exp_award_state_value'): 'quantity',
    ('institution_details', 'exp_award_natl_value'): 'quantity',
    ('institution_details', 'exp_award_percentile'): 'percentile',
    ('institution_details', 'ft_pct'): 'rate',
    ('institution_details', 'fte_value'): 'quantity',
    ('institution_details', 'fte_percentile'): 'percentile',
    ('institution_details', 'med_sat_value'): 'numeric',
    ('institution_details', 'med_sat_percentile'): 'numeric',
    ('institution_details', 'aid_value'): 'quantity',
    ('institution_details', 'aid_percentile'): 'percentile',
    ('institution_details', 'endow_value'): 'numeric',
    ('institution_details', 'endow_percentile'): 'numeric',
    ('institution_details', 'grad_100_value'): 'rate',
    ('institution_details', 'grad_100_percentile'): 'percentile',
    ('institution_details', 'grad_150_value'): 'rate',
    ('institution_details', 'grad_150_percentile'): 'percentile',
    ('institution_details', 'pell_value'): 'rate',
    ('institution_details', 'pell_percentile'): 'percentile',
    ('institution_details', 'retain_value'): 'rate',
    ('institution_details', 'retain_percentile'): 'percentile',
    ('institution_details', 'ft_fac_value'): 'rate',
    ('institution_details', 'ft_fac_percentile'): 'percentile',
    ('institution_details', 'vsa_year'): 'year',
    ('institution_details', 'vsa_grad_after4_first'): 'numeric',
    ('institution_details', 'vsa_grad_elsewhere_after4_first'): 'numeric',
    ('institution_details', 'vsa_enroll_after4_first'): 'numeric',
    ('institution_details', 'vsa_enroll_elsewhere_after4_first'): 'numeric',
    ('institution_details', 'vsa_grad_after6_first'): 'numeric',
    ('institution_details', 'vsa_grad_elsewhere_after6_first'): 'numeric',
    ('institution_details', 'vsa_enroll_after6_first'): 'numeric',
    ('institution_details', 'vsa_enroll_elsewhere_after6_first'): 'numeric',
    ('institution_details', 'vsa_grad_after4_transfer'): 'numeric',
    ('institution_details', 'vsa_grad_elsewhere_after4_transfer'): 'numeric',
    ('institution_details', 'vsa_enroll_after4_transfer'): 'numeric',
    ('institution_details', 'vsa_enroll_elsewhere_after4_transfer'): 'numeric',
    ('institution_details', 'vsa_grad_after6_transfer'): 'numeric',
    ('institution_details', 'vsa_grad_elsewhere_after6_transfer'): 'numeric',
    ('institution_details', 'vsa_enroll_after6_transfer'): 'numeric',
    ('institution_details', 'vsa_enroll_elsewhere_after6_transfer'): 'numeric',
    ('institution_details', 'similar'): 'pipe',
    ('institution_details', 'state_sector_ct'): 'count',
    ('institution_details', 'carnegie_ct'): 'count',
    ('institution_details', 'counted_pct'): 'numeric',
    ('institution_details', 'nicknames'): 'short',
    ('institution_details', 'cohort_size'): 'quantity',
    ('institution_grads', 'unitid'): 'int_fk',
    ('institution_grads', 'year'): 'year',
    ('institution_grads', 'gender'): 'gender',
    ('institution_grads', 'race'): 'race',
    ('institution_grads', 'cohort'): 'cohort',
    ('institution_grads', 'grad_cohort'): 'grad_cohort',
    ('institution_grads', 'grad_100'): 'grad_count',
    ('institution_grads', 'grad_150'): 'grad_count',
    ('institution_grads', 'grad_100_rate'): 'grad_rate',
    ('institution_grads', 'grad_150_rate'): 'grad_rate',
    ('state_sector_details', 'stateid'): 'int_pk',
    ('state_sector_details', 'state'): 'state',
    ('state_sector_details', 'state_post'): 'state_post',
    ('state_sector_details', 'level'): 'level',
    ('state_sector_details', 'control'): 'control',
    ('state_sector_details', 'schools_count'): 'count',
    ('state_sector_details', 'counted_pct'): 'numeric',
    ('state_sector_details', 'awards_per_state_value'): 'numeric',
    ('state_sector_details', 'awards_per_natl_value'): 'rate',
    ('state_sector_details', 'exp_award_state_value'): 'numeric',
    ('state_sector_details', 'exp_award_natl_value'): 'quantity',
    ('state_sector_details', 'state_appr_value'): 'empty_or_x',
    ('state_sector_details', 'state_appr_rank'): 'rank',
    ('state_sector_details', 'grad_rate_rank'): 'rank',
    ('state_sector_details', 'awards_per_rank'): 'rank',
    ('state_sector_grads', 'stateid'): 'int_fk',
    ('state_sector_grads', 'state'): 'state',
    ('state_sector_grads', 'state_abbr'): 'state_abbr',
    ('state_sector_grads', 'control'): 'control',
    ('state_sector_grads', 'level'): 'level',
    ('state_sector_grads', 'year'): 'year',
    ('state_sector_grads', 'gender'): 'gender',
    ('state_sector_grads', 'race'): 'race',
    ('state_sector_grads', 'cohort'): 'cohort',
    ('state_sector_grads', 'grad_cohort'): 'grad_cohort',
    ('state_sector_grads', 'grad_100'): 'grad_count',
    ('state_sector_grads', 'grad_150'): 'grad_count',
    ('state_sector_grads', 'grad_100_rate'): 'grad_rate',
    ('state_sector_grads', 'grad_150_rate'): 'grad_rate',
    ('state_sector_grads', 'grad_cohort_ct'): 'count',
}

NULL_SHARE = {
    ('institution_details', 'chronname'): 0.01,
    ('institution_details', 'state'): 0.01,
    ('institution_details', 'site'): 0.005,
    ('institution_details', 'med_sat_value'): 0.01,
    ('institution_details', 'med_sat_percentile'): 0.01,
    ('institution_details', 'endow_value'): 0.01,
    ('institution_details', 'endow_percentile'): 0.01,
    ('institution_details', 'grad_100_value'): 0.087,
    ('institution_details', 'grad_100_percentile'): 0.087,
    ('institution_details', 'grad_150_value'): 0.087,
    ('institution_details', 'grad_150_percentile'): 0.087,
    ('institution_details', 'retain_value'): 0.069,
    ('institution_details', 'retain_percentile'): 0.069,
    ('institution_details', 'ft_fac_value'): 0.003,
    ('institution_details', 'ft_fac_percentile'): 0.003,
    ('institution_details', 'vsa_year'): 0.003,
    ('institution_details', 'cohort_size'): 0.087,
    ('institution_details', 'lat_y'): 0.01,
    ('institution_grads', 'unitid'): 0.01,
    ('institution_grads', 'grad_100'): 0.01,
    ('institution_grads', 'grad_150'): 0.01,
    ('institution_grads', 'grad_100_rate'): 0.01,
    ('institution_grads', 'grad_150_rate'): 0.01,
    ('institution_grads', 'cohort'): 0.01,
    ('state_sector_details', 'state'): 0.01,
    ('state_sector_details', 'counted_pct'): 0.01,
    ('state_sector_details', 'awards_per_state_value'): 0.01,
    ('state_sector_details', 'exp_award_state_value'): 0.01,
    ('state_sector_details', 'state_appr_value'): 0.01,
    ('state_sector_details', 'state_appr_rank'): 0.01,
    ('state_sector_grads', 'stateid'): 0.01,
    ('state_sector_grads', 'grad_100_rate'): 0.01,
    ('state_sector_grads', 'grad_150_rate'): 0.01,
    ('state_sector_grads', 'race'): 0.01,
}

COPY_RULES = {
    ('state_sector_grads', 'stateid'): ('state_sector_details', 'stateid', ['state', 'state_abbr']),
}

DUP_COLUMNS = {
    ('institution_details', 'chronname'),
    ('institution_details', 'site'),
    ('institution_details', 'city'),
}
TIE_COLUMNS = {
    ('institution_details', 'chronname'),
    ('institution_details', 'state'),
    ('state_sector_details', 'schools_count'),
    ('state_sector_details', 'state_appr_value'),
    ('state_sector_grads', 'grad_cohort'),
    ('institution_grads', 'unitid'),
}
DIFF_COLUMNS = {
    ('institution_grads', 'grad_100'),
    ('institution_grads', 'grad_150'),
    ('institution_details', 'lat_y'),
    ('institution_details', 'retain_percentile'),
    ('institution_details', 'student_count'),
    ('state_sector_details', 'schools_count'),
}
GROUP_SIZE_COLUMNS = {
    ('state_sector_grads', 'grad_cohort'),
}

TABLE_SIZES = {
    'institution_details': 230,
    'institution_grads': 230,
    'state_sector_details': 230,
    'state_sector_grads': 230,
}

def boundary_values(table: str, column: str) -> list:
    return BOUNDARY.get((table, column), [])


def rule_for(table: str, column: str):
    return RULES.get((table, column))


def kind_for(table: str, column: str) -> str:
    return KIND.get((table, column), 'short')


def null_share(table: str, column: str) -> float:
    return NULL_SHARE.get((table, column), 0.0)


def copy_rule_for(table: str, column: str):
    return COPY_RULES.get((table, column))


def is_dup_column(table: str, column: str) -> bool:
    return (table, column) in DUP_COLUMNS


def is_tie_column(table: str, column: str) -> bool:
    return (table, column) in TIE_COLUMNS


def is_diff_column(table: str, column: str) -> bool:
    return (table, column) in DIFF_COLUMNS


def is_group_size_column(table: str, column: str) -> bool:
    return (table, column) in GROUP_SIZE_COLUMNS


def table_size(table: str) -> int:
    return TABLE_SIZES.get(table, 230)


def case_variant(rng, value: str) -> str:
    """Return a case variant of a string (upper / lower / title / as-is)."""
    if not isinstance(value, str) or not value:
        return value
    u = rng.random()
    if u < 0.25:
        return value.upper()
    if u < 0.5:
        return value.lower()
    if u < 0.75:
        return value.title()
    return value


def like_pattern(value: str) -> str:
    """A LIKE pattern without '%' that still matches value (prefix)."""
    if not isinstance(value, str) or not value:
        return value
    return value[:max(1, len(value) // 2)]


_NUM_RE = re.compile(r'^-?\d+(?:\.\d+)?$')


def is_numeric_string(v) -> bool:
    return isinstance(v, str) and bool(_NUM_RE.match(v.strip()))


def enum_accepts(rule, v) -> bool:
    """True if v is an enum member or a case variant of one (boundary targets must survive)."""
    if rule is None or rule[0] != 'enum':
        return True
    if v in rule[1]:
        return True
    if isinstance(v, str):
        low = v.lower()
        return any(isinstance(m, str) and m.lower() == low for m in rule[1])
    return False
