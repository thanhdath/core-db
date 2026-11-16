"""Specification loading: value domains, boundary literals, NULL targets, sizes, dependencies."""
import json
import re

_DEFAULT = {
    "generic_sampling_rules": {
        "integer_pk": "Sequential integers starting at 0, unique per table; never NULL.",
        "integer_fk": "Sample from parent key pool; NULL share follows the compact DB share.",
        "integer_numeric": "Uniform integer within the column's declared range; include boundary values.",
        "real_numeric": "Uniform real within the column's declared range rounded to 3 decimals; include boundary values.",
        "text_enum": "Uniform choice from explicit enum pool; boundary literals are added to the pool.",
        "text_free": "Short alphanumeric string; near-variants of listed equality literals.",
        "datetime": "Uniform datetime within table's observed range, format '%Y-%m-%d %H:%M:%S.0'.",
        "boolean_text": "Choice of 'true'/'false' with case variants 'TRUE'/'FALSE'.",
        "null_share": "For nullable columns, NULL share follows the compact DB share; at least one NULL row per nullable column.",
        "duplicates_distinct": "For DISTINCT-count columns that are not primary keys, 20-50% duplicate values.",
        "ties_order_limit": "For ORDER/LIMIT columns that are not primary keys, plant ties at the listed rank.",
    },
    "per_column_exceptions": [
        {"table": "Customers", "column": "ID", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["Mailings1_2.REFID", "mailings3.REFID"],
                     "parent_rows_without_children": True}},
        {"table": "Customers", "column": "GEOID", "pattern": "null_in_count_column",
         "targets": {"null_share": "5-30%"}},
        {"table": "Customers", "column": "GEOID", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["Demog.GEOID"], "parent_rows_without_children": True,
                     "child_rows_with_null_fk": True}},
        {"table": "Customers", "column": "age", "pattern": "comparison_boundary",
         "targets": {"values": [12, 13, 14, 18, 19, 20, 21]}},
        {"table": "Customers", "column": "EDUCATIONNUM", "pattern": "comparison_boundary",
         "targets": {"values": [6, 7, 8, 9]}},
        {"table": "Customers", "column": "SEX", "pattern": "comparison_boundary",
         "targets": {"values": ["Male", "male", "Female", "female"]}},
        {"table": "Customers", "column": "MARITAL_STATUS", "pattern": "comparison_boundary",
         "targets": {"values": ["never married", "NEVER MARRIED", "nevearried", "NEVEARRIED",
                                "never md", "NEVER MD", "nevermarried", "NEVERMARRIED"]}},
        {"table": "Customers", "column": "OCCUPATION", "pattern": "comparison_boundary",
         "targets": {"values": ["Sales", "sales"]}},
        {"table": "Demog", "column": "GEOID", "pattern": "comparison_boundary",
         "targets": {"values": [9, 10, 11, 29, 30, 31]}},
        {"table": "Demog", "column": "GEOID", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["Customers.GEOID"], "parent_rows_without_children": True}},
        {"table": "Demog", "column": "INHABITANTS_K", "pattern": "comparison_boundary",
         "targets": {"values": [19.999, 20, 20.001, 29.999, 30, 30.001]}},
        {"table": "Demog", "column": "INCOME_K", "pattern": "comparison_boundary",
         "targets": {"values": [2099.99, 2100, 2100.01, 2499.99, 2500, 2500.01]}},
        {"table": "Demog", "column": "INCOME_K", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "DESC"}},
        {"table": "Demog", "column": "A_VAR4", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "DESC"}},
        {"table": "Demog", "column": "A_VAR11", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "DESC"}},
        {"table": "Demog", "column": "A_VAR14", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "DESC"}},
        {"table": "Mailings1_2", "column": "REFID", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["Customers.ID"], "parent_rows_without_children": True}},
        {"table": "Mailings1_2", "column": "REF_DATE", "pattern": "comparison_boundary",
         "targets": {"values": ["2007-01-31 00:00:00.0", "2007-02-01 00:00:00.0",
                                "2007-02-02 00:00:00.0", "2007-02-27 00:00:00.0",
                                "2007-02-28 00:00:00.0", "2007-03-01 00:00:00.0"]}},
        {"table": "Mailings1_2", "column": "RESPONSE", "pattern": "comparison_boundary",
         "targets": {"values": ["true", "TRUE"]}},
        {"table": "mailings3", "column": "REFID", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["Customers.ID"], "parent_rows_without_children": True}},
    ],
    "dependencies": [
        {"child": "Customers.GEOID", "parent": "Demog.GEOID", "copied": []},
        {"child": "Mailings1_2.REFID", "parent": "Customers.ID", "copied": []},
        {"child": "Sales.REFID", "parent": "Customers.ID", "copied": []},
        {"child": "mailings3.REFID", "parent": "Customers.ID", "copied": []},
    ],
    "semantic_rules_and_formulas": [
        {"table": "Customers", "column": "SEX", "formula": "SEX IN ('Male','Female','male','female')"},
        {"table": "Customers", "column": "MARITAL_STATUS",
         "formula": "MARITAL_STATUS IN ('Never-married','Married-civ-spouse','Divorced','Widowed','Other',"
                    "'never married','NEVER MARRIED','nevearried','NEVEARRIED','never md','NEVER MD',"
                    "'nevermarried','NEVERMARRIED')"},
        {"table": "Customers", "column": "OCCUPATION",
         "formula": "OCCUPATION IN ('Machine-op-inspct','Handlers-cleaners','Exec-managerial',"
                    "'Farming-fishing','Other-service','Prof-specialty','Craft-repair','Sales','sales')"},
        {"table": "Customers", "column": "age", "formula": "age BETWEEN 12 AND 90"},
        {"table": "Customers", "column": "EDUCATIONNUM", "formula": "EDUCATIONNUM BETWEEN 1 AND 16"},
        {"table": "Demog", "column": "INHABITANTS_K", "formula": "INHABITANTS_K > 0"},
        {"table": "Demog", "column": "INCOME_K", "formula": "INCOME_K > 0"},
        {"table": "Mailings1_2", "column": "RESPONSE", "formula": "RESPONSE IN ('true','false','TRUE','FALSE')"},
        {"table": "mailings3", "column": "RESPONSE", "formula": "RESPONSE IN ('true','false','TRUE','FALSE')"},
        {"table": "Sales", "column": "AMOUNT", "formula": "AMOUNT >= 0"},
    ],
    "table_sizes_per_instance": {"Demog": 200, "Customers": 230, "Mailings1_2": 230,
                                 "Sales": 230, "mailings3": 230},
    "null_targets": ["Customers.GEOID", "Customers.SEX", "Customers.MARITAL_STATUS",
                     "Customers.EDUCATIONNUM", "Customers.OCCUPATION", "Customers.age",
                     "Mailings1_2.REF_DATE", "Mailings1_2.RESPONSE", "Sales.REFID",
                     "Sales.EVENT_DATE", "Sales.AMOUNT", "mailings3.REF_DATE",
                     "mailings3.RESPONSE"],
}


def default_specification() -> dict:
    """Deep-ish copy of the built-in specification."""
    return json.loads(json.dumps(_DEFAULT))


def load_specification(path: str) -> dict:
    """Read specification.json and fill missing keys from the built-in default."""
    with open(path) as f:
        spec = json.load(f)
    base = default_specification()
    for k, v in base.items():
        spec.setdefault(k, v)
    return spec


def boundary_values(spec: dict) -> dict:
    """{(table, COLUMN): [literal, ...]} from per_column_exceptions with pattern comparison_boundary."""
    out: dict = {}
    for ex in spec.get('per_column_exceptions', []):
        if ex.get('pattern') != 'comparison_boundary':
            continue
        key = (ex['table'], ex['column'].upper())
        out.setdefault(key, [])
        for v in ex.get('targets', {}).get('values', []):
            if v not in out[key]:
                out[key].append(v)
    return out


def tie_columns(spec: dict, schema=None) -> dict:
    """{(table, COLUMN): direction} for ties_for_order_limit exceptions (PK columns dropped)."""
    out: dict = {}
    for ex in spec.get('per_column_exceptions', []):
        if ex.get('pattern') != 'ties_for_order_limit':
            continue
        t, c = ex['table'], ex['column']
        if schema is not None:
            tm = schema.tables.get(t)
            if tm is not None and any(cm.name == c and cm.pk_pos > 0 for cm in tm.columns):
                continue
        out[(t, c.upper())] = ex.get('targets', {}).get('direction', 'DESC')
    return out


def duplicate_columns(spec: dict, schema=None) -> set:
    """{(table, COLUMN)} for duplicates_for_distinct exceptions (PK columns dropped)."""
    out = set()
    for ex in spec.get('per_column_exceptions', []):
        if ex.get('pattern') != 'duplicates_for_distinct':
            continue
        t, c = ex['table'], ex['column']
        if schema is not None:
            tm = schema.tables.get(t)
            if tm is not None and any(cm.name == c and cm.pk_pos > 0 for cm in tm.columns):
                continue
        out.add((t, c.upper()))
    return out


def null_targets(spec: dict) -> set:
    """{(table, COLUMN)} that must contain NULL rows."""
    return {(s.split('.')[0], s.split('.')[1].upper()) for s in spec.get('null_targets', [])}


def null_shares(spec: dict, schema) -> dict:
    """{(table, COLUMN): share} for the columns the NULL rule applies to."""
    targets = null_targets(spec)
    out: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            if cm.pk_pos > 0 or cm.notnull:
                continue
            key = (t, cm.name.upper())
            vals = schema.original_values.get((t, cm.name)) or []
            share = (sum(1 for v in vals if v is None) / float(len(vals))) if vals else 0.0
            if key not in targets and share <= 0.0:
                continue
            if share <= 0.0:
                share = 0.15
            elif share < 0.05:
                share = 0.05
            elif share > 0.30:
                share = 0.30
            out[key] = share
    return out


def enum_domains(spec: dict) -> dict:
    """{(table, COLUMN): [allowed values]} parsed from `COL IN (...)` formulas."""
    out: dict = {}
    for rule in spec.get('semantic_rules_and_formulas', []):
        f = rule.get('formula', '')
        m = re.match(r"\s*\w+\s+IN\s*\((.*)\)\s*$", f, re.I)
        if not m:
            continue
        vals = re.findall(r"'((?:[^']|'')*)'", m.group(1))
        if vals:
            out[(rule['table'], rule['column'].upper())] = [v.replace("''", "'") for v in vals]
    for key, extra in boundary_values(spec).items():
        if key in out:
            for v in extra:
                if isinstance(v, str) and v not in out[key]:
                    out[key].append(v)
    return out


def numeric_ranges(spec: dict) -> dict:
    """{(table, COLUMN): (lo, hi)} parsed from BETWEEN / > / >= formulas (2-tuples)."""
    out: dict = {}
    for rule in spec.get('semantic_rules_and_formulas', []):
        f = rule.get('formula', '')
        m = re.search(r"BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", f, re.I)
        if m:
            out[(rule['table'], rule['column'].upper())] = (float(m.group(1)), float(m.group(2)))
            continue
        m = re.search(r"(>=|>)\s*(-?\d+(?:\.\d+)?)", f)
        if m:
            lo = float(m.group(2)) + (0.0 if m.group(1) == '>=' else 1e-9)
            out[(rule['table'], rule['column'].upper())] = (lo, None)
    return out


def numeric_is_int(spec: dict) -> dict:
    """{(table, COLUMN): bool} integer flag for numeric domains (carried separately)."""
    out: dict = {}
    for rule in spec.get('semantic_rules_and_formulas', []):
        f = rule.get('formula', '')
        m = re.search(r"BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", f, re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            out[(rule['table'], rule['column'].upper())] = lo == int(lo) and hi == int(hi)
            continue
        m = re.search(r"(>=|>)\s*(-?\d+(?:\.\d+)?)", f)
        if m:
            lo = float(m.group(2))
            out[(rule['table'], rule['column'].upper())] = lo == int(lo)
    return out
