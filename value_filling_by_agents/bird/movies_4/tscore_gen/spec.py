"""Specification loader: value pools, ranges, enums, NULL targets and per-column exceptions."""
import json
import os
import re

_SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specification.json')

_DEFAULT = {
    "generic_sampling_rules": {
        "integer_pk": "Sequential integers starting at 1, unique per table; never NULL.",
        "integer_fk": "Sample from the parent table's generated primary-key pool; 5-30% NULL where nullable.",
        "integer_quantity": "Uniform integer in [1, 1000] unless a range rule narrows it.",
        "integer_amount": "Uniform integer in [0, 1000000000] unless a range rule narrows it.",
        "real_metric": "Uniform real in [0.0, 200.0] rounded to 6 decimals unless a range rule narrows it.",
        "text_short": "Random token of 3-20 lowercase letters; 20-50% duplicate share on DISTINCT-targeted columns.",
        "text_long": "Random sentence of 40-250 characters.",
        "date_iso": "Random date between 1900-01-01 and 2025-12-31 formatted %Y-%m-%d.",
        "enum_small": "Uniform choice from the listed enum values; case-flipped near-variants for equality literals.",
        "null_share": "For nullable columns, 5-30% NULL rows per instance; at least one NULL row per nullable column.",
        "boundary_numbers": "For each listed numeric literal L, include L-1, L, L+1.",
        "boundary_dates": "For each listed date literal D, include D-1 day, D, D+1 day.",
        "tie_ranks": "For ORDER/LIMIT target columns, plant ties at the listed ranks (1, 100) in both directions.",
        "fresh_values": "All non-key text columns draw fresh random values."
    },
    "per_column_exceptions": [
        {"column": "movie.title", "pattern": "like_near_variant",
         "targets": {"literals": ["Pirates of the Caribbean: At World's End",
                                  "Pirates of the Caribbean: Dead Man's Chest",
                                  "C'era una volta il West"],
                     "variants": ["Pirates of the Caribbean: At Worlds End",
                                  "pirates of the caribbean: at worlds end",
                                  "Pirates of the Caribbean: Dead Mans Chest",
                                  "pirates of the caribbean: dead mans chest"]}},
        {"column": "movie.title", "pattern": "comparison_boundary",
         "targets": {"values": ["Pirates of the Caribbean: At World's End",
                                "pirates of the caribbean: at world's end", "Four Rooms", "four rooms",
                                "I Hope They Serve Beer in Hell", "i hope they serve beer in hell"]}},
        {"column": "movie.title", "pattern": "duplicates_for_distinct", "targets": {"duplicate_share": "20-50 %"}},
        {"column": "movie.title", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1, 100], "direction": "ASC and DESC", "tie_on": ["COUNT(*)"]}},
        {"column": "movie.movie_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie_cast.movie_id", "movie_company.movie_id", "movie_crew.movie_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie.movie_id", "pattern": "comparison_boundary",
         "targets": {"values": [128, 129, 130, 284, 285, 286]}},
        {"column": "movie.release_date", "pattern": "comparison_boundary",
         "targets": {"values": ["1999-12-31", "2000-01-01", "2000-12-31", "2001-01-01"]}},
        {"column": "movie.release_date", "pattern": "like_near_variant",
         "targets": {"literals": ["2000%", "2006%", "1916%", "1945%", "1995%", "2016%"],
                     "variants": ["1999-12-31", "2000-01-01", "2000-12-31", "2001-01-01",
                                  "2005-12-31", "2006-01-01", "2006-12-31", "2007-01-01"]}},
        {"column": "movie.release_date", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "ASC and DESC"}},
        {"column": "movie.revenue", "pattern": "comparison_boundary",
         "targets": {"values": [119999999, 120000000, 120000001, 999999999, 1000000000, 1000000001]}},
        {"column": "movie.movie_status", "pattern": "comparison_boundary",
         "targets": {"values": ["Released", "released", "Post Production", "post production",
                                "st Product", "st product"]}},
        {"column": "person.person_name", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "person.person_name", "pattern": "comparison_boundary",
         "targets": {"values": ["Marcia Ross", "marcia ross", "Dariusz Wolski", "dariusz wolski",
                                "harrison ford", "HARRISON FORD"]}},
        {"column": "person.person_name", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "ASC and DESC", "tie_on": ["COUNT(*)"]}},
        {"column": "person.person_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie_crew.person_id", "movie_cast.person_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "person.person_id", "pattern": "comparison_boundary",
         "targets": {"values": [1325272, 1325273, 1325274]}},
        {"column": "movie_company.movie_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie.movie_id", "production_country.movie_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie_company.movie_id", "pattern": "aggregate_boundary",
         "targets": {"aggregate": ["COUNT(movie_company.movie_id)"], "values": [199, 200, 201]}},
        {"column": "movie_company.movie_id", "pattern": "null_in_count_column",
         "targets": {"null_share": "5-30 % of generated rows"}},
        {"column": "movie_company.company_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["production_company.company_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie_company.company_id", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "genre.genre_name", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "genre.genre_name", "pattern": "comparison_boundary",
         "targets": {"values": ["Animation", "animation", "Romance", "romance", "Horror", "horror"]}},
        {"column": "production_company.company_name", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "production_company.company_name", "pattern": "group_sizes",
         "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "production_company.company_name", "pattern": "comparison_boundary",
         "targets": {"values": ["Walt Disney Pictures", "walt disney pictures",
                                "Universal Studios", "universal studios"]}},
        {"column": "production_company.company_name", "pattern": "aggregate_boundary",
         "targets": {"aggregate": ["COUNT(production_company.company_name)", "COUNT(*)"],
                     "values": [149, 150, 151, 199, 200, 201]}},
        {"column": "production_company.company_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie_company.company_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "production_company.company_id", "pattern": "aggregate_boundary",
         "targets": {"aggregate": ["COUNT(*)"], "values": [149, 150, 151, 199, 200, 201]}},
        {"column": "movie_cast.movie_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie.movie_id", "movie_genres.movie_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie_cast.movie_id", "pattern": "comparison_boundary",
         "targets": {"values": [284, 285, 286, 1864, 1865, 1866]}},
        {"column": "movie_cast.movie_id", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "movie_cast.character_name", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "movie_crew.person_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["person.person_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie_crew.person_id", "pattern": "comparison_boundary",
         "targets": {"values": [1325272, 1325273, 1325274]}},
        {"column": "movie_crew.person_id", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "movie_crew.movie_id", "pattern": "unmatched_join_rows",
         "targets": {"joins_with": ["movie.movie_id"],
                     "parent_rows_without_children": True, "child_rows_with_null_fk": True}},
        {"column": "movie_crew.movie_id", "pattern": "null_in_count_column",
         "targets": {"null_share": "5-30 % of generated rows"}},
        {"column": "movie_crew.movie_id", "pattern": "comparison_boundary",
         "targets": {"values": [11, 12, 13, 128, 129, 130]}},
        {"column": "movie_crew.job", "pattern": "comparison_boundary",
         "targets": {"values": ["Director of Photography", "director of photography",
                                "Director", "director", "Animation", "animation"]}},
        {"column": "keyword.keyword_name", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "ASC and DESC", "tie_on": ["COUNT(*)"]}},
        {"column": "keyword.keyword_name", "pattern": "comparison_boundary",
         "targets": {"values": ["independent film", "INDEPENDENT FILM", "woman director",
                                "WOMAN DIRECTOR", "saving the world", "SAVING THE WORLD"]}},
        {"column": "keyword.keyword_id", "pattern": "group_sizes",
         "targets": {"group_sizes": "1, 2 and >= 3"}},
        {"column": "movie_keywords.keyword_id", "pattern": "null_in_count_column",
         "targets": {"null_share": "5-30 % of generated rows"}},
        {"column": "gender.gender", "pattern": "comparison_boundary",
         "targets": {"values": ["Female", "female", "Male", "male"]}},
        {"column": "department.department_id", "pattern": "ties_for_order_limit",
         "targets": {"tie_at_rank": [1], "direction": "DESC", "tie_on": ["COUNT(movie_crew.department_id)"]}},
        {"column": "department.department_name", "pattern": "duplicates_for_distinct",
         "targets": {"duplicate_share": "20-50 %"}},
        {"column": "movie.budget", "pattern": "rows_with_different_values",
         "targets": {"qualifying_rows": ">= 2 per group with different values"}},
        {"column": "movie.popularity", "pattern": "rows_with_different_values",
         "targets": {"qualifying_rows": ">= 2 per group with different values"}}
    ],
    "dependencies": [
        {"child": "movie_genres.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_genres.genre_id", "parent": "genre.genre_id", "copied": []},
        {"child": "movie_languages.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_languages.language_id", "parent": "language.language_id", "copied": []},
        {"child": "movie_languages.language_role_id", "parent": "language_role.role_id", "copied": []},
        {"child": "movie_crew.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_crew.person_id", "parent": "person.person_id", "copied": []},
        {"child": "movie_crew.department_id", "parent": "department.department_id", "copied": []},
        {"child": "movie_cast.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_cast.person_id", "parent": "person.person_id", "copied": []},
        {"child": "movie_cast.gender_id", "parent": "gender.gender_id", "copied": []},
        {"child": "production_country.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "production_country.country_id", "parent": "country.country_id", "copied": []},
        {"child": "movie_keywords.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_keywords.keyword_id", "parent": "keyword.keyword_id", "copied": []},
        {"child": "movie_company.movie_id", "parent": "movie.movie_id", "copied": []},
        {"child": "movie_company.company_id", "parent": "production_company.company_id", "copied": []}
    ],
    "semantic_rules_and_formulas": [
        {"table": "movie", "column": "budget", "formula": "budget >= 0"},
        {"table": "movie", "column": "revenue", "formula": "revenue >= 0"},
        {"table": "movie", "column": "runtime", "formula": "runtime > 0"},
        {"table": "movie", "column": "popularity", "formula": "popularity >= 0"},
        {"table": "movie", "column": "vote_average", "formula": "vote_average BETWEEN 0 AND 10"},
        {"table": "movie", "column": "vote_count", "formula": "vote_count >= 0"},
        {"table": "movie", "column": "movie_status",
         "formula": "movie_status IN ('Released','Rumored','Post Production')"},
        {"table": "movie_cast", "column": "cast_order", "formula": "cast_order >= 0"},
        {"table": "movie_cast", "column": "gender_id", "formula": "gender_id IN (0,1,2)"},
        {"table": "gender", "column": "gender", "formula": "gender IN ('Unspecified','Female','Male')"},
        {"table": "language_role", "column": "language_role", "formula": "language_role IN ('Original','Spoken')"},
        {"table": "movie_languages", "column": "language_role_id", "formula": "language_role_id IN (1,2)"}
    ],
    "table_sizes_per_instance": {"country": 20, "department": 12, "gender": 3, "genre": 20, "keyword": 200,
                                 "language": 20, "language_role": 2, "movie": 200, "movie_genres": 400,
                                 "movie_languages": 300, "person": 300, "movie_crew": 600,
                                 "production_company": 100, "production_country": 300, "movie_cast": 600,
                                 "movie_keywords": 400, "movie_company": 300},
    "null_targets": ["movie_cast.movie_id", "movie_company.movie_id", "movie_crew.movie_id",
                     "movie_crew.person_id", "movie_keywords.keyword_id", "movie_languages.movie_id",
                     "movie_genres.movie_id", "production_country.movie_id"]
}


def load_spec(path: str = None) -> dict:
    """Load specification.json if present, else the embedded default."""
    p = path or _SPEC_PATH
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return _DEFAULT


def _split_col(col: str) -> tuple:
    parts = col.split('.')
    if len(parts) == 2:
        return parts[0].lower(), parts[1]
    return None, parts[-1]


def column_exceptions(spec: dict) -> dict:
    """{(table_lower, COLUMN): [exception, ...]}."""
    out: dict = {}
    for ex in spec.get('per_column_exceptions', []):
        t, c = _split_col(ex.get('column', ''))
        if t is None:
            continue
        out.setdefault((t, c), []).append(ex)
    return out


def enum_values(spec: dict) -> dict:
    """{(table_lower, COLUMN): [allowed values]} from IN (...) formulas."""
    out: dict = {}
    for r in spec.get('semantic_rules_and_formulas', []):
        f = r.get('formula', '')
        m = re.search(r'\bIN\s*\(([^)]*)\)', f, re.I)
        if not m:
            continue
        vals = re.findall(r"'((?:[^']|'')*)'", m.group(1))
        if vals:
            out[(r['table'].lower(), r['column'])] = [v.replace("''", "'") for v in vals]
    return out


def numeric_ranges(spec: dict) -> dict:
    """{(table_lower, COLUMN): (lo, hi, is_int)} from simple range formulas."""
    out: dict = {}
    for r in spec.get('semantic_rules_and_formulas', []):
        f = r.get('formula', '')
        key = (r['table'].lower(), r['column'])
        m = re.search(r'BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)', f, re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            out[key] = (lo, hi, lo == int(lo) and hi == int(hi))
            continue
        m = re.search(r'>=\s*(-?\d+(?:\.\d+)?)', f)
        if m:
            out[key] = (float(m.group(1)), None, '.' not in m.group(1))
            continue
        m = re.search(r'>\s*(-?\d+(?:\.\d+)?)', f)
        if m:
            out[key] = (float(m.group(1)) + (1 if '.' not in m.group(1) else 0.0), None, '.' not in m.group(1))
    return out


def table_sizes(spec: dict) -> dict:
    return {k.lower(): int(v) for k, v in spec.get('table_sizes_per_instance', {}).items()}


def null_targets(spec: dict) -> set:
    out = set()
    for c in spec.get('null_targets', []):
        t, col = _split_col(c)
        if t is not None:
            out.add((t, col))
    return out


def spec_pool_literals(spec: dict, schema) -> dict:
    """Route specification literals to (table, COLUMN) pools (tolerant of table-name case)."""
    tlow = {t.lower(): t for t in schema.tables}
    pool: dict = {}

    def add(t, c, v):
        tt = tlow.get(t.lower())
        if tt is None:
            return
        col = next((cm.name for cm in schema.tables[tt].columns if cm.name.lower() == c.lower()), None)
        if col is None:
            return
        pool.setdefault((tt, col), []).append(str(v))

    for ex in spec.get('per_column_exceptions', []):
        t, c = _split_col(ex.get('column', ''))
        if t is None:
            continue
        tg = ex.get('targets', {}) or {}
        for v in tg.get('values', []) or []:
            add(t, c, v)
        for v in tg.get('literals', []) or []:
            add(t, c, v)
            if isinstance(v, str) and v.endswith('%'):
                add(t, c, v[:-1])
        for v in tg.get('variants', []) or []:
            add(t, c, v)
    return pool


def pk_boundary_values(spec: dict, schema) -> dict:
    """{(table, COLUMN): [int boundary values]} for integer PK columns with comparison_boundary targets."""
    out: dict = {}
    for ex in spec.get('per_column_exceptions', []):
        if ex.get('pattern') != 'comparison_boundary':
            continue
        t, c = _split_col(ex.get('column', ''))
        if t is None:
            continue
        tt = next((tn for tn in schema.tables if tn.lower() == t), None)
        if tt is None:
            continue
        col = next((cm for cm in schema.tables[tt].columns if cm.name.lower() == c.lower()), None)
        if col is None or col.pk_pos == 0:
            continue
        if 'int' not in (col.type_str or '').lower():
            continue
        vals = []
        for v in (ex.get('targets', {}) or {}).get('values', []) or []:
            try:
                vals.append(int(v))
            except (TypeError, ValueError):
                pass
        if vals:
            out[(tt, col.name)] = sorted(set(vals))
    return out


def aggregate_targets(spec: dict) -> list:
    """Aggregate-boundary targets (aspirational; recorded but not planted by construction)."""
    out = []
    for ex in spec.get('per_column_exceptions', []):
        if ex.get('pattern') == 'aggregate_boundary':
            out.append(ex)
    return out
