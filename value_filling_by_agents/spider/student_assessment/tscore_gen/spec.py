"""Specification constants (tscore_gen/specification.json) implemented by construction."""

TABLE_SIZES = {
    'Addresses': 20,
    'People': 26,
    'Students': 18,
    'Courses': 20,
    'People_Addresses': 22,
    'Student_Course_Registrations': 30,
    'Student_Course_Attendance': 14,
    'Candidates': 10,
    'Candidate_Assessments': 16,
}

FORCED_VALUES = {
    ('Courses', 'course_name'): ['statistics', 'STATISTICS'],
    ('Courses', 'course_description'): ['statistics', 'STATISTICS'],
    ('Candidate_Assessments', 'qualification'): ['A', 'B', 'C', 'D'],
    ('Candidate_Assessments', 'asessment_outcome_code'): ['Pass', 'Fail'],
    ('People', 'email_address'): ['stanley.monahan@example.org'],
}

PARENT_KEY_INJECTIONS = {
    'People': {'person_id': [170, 171, 172]},
    'Courses': {'course_id': ['300', '301', '302', '303', '304', '305', '306', '307', '308', '309', '310']},
}

ENUMS = {
    ('Candidate_Assessments', 'qualification'): ['A', 'B', 'C', 'D'],
    ('Candidate_Assessments', 'asessment_outcome_code'): ['Pass', 'Fail'],
}

NOT_NULL_COLUMNS = {
    ('Students', 'student_id'),
    ('Student_Course_Attendance', 'student_id'),
    ('Student_Course_Attendance', 'course_id'),
    ('Candidate_Assessments', 'candidate_id'),
    ('Candidate_Assessments', 'qualification'),
    ('Candidate_Assessments', 'assessment_date'),
    ('Candidate_Assessments', 'asessment_outcome_code'),
    ('Student_Course_Registrations', 'student_id'),
    ('Student_Course_Registrations', 'course_id'),
    ('Student_Course_Registrations', 'registration_date'),
    ('People_Addresses', 'person_id'),
    ('People_Addresses', 'address_id'),
    ('People_Addresses', 'person_address_id'),
    ('Candidates', 'candidate_id'),
    ('Courses', 'course_id'),
    ('People', 'person_id'),
    ('Addresses', 'address_id'),
}

NULL_TARGETS = [
    ('People', 'middle_name'),
    ('People', 'cell_mobile_number'),
    ('People', 'email_address'),
    ('People', 'login_name'),
    ('People', 'password'),
    ('Addresses', 'line_2'),
    ('Addresses', 'city'),
    ('Addresses', 'zip_postcode'),
    ('Addresses', 'state_province_county'),
    ('Addresses', 'country'),
    ('People_Addresses', 'date_to'),
    ('Students', 'student_details'),
    ('Courses', 'course_name'),
    ('Courses', 'course_description'),
    ('Courses', 'other_details'),
    ('Candidates', 'candidate_details'),
]

ALL_NULL_COLUMNS = {
    ('Courses', 'other_details'),
}

COMPOSITE_FK = {
    'child_table': 'Student_Course_Attendance',
    'child_cols': ['student_id', 'course_id'],
    'parent_table': 'Student_Course_Registrations',
    'parent_cols': ['student_id', 'course_id'],
}

COERCE_FK = {
    ('Student_Course_Registrations', 'course_id'): 'int',
    ('Student_Course_Attendance', 'course_id'): 'int',
}

GROUP_SIZE_TARGET = {
    'table': 'Student_Course_Registrations',
    'column': 'course_id',
    'sizes': [1, 2, 3],
}

TIE_TARGET = {
    'table': 'Student_Course_Attendance',
    'column': 'date_of_attendance',
    'tie_on': 'date',
}

DIFFERENT_VALUES_TARGET = {
    'table': 'Candidate_Assessments',
    'group_column': 'candidate_id',
    'value_column': 'assessment_date',
    'min_per_group': 2,
}

DUPLICATE_TARGETS = [
    ('Addresses', 'city'),
    ('Student_Course_Registrations', 'student_id'),
    ('Student_Course_Attendance', 'student_id'),
    ('Student_Course_Attendance', 'course_id'),
    ('People', 'first_name'),
    ('People', 'last_name'),
]
