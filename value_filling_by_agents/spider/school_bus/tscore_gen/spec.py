"""Specification of the generation task, implemented by construction (no SQL evaluation)."""
import json
import os

DEFAULT_SPEC = {
    "generic_sampling_rules": {
        "int_primary_key": "Sequential integers, 1..N, no NULL, no duplicates.",
        "int_foreign_key": "Sample from the parent table's generated primary-key values; NULL only when the column is nullable.",
        "int_numeric": "Uniform integer within the range rule; include boundary values and one step on each side.",
        "text": "Short ASCII strings; a small pool of near-duplicates; NULL only when the column is nullable.",
        "bool": "0 or 1 only.",
        "text_enum": "Uniform sample from the listed enum values.",
        "fresh_values_share": 0.2,
    },
    "per_column_exceptions": [
        {"table": "driver", "column": "Driver_ID",
         "pattern": "unmatched_join_rows",
         "targets": "parent rows without children; PK remains sequential unique integers 1..N; the duplicates_for_distinct and group_sizes targets extracted for this column refer to join/aggregation behaviour over school_bus, not to PK values, and are not enforced on the PK column"},
        {"table": "driver", "column": "Home_city",
         "pattern": "group_sizes; aggregate_boundary; duplicates_for_distinct; ties_for_order_limit; comparison_boundary",
         "targets": "group_sizes 1,2,>=3; COUNT(*) 1,2,3,4; duplicate_share 20-50%; tie at rank 1 DESC; 'Hartford' and 'hartford'"},
        {"table": "driver", "column": "Age", "pattern": "comparison_boundary; group_sizes",
         "targets": "39,40,41; group_sizes 1,2,>=3"},
        {"table": "driver", "column": "Name", "pattern": "duplicates_for_distinct; ties_for_order_limit",
         "targets": "duplicate_share 20-50%; tie at rank 1 ASC"},
        {"table": "driver", "column": "Party", "pattern": "aggregate_boundary", "targets": "COUNT(*) 0,1; values only in {Dem, Rep}; no NULLs"},
        {"table": "school", "column": "School_ID", "pattern": "unmatched_join_rows",
         "targets": "parent rows without children"},
        {"table": "school", "column": "Type", "pattern": "duplicates_for_distinct; aggregate_boundary",
         "targets": "duplicate_share 20-50%; COUNT(*) 1,2,3"},
        {"table": "school", "column": "School", "pattern": "duplicates_for_distinct",
         "targets": "duplicate_share 20-50%"},
        {"table": "school_bus", "column": "Driver_ID", "pattern": "unmatched_join_rows; null_rows",
         "targets": "parent rows without children; no NULL (NOT NULL column); participates in composite-PK uniqueness repair"},
        {"table": "school_bus", "column": "School_ID",
         "pattern": "unmatched_join_rows; null_rows; aggregate_boundary; null_in_count_column",
         "targets": "parent rows without children; no NULL (NOT NULL column); restrict to at most 3 distinct parent values per instance and at least 1; no NULL share; participates in composite-PK uniqueness repair"},
        {"table": "school_bus", "column": "Years_Working", "pattern": "rows_with_different_values",
         "targets": "for each group by School_ID (and/or Driver_ID) with >=2 rows, assign >=2 distinct values and protect those positions from NULL application; range 0..20"},
    ],
    "dependencies": [
        {"child": "school_bus.School_ID", "parent": "school.School_ID", "copied_from_parent": []},
        {"child": "school_bus.Driver_ID", "parent": "driver.Driver_ID", "copied_from_parent": []},
        {"child": "school_bus", "parent": "school_bus", "copied_from_parent": [],
         "note": "composite PRIMARY KEY (School_ID, Driver_ID) enforced by construction after FK assignment"},
    ],
    "semantic_rules_and_formulas": [
        {"table": "driver", "column": "Driver_ID", "formula": "Driver_ID > 0"},
        {"table": "driver", "column": "Age", "formula": "Age BETWEEN 18 AND 120"},
        {"table": "driver", "column": "Party", "formula": "Party IN ('Dem','Rep')"},
        {"table": "school", "column": "School_ID", "formula": "School_ID > 0"},
        {"table": "school", "column": "Type", "formula": "Type IN ('Public','Private','Private Catholic')"},
        {"table": "school_bus", "column": "School_ID", "formula": "School_ID > 0"},
        {"table": "school_bus", "column": "Driver_ID", "formula": "Driver_ID > 0"},
        {"table": "school_bus", "column": "Years_Working", "formula": "Years_Working >= 0"},
        {"table": "school_bus", "column": "If_full_time", "formula": "If_full_time IN (0,1)"},
    ],
    "table_sizes_per_instance": {"driver": 12, "school": 7, "school_bus": 5},
    "null_targets": ["driver.Home_city", "driver.Age", "driver.Name", "school.Grade", "school.School",
                     "school.Location", "school.Type", "school_bus.Years_Working", "school_bus.If_full_time"],
    "supporting_evidence": [
        "driver.Party values: Dem, Rep (no NULLs).",
        "driver.Age values: 30, 35, 36, 40, 42, 45, 46, 52.",
        "school.Type values: Public, Private, Private Catholic.",
        "school_bus.If_full_time values: T, F.",
        "school_bus.Years_Working values: 2, 3, 6, 8, 10.",
        "school_bus.Driver_ID and school_bus.School_ID are NOT NULL (composite PRIMARY KEY).",
    ],
    "uncertainty": [
        "No formulas were found; the original data does not show any calculated columns.",
        "The NULL share follows the compact database's share per column (as implemented); a nullable column with compact share 0 still gets exactly one NULL row per instance.",
        "The per-instance sizes are 12/7/5 (chosen, not the original compact sizes); the compact database is the source of the observed values and statistics, not of the generated row counts.",
        "The upper bound 20 for school_bus.Years_Working is an explicit assumption; the observed values are 2..10 and the semantic rule only requires Years_Working >= 0.",
        "The driver.Age range 18..120 is an explicit assumption; the supplied DDL has no CHECK constraints and observed values are 30..52.",
        "Planting 'hartford' (lowercase) in driver.Home_city is an assumption to exercise case sensitivity of the <= / = comparison boundary; the compact DB does not show this value.",
        "The composite-PK uniqueness repair and the school_bus.School_ID distinct-count restriction (1..3) are construction steps; after the fix, rows_skipped must be empty for all tables.",
    ],
}

ENUMS = {
    ("driver", "Party"): ["Dem", "Rep"],
    ("school", "Type"): ["Public", "Private", "Private Catholic"],
}
RANGES = {
    ("driver", "Age"): (18, 120),
    ("school_bus", "Years_Working"): (0, 20),
}
BOUNDARY_VALUES = {
    ("driver", "Age"): [39, 40, 41],
    ("driver", "Home_city"): ["Hartford", "hartford"],
}
DUPLICATE_SHARE_COLUMNS = {
    ("driver", "Home_city"), ("driver", "Name"),
    ("school", "Type"), ("school", "School"),
}
GROUP_SIZE_COLUMNS = {("driver", "Home_city"), ("driver", "Age")}
UNMATCHED_PARENT_COLUMNS = {("driver", "Driver_ID"), ("school", "School_ID")}
NULL_FK_COLUMNS = set()
DIFFERENT_VALUES_COLUMNS = {("school_bus", "Years_Working")}
TIE_COLUMNS = {("driver", "Name"): "ASC", ("driver", "Home_city"): "DESC"}
NO_NULL_COLUMNS = {("driver", "Party")}
DISTINCT_COUNT_COLUMNS = {("school_bus", "School_ID"): (1, 2, 3)}
AGGREGATE_BOUNDARY_COLUMNS = {
    ("driver", "Home_city"): [1, 2, 3, 4],
    ("school", "Type"): [1, 2, 3],
}
MAX_DISTINCT_FK = {("school_bus", "School_ID"): 3}


def load_spec(path: str = None) -> dict:
    """Load specification.json if present, else the built-in default."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'specification.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_SPEC


def enum_for(table: str, column: str):
    return ENUMS.get((table, column))


def range_for(table: str, column: str):
    return RANGES.get((table, column))


def boundaries_for(table: str, column: str):
    return BOUNDARY_VALUES.get((table, column), [])


def null_share_for(table: str, column: str, observed_share: float) -> float:
    """NULL share: follow the compact database's share, at least one NULL row per nullable column."""
    return max(observed_share, 0.0)
