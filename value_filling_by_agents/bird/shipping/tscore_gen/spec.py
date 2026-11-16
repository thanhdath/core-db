"""Specification loading and compilation into per-column construction parameters."""
import json
import os
import re

_SPEC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'specification.json')

_DEFAULT = {
    "per_column_exceptions": [
        {"table": "shipment", "column": "ship_date", "pattern": "comparison_boundary",
         "targets": ["2015-12-31", "2016-01-01", "2016-12-31", "2017-01-01", "2017-12-31", "2018-01-01"]},
        {"table": "shipment", "column": "ship_date", "pattern": "like_near_variant",
         "targets": ["2016-%", "2017%", "2017-%", "2016%", "2017-02-%", "2017-02%"]},
        {"table": "shipment", "column": "weight", "pattern": "comparison_boundary",
         "targets": ["9999", "10000", "10001", "69999", "70000", "70001"]},
        {"table": "shipment", "column": "weight", "pattern": "tie", "targets": ["1", "5"]},
        {"table": "shipment", "column": "weight", "pattern": "null_rows", "targets": ["5-30%"]},
        {"table": "city", "column": "city_name", "pattern": "comparison_boundary",
         "targets": ["Jacksonville", "jacksonville", "New York", "new york", "Chicago", "chicago"]},
        {"table": "driver", "column": "last_name", "pattern": "comparison_boundary",
         "targets": ["Hicks", "hicks", "Newell", "newell", "Kieltyka", "kieltyka"]},
        {"table": "driver", "column": "last_name", "pattern": "duplicates_for_distinct", "targets": ["20-50%"]},
        {"table": "customer", "column": "cust_name", "pattern": "comparison_boundary",
         "targets": ["S K L Enterprises Inc", "s k l enterprises inc", "Autoware Inc", "autoware inc",
                     "Klett & Sons Repair", "klett & sons repair"]},
        {"table": "customer", "column": "cust_name", "pattern": "like_near_variant",
         "targets": ["%S K L Enterprises Inc%", "S K L Enterprises Inc", "S K L Enterprises Ind",
                     "S K L Enterprises Inc x", "s k l enterprises inc"]},
        {"table": "truck", "column": "model_year", "pattern": "comparison_boundary",
         "targets": ["2004", "2005", "2006", "2007"]},
        {"table": "driver", "column": "first_name", "pattern": "comparison_boundary",
         "targets": ["Sue", "sue", "Zachery", "zachery"]},
        {"table": "driver", "column": "first_name", "pattern": "duplicates_for_distinct", "targets": ["20-50%"]},
        {"table": "truck", "column": "make", "pattern": "comparison_boundary",
         "targets": ["Mack", "mack", "Peterbilt", "peterbilt", "Kenworth", "kenworth"]},
        {"table": "truck", "column": "truck_id", "pattern": "comparison_boundary", "targets": ["2", "3", "4"]},
        {"table": "city", "column": "area", "pattern": "tie", "targets": ["1"]},
        {"table": "shipment", "column": "ship_id", "pattern": "null_in_count_column", "targets": ["none"]},
        {"table": "customer", "column": "cust_id", "pattern": "unmatched_join_rows", "targets": ["shipment.cust_id"]},
        {"table": "shipment", "column": "cust_id", "pattern": "unmatched_join_rows", "targets": ["customer.cust_id"]},
        {"table": "driver", "column": "driver_id", "pattern": "unmatched_join_rows", "targets": ["shipment.driver_id"]},
        {"table": "city", "column": "city_id", "pattern": "unmatched_join_rows", "targets": ["shipment.city_id"]},
    ],
    "dependencies": [
        {"child": "shipment", "child_column": "cust_id", "parent": "customer", "parent_column": "cust_id",
         "copied_columns": []},
        {"child": "shipment", "child_column": "city_id", "parent": "city", "parent_column": "city_id",
         "copied_columns": []},
        {"child": "shipment", "child_column": "driver_id", "parent": "driver", "parent_column": "driver_id",
         "copied_columns": []},
        {"child": "shipment", "child_column": "truck_id", "parent": "truck", "parent_column": "truck_id",
         "copied_columns": []},
    ],
    "semantic_rules_and_formulas": [
        {"table": "city", "column": "population", "formula": "population > 0"},
        {"table": "city", "column": "area", "formula": "area > 0"},
        {"table": "customer", "column": "annual_revenue", "formula": "annual_revenue >= 0"},
        {"table": "customer", "column": "cust_type",
         "formula": "cust_type IN ('manufacturer', 'wholesaler', 'retailer')"},
        {"table": "shipment", "column": "weight", "formula": "weight > 0"},
        {"table": "shipment", "column": "ship_date",
         "formula": "ship_date >= '2015-12-31' AND ship_date <= '2018-01-01'"},
        {"table": "truck", "column": "model_year", "formula": "model_year BETWEEN 2004 AND 2010"},
        {"table": "truck", "column": "make", "formula": "make IN ('Peterbilt', 'Mack', 'Kenworth')"},
    ],
    "table_sizes_per_instance": {"city": 12, "customer": 12, "driver": 12, "truck": 12, "shipment": 12},
    "null_targets": ["shipment.weight", "shipment.cust_id", "shipment.driver_id", "shipment.city_id",
                     "shipment.truck_id"],
    "supporting_evidence": {},
    "uncertainty": "",
}


def load_specification(path: str = None) -> dict:
    """Read specification.json if present, else the embedded default."""
    try:
        with open(path or _SPEC_PATH) as f:
            return json.load(f)
    except Exception:
        return dict(_DEFAULT)


_NUM = r'-?\d+(?:\.\d+)?'
_STR = r"'(?:[^']|'')*'"


def _lit(v: str):
    v = v.strip()
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1].replace("''", "'")
    try:
        return float(v) if '.' in v else int(v)
    except ValueError:
        return v


def _compile_formula(formula: str):
    """Compile a simple formula into f(value) -> bool (True when not FALSE)."""
    f = formula.strip()
    fn = None
    m = re.fullmatch(r'(\w+)\s+IN\s*\(([^)]*)\)', f, re.I)
    if m:
        vals = [_lit(x) for x in re.findall(_STR + '|' + _NUM, m.group(2))]
        fn = lambda v, vals=vals: v is None or v in vals
    if fn is None:
        m = re.fullmatch(r'(\w+)\s+BETWEEN\s+(' + _NUM + r')\s+AND\s+(' + _NUM + r')', f, re.I)
        if m:
            lo, hi = _lit(m.group(2)), _lit(m.group(3))
            fn = lambda v, lo=lo, hi=hi: v is None or (lo <= v <= hi)
    if fn is None:
        parts = re.split(r'\s+AND\s+', f, flags=re.I)
        preds = []
        for p in parts:
            m = re.fullmatch(r'(\w+)\s*(>=|<=|<>|!=|=|>|<)\s*(' + _STR + '|' + _NUM + ')', p.strip(), re.I)
            if not m:
                continue
            op, lit = m.group(2), _lit(m.group(3))
            if op == '=':
                preds.append(lambda v, lit=lit: v is None or v == lit)
            elif op in ('<>', '!='):
                preds.append(lambda v, lit=lit: v is None or v != lit)
            elif op == '>':
                preds.append(lambda v, lit=lit: v is None or v > lit)
            elif op == '>=':
                preds.append(lambda v, lit=lit: v is None or v >= lit)
            elif op == '<':
                preds.append(lambda v, lit=lit: v is None or v < lit)
            elif op == '<=':
                preds.append(lambda v, lit=lit: v is None or v <= lit)
        if preds:
            fn = lambda v, preds=preds: all(p(v) for p in preds)
    if fn is not None:
        try:
            fn.__src__ = formula
        except (AttributeError, TypeError):
            pass
    return fn


def _parse_share(t) -> float:
    """'5-30%' -> 0.175 (midpoint); '20-50%' -> 0.35; 'none' -> 0.0."""
    if isinstance(t, (int, float)):
        return float(t)
    s = str(t)
    m = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%', s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 200.0
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', s)
    if m:
        return float(m.group(1)) / 100.0
    return 0.0


def _coerce(v, type_str: str):
    t = (type_str or '').lower()
    if any(k in t for k in ('int', 'year', 'bit')):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return v
    if any(k in t for k in ('real', 'float', 'double', 'decimal', 'numeric', 'number')):
        try:
            return float(v)
        except (TypeError, ValueError):
            return v
    return str(v)


def build_spec(raw: dict, schema) -> dict:
    """Turn the specification into per-column construction parameters."""
    cols: dict = {}
    for t, tm in schema.tables.items():
        for cm in tm.columns:
            cols[(t, cm.name)] = {
                'boundary': [], 'like': [], 'tie': False, 'dup_share': 0.0,
                'null_share': None, 'formula': None, 'formula_src': None,
                'unmatched': False, 'null_in_count': False,
            }
    for ex in raw.get('per_column_exceptions', []):
        t, c = ex.get('table'), ex.get('column')
        key = (t, c)
        if key not in cols:
            continue
        pat = ex.get('pattern')
        tg = ex.get('targets') or []
        type_str = next((cm.type_str for cm in schema.tables[t].columns if cm.name == c), '')
        if pat == 'comparison_boundary':
            cols[key]['boundary'] = [_coerce(v, type_str) for v in tg]
        elif pat == 'like_near_variant':
            cols[key]['like'] = [str(v) for v in tg]
        elif pat == 'tie':
            cols[key]['tie'] = True
        elif pat == 'duplicates_for_distinct':
            cols[key]['dup_share'] = _parse_share(tg[0] if tg else 0)
        elif pat == 'null_rows':
            cols[key]['null_share'] = _parse_share(tg[0] if tg else 0)
        elif pat == 'unmatched_join_rows':
            cols[key]['unmatched'] = True
        elif pat == 'null_in_count_column':
            cols[key]['null_in_count'] = True
    for rule in raw.get('semantic_rules_and_formulas', []):
        key = (rule.get('table'), rule.get('column'))
        if key in cols:
            src = rule.get('formula', '')
            cols[key]['formula'] = _compile_formula(src)
            cols[key]['formula_src'] = src
    sizes = {t: int(n) for t, n in (raw.get('table_sizes_per_instance') or {}).items()}
    null_targets = set()
    for nt in raw.get('null_targets', []):
        if '.' in nt:
            t, c = nt.split('.', 1)
            null_targets.add((t, c))
    return {'columns': cols, 'sizes': sizes, 'null_targets': null_targets, 'raw': raw,
            'literal_pool': {}}
