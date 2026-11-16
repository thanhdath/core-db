"""Specification constants: per-column exceptions, semantic rules, null targets, sizes."""

EXCEPTIONS = {
    ('publishers', 'pub_id'): [('duplicates_for_distinct', {'duplicate_share': (0.2, 0.5)})],
    ('publishers', 'pub_name'): [('ties_for_order_limit', {'tie_at_rank': [1]}),
                                 ('comparison_boundary', {'values': ['GGG&G', 'ggg&g', 'Binnet & Hardley',
                                                                     'binnet & hardley']})],
    ('publishers', 'country'): [('duplicates_for_distinct', {'duplicate_share': (0.2, 0.5)})],
    ('publishers', 'city'): [('ties_for_order_limit', {'tie_at_rank': [1]})],
    ('titles', 'title'): [('comparison_boundary', {'values': ['Life Without Fear', 'life without fear']})],
    ('titles', 'pub_id'): [('group_sizes', {'group_sizes': (1, 2, 3)})],
    ('titles', 'price'): [('rows_with_different_values', {}), ('null_rows', {'null_share': (0.05, 0.30)})],
    ('titles', 'pubdate'): [('comparison_boundary', {'values': ['1990-12-31 00:00:00.0', '1991-01-01 00:00:00.0',
                                                                '1991-12-31 00:00:00.0', '1992-01-01 00:00:00.0']}),
                            ('like_near_variant', {'values': ['1991%']})],
    ('titles', 'title_id'): [('comparison_boundary', {'values': ['14', '15', '16', 'BU2075', 'bu2075']})],
    ('jobs', 'job_desc'): [('comparison_boundary', {'values': ['Designer', 'designer', 'Editor', 'editor',
                                                               'DESIGNER']})],
    ('jobs', 'job_id'): [('unmatched_join_rows', {'joins_with': [('employee', 'job_id')]})],
    ('employee', 'job_id'): [('unmatched_join_rows', {'joins_with': [('jobs', 'job_id')]})],
    ('employee', 'fname'): [('duplicates_for_distinct', {'duplicate_share': (0.2, 0.5)})],
    ('employee', 'lname'): [('duplicates_for_distinct', {'duplicate_share': (0.2, 0.5)})],
    ('employee', 'minit'): [('comparison_boundary', {'values': ['P', 'p', 'S', 's', 'W', 'w']})],
    ('employee', 'hire_date'): [('comparison_boundary', {'values': ['1989-12-31 00:00:00.0', '1990-01-01 00:00:00.0',
                                                                   '1990-01-02 00:00:00.0', '1990-12-31 00:00:00.0',
                                                                   '1991-01-01 00:00:00.0']})],
    ('stores', 'stor_id'): [('group_sizes', {'group_sizes': (1, 2, 3)}),
                            ('comparison_boundary', {'values': ['7065', '7066', '7067']})],
    ('stores', 'stor_name'): [('duplicates_for_distinct', {'duplicate_share': (0.2, 0.5)})],
    ('stores', 'city'): [('group_sizes', {'group_sizes': (1, 2, 3)})],
    ('stores', 'state'): [('comparison_boundary', {'values': ['Massachusetts', 'massachusetts', 'MA', 'ma',
                                                              '%Massachusetts%', '%massachusetts%']})],
    ('sales', 'stor_id'): [('comparison_boundary', {'values': ['7065', '7066', '7067']})],
    ('sales', 'qty'): [('rows_with_different_values', {})],
    ('sales', 'ord_num'): [('null_in_count_column', {})],
    ('roysched', 'lorange'): [('comparison_boundary', {'values': [-1, 0, 1]})],
    ('roysched', 'royalty'): [('comparison_boundary', {'values': [9, 10, 11]})],
}

ENUMS = {
    ('titles', 'type'): ['business', 'mod_cook', 'UNDECIDED', 'popular_comp', 'psychology', 'trad_cook'],
    ('sales', 'payterms'): ['Net 60', 'Net 30', 'ON invoice'],
    ('authors', 'contract'): ['0', '1'],
}

BOUNDS = {
    ('jobs', 'min_lvl'): (0, None),
    ('titles', 'price'): (0, None),
    ('titles', 'advance'): (0, None),
    ('titles', 'royalty'): (0, 100),
    ('titles', 'ytd_sales'): (0, None),
    ('discounts', 'discount'): (0, 100),
    ('discounts', 'lowqty'): (0, None),
    ('roysched', 'lorange'): (0, None),
    ('roysched', 'royalty'): (0, 100),
    ('sales', 'qty'): (1, None),
    ('titleauthor', 'au_ord'): (1, None),
    ('titleauthor', 'royaltyper'): (0, 100),
}

DATE_MIN = {}

NULL_TARGETS = [
    ('authors', 'address'), ('authors', 'city'), ('authors', 'state'), ('authors', 'zip'),
    ('discounts', 'stor_id'), ('discounts', 'lowqty'), ('discounts', 'highqty'),
    ('employee', 'minit'), ('employee', 'job_lvl'),
    ('pub_info', 'logo'), ('pub_info', 'pr_info'),
    ('publishers', 'pub_name'), ('publishers', 'city'), ('publishers', 'state'), ('publishers', 'country'),
    ('roysched', 'lorange'), ('roysched', 'hirange'), ('roysched', 'royalty'),
    ('stores', 'stor_name'), ('stores', 'stor_address'), ('stores', 'city'), ('stores', 'state'), ('stores', 'zip'),
    ('titleauthor', 'au_ord'), ('titleauthor', 'royaltyper'),
    ('titles', 'pub_id'), ('titles', 'price'), ('titles', 'advance'), ('titles', 'royalty'),
    ('titles', 'ytd_sales'), ('titles', 'notes'),
]

TABLE_SIZES = {
    'publishers': 8, 'jobs': 14, 'authors': 23, 'stores': 6, 'titles': 18, 'employee': 43,
    'pub_info': 7, 'roysched': 86, 'sales': 21, 'titleauthor': 25, 'discounts': 3,
}

UNIQUE_TUPLES = {
    'sales': [('stor_id', 'ord_num', 'title_id')],
    'titleauthor': [('au_id', 'title_id')],
}

TEXT_PK_PREFIX = {
    ('authors', 'au_id'): 'GEN-AU-',
    ('employee', 'emp_id'): 'GEN-EMP-',
    ('publishers', 'pub_id'): 'GEN-PUB-',
    ('stores', 'stor_id'): 'GEN-ST-',
    ('titles', 'title_id'): 'GEN-TI-',
}


def exceptions_for(table: str, column: str) -> list:
    """Return the list of (pattern, targets) for a column."""
    return EXCEPTIONS.get((table, column), [])


def has_pattern(table: str, column: str, pattern: str) -> bool:
    """True if the column carries the given pattern."""
    return any(p == pattern for p, _ in exceptions_for(table, column))


def pattern_targets(table: str, column: str, pattern: str) -> dict:
    """Targets dict for a pattern (empty if absent)."""
    for p, t in exceptions_for(table, column):
        if p == pattern:
            return t
    return {}
