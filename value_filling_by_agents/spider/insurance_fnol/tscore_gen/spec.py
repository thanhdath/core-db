"""Specification loading, column plans and semantic rules."""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC_PATH = os.path.join(_HERE, 'specification.json')

_EMBEDDED = {
    "generic_sampling_rules": {
        "integer_pk": "Sequential integers starting at 1, unique per table, never NULL.",
        "integer_fk": "Sample from parent PK pool; include at least one parent row with no children and, where nullable, at least one NULL.",
        "varchar_name": "Random first+last name from a fixed name pool; allow near-duplicate variants and duplicates on DISTINCT columns.",
        "varchar_phone": "Random phone format from a fixed pool of formats; allow duplicates and NULL where nullable.",
        "char_code": "Sample from the table's enum pool; allow case variants for equality literals.",
        "date": "Random date in 2015-01-01..2019-12-31 formatted %Y-%m-%d; allow duplicates on DISTINCT columns.",
        "real_amount": "Uniform random in [0.01, 10000.0], two decimals.",
        "boundary": "For each listed literal, include the literal and one step on each side.",
        "near_variant": "For each listed LIKE/equality literal, include the literal plus case, suffix and one-character variants.",
        "tie": "Ensure at least two rows share the top value of the ORDER column at the listed rank.",
        "null_share": "For nullable columns, 5-30% of generated rows are NULL, at least one per column."
    },
    "per_column_exceptions": [
        {"column": "Customers.Customer_name", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Customers.Customer_name", "pattern": "group_sizes", "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "Customers.Customer_name", "pattern": "ties_for_order_limit", "targets": {"tie_at_rank": [1], "direction": "DESC", "tie_on": ["COUNT(*)", "COUNT(DISTINCT customers_policies.policy_id)"]}},
        {"column": "Customers.Customer_name", "pattern": "like_near_variant", "targets": {"literals": ["%Diana%", "%sian%"], "variants": ["Diana", "Dianb", "Diana x", "diana", "sian", "siao", "sian x", "SIAN"]}},
        {"column": "Customers.Customer_ID", "pattern": "group_sizes", "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "Customers.Customer_ID", "pattern": "ties_for_order_limit", "targets": {"tie_at_rank": [1], "direction": "ASC and DESC", "tie_on": ["COUNT(*)", "COUNT(DISTINCT customers_policies.policy_id)"]}},
        {"column": "Customers.Customer_ID", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "First_Notification_of_Loss.Service_ID", "pattern": "group_sizes", "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "First_Notification_of_Loss.Service_ID", "pattern": "aggregate_boundary", "targets": {"aggregate": ["COUNT(first_notification_of_loss.service_id)", "COUNT(*)"], "values": [1, 2, 3]}},
        {"column": "First_Notification_of_Loss.Service_ID", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Services.Service_name", "pattern": "group_sizes", "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "Services.Service_name", "pattern": "aggregate_boundary", "targets": {"aggregate": ["COUNT(*)"], "values": [1, 2, 3]}},
        {"column": "Services.Service_name", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Available_Policies.Customer_Phone", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Available_Policies.Customer_Phone", "pattern": "null_rows", "targets": {"null_share": "5-30 % of generated rows"}},
        {"column": "Available_Policies.policy_type_code", "pattern": "aggregate_boundary", "targets": {"aggregate": ["COUNT(*)"], "values": [3, 4, 5]}},
        {"column": "Available_Policies.policy_type_code", "pattern": "comparison_boundary", "targets": {"values": ["Life Insurance", "life insurance"]}},
        {"column": "Customers_Policies.Policy_ID", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Available_Policies.Policy_ID", "pattern": "aggregate_boundary", "targets": {"aggregate": ["COUNT(DISTINCT available_policies.policy_id)"], "values": [3, 4, 5]}},
        {"column": "Customers_Policies.Date_Closed", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "Customers_Policies.Date_Opened", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}}
    ],
    "dependencies": [
        {"child": "Customers_Policies.Customer_ID", "parent_table": "Customers", "parent_column": "Customer_ID", "copied": []},
        {"child": "Customers_Policies.Policy_ID", "parent_table": "Available_Policies", "parent_column": "Policy_ID", "copied": []},
        {"child": "First_Notification_of_Loss.Customer_ID", "parent_table": "Customers", "parent_column": "Customer_ID", "copied": []},
        {"child": "First_Notification_of_Loss.Policy_ID", "parent_table": "Available_Policies", "parent_column": "Policy_ID", "copied": []},
        {"child": "First_Notification_of_Loss.Service_ID", "parent_table": "Services", "parent_column": "Service_ID", "copied": []},
        {"child": "Claims.FNOL_ID", "parent_table": "First_Notification_of_Loss", "parent_column": "FNOL_ID", "copied": []},
        {"child": "Settlements.Claim_ID", "parent_table": "Claims", "parent_column": "Claim_ID", "copied": []}
    ],
    "semantic_rules_and_formulas": [
        {"table": "Available_Policies", "column": "policy_type_code", "formula": "policy_type_code IN ('Life Insurance','Property Insurance','Mortgage Insurance','Travel Insurance')"},
        {"table": "Customers_Policies", "column": "Date_Closed", "formula": "Date_Closed >= Date_Opened"},
        {"table": "Settlements", "column": "Settlement_Amount", "formula": "Settlement_Amount >= 0"}
    ],
    "table_sizes_per_instance": {"Customers": 15, "Services": 4, "Available_Policies": 15, "Customers_Policies": 14,
                                  "First_Notification_of_Loss": 7, "Claims": 10, "Settlements": 10},
    "null_targets": ["Available_Policies.Customer_Phone", "Settlements.Claim_ID"]
}


def load_specification() -> dict:
    """Load specification.json next to this module, else the embedded fallback."""
    if os.path.exists(_SPEC_PATH):
        try:
            with open(_SPEC_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return _EMBEDDED


def _col_key(s: str):
    if not s or '.' not in s:
        return None
    t, c = s.split('.', 1)
    return (t.strip(), c.strip())


def _parse_share(spec: str):
    """'20-50 %' -> (0.20, 0.50); '5-30 % of generated rows' -> (0.05, 0.30)."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)', spec or '')
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    if '%' in spec:
        return lo / 100.0, hi / 100.0
    return lo, hi


_RULE_IN = re.compile(r'^(\w+)\s+in\s*\((.*)\)\s*$', re.I)
_RULE_GE = re.compile(r'^(\w+)\s*>=\s*(\w+)\s*$', re.I)
_RULE_GE_LIT = re.compile(r'^(\w+)\s*>=\s*(-?\d+(?:\.\d+)?)\s*$', re.I)
_RULE_NN = re.compile(r'^(\w+)\s+is\s+not\s+null\s*$', re.I)


def _parse_formula(table: str, text: str) -> dict:
    """Turn one formula string into an executable rule dict (Python-side)."""
    s = (text or '').strip()
    m = _RULE_IN.match(s)
    if m:
        col = m.group(1)
        inner = m.group(2)
        vals = [v.strip().strip("'\"") for v in re.findall(r"'[^']*'|\"[^\"]*\"", inner)]
        return {'kind': 'enum', 'table': table, 'col': col, 'values': vals}
    m = _RULE_GE.match(s)
    if m:
        return {'kind': 'ge_cols', 'table': table, 'col': m.group(1), 'ref': m.group(2)}
    m = _RULE_GE_LIT.match(s)
    if m:
        return {'kind': 'ge_lit', 'table': table, 'col': m.group(1), 'min': float(m.group(2))}
    m = _RULE_NN.match(s)
    if m:
        return {'kind': 'not_null', 'table': table, 'col': m.group(1)}
    return {'kind': 'opaque', 'table': table, 'text': s}


def build_plan(spec: dict, schema) -> dict:
    """Translate the specification into sampling directives + rules for one schema."""
    cols: dict = {}
    for exc in spec.get('per_column_exceptions', []):
        key = _col_key(exc.get('column', ''))
        if key is None:
            continue
        pat = exc.get('pattern')
        tg = exc.get('targets') or {}
        d = cols.setdefault(key, {})
        if pat == 'duplicates_for_distinct':
            sh = _parse_share(tg.get('duplicate_share', ''))
            if sh:
                d['dup_share'] = sh
            d['distinct'] = True
        elif pat == 'group_sizes':
            d['group_sizes'] = True
        elif pat == 'ties_for_order_limit':
            d['tie_at_rank'] = int((tg.get('tie_at_rank') or [1])[0])
            d['tie_direction'] = str(tg.get('direction', 'DESC'))
        elif pat == 'like_near_variant':
            d['like_variants'] = list(tg.get('variants', []))
            d['like_literals'] = list(tg.get('literals', []))
        elif pat == 'null_rows':
            sh = _parse_share(tg.get('null_share', ''))
            if sh:
                d['null_share'] = sh
        elif pat == 'comparison_boundary':
            d['cmp_values'] = list(tg.get('values', []))
        elif pat == 'aggregate_boundary':
            d['agg_values'] = list(tg.get('values', []))
    for txt in spec.get('null_targets', []):
        k = _col_key(txt)
        if k is not None:
            cols.setdefault(k, {})['null_target'] = True
    rules = []
    for r in spec.get('semantic_rules_and_formulas', []):
        rules.append(_parse_formula(r.get('table', ''), r.get('formula', '')))
    sizes = spec.get('table_sizes_per_instance', {}) or {}
    norm_sizes = {}
    for t, n in sizes.items():
        if t in schema.tables:
            norm_sizes[t] = int(n)
    deps = []
    for d in spec.get('dependencies', []):
        c = _col_key(d.get('child', ''))
        if c is None:
            continue
        deps.append({'child': c, 'parent': (d.get('parent_table'), d.get('parent_column'))})
    return {'cols': cols, 'rules': rules, 'sizes': norm_sizes, 'deps': deps,
            'null_targets': [k for k in cols if cols[k].get('null_target')]}
