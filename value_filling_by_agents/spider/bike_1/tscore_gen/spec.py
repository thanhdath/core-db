"""Specification model: per-column domains, NULL targets, dependencies and semantic rules."""
import json
import re

DEFAULT_DOMAINS = {
    ('station', 'id'): ('int_seq', 1, 5000),
    ('station', 'name'): ('text', ["San Jose Diridon Caltrain Station", "San Jose Civic Center",
                                   "Santa Clara at Almaden", "Adobe on Almaden", "San Pedro Square",
                                   "Paseo de San Antonio", "San Salvador at 1st", "Japantown"]),
    ('station', 'lat'): ('numeric', [37.329732, 37.330698, 37.333988, 37.331415, 37.336721,
                                     37.333798, 37.330165, 37.348742]),
    ('station', 'long'): ('numeric', [-121.901782, -121.888979, -121.894902, -121.8932,
                                      -121.894074, -121.886943, -121.885831, -121.894715]),
    ('station', 'dock_count'): ('int_pool', [11, 15, 19, 23, 25, 27]),
    ('station', 'city'): ('enum', ["San Jose", "Redwood City", "Mountain View", "Palo Alto",
                                   "San Francisco"]),
    ('station', 'installation_date'): ('date', ["8/3/2013", "8/4/2013", "8/5/2013", "8/6/2013",
                                                "8/7/2013", "8/8/2013", "8/12/2013", "8/13/2013",
                                                "8/14/2013", "8/15/2013", "8/16/2013", "12/30/2013",
                                                "12/31/2013", "1/1/2014"]),
    ('status', 'station_id'): ('fk', 1, 5000),
    ('status', 'bikes_available'): ('int_pool', list(range(0, 19))),
    ('status', 'docks_available'): ('int_pool', list(range(0, 27))),
    ('status', 'time'): ('date', ["2015-06-02 12:46:02", "2015-06-02 12:47:02", "2015-06-02 12:48:02",
                                  "2015-06-02 12:49:02", "2015-06-02 12:50:02", "2015-06-02 12:51:02",
                                  "2015-06-02 12:52:02", "2015-06-02 12:53:03"]),
    ('trip', 'id'): ('int_seq', 900504, 1200000),
    ('trip', 'duration'): ('int_pool', [196, 362, 384, 528, 588, 823, 984, 1059]),
    ('trip', 'start_date'): ('date', ["8/21/2015 17:03", "8/21/2015 17:04", "8/21/2015 17:05",
                                      "8/21/2015 17:06", "8/21/2015 17:07", "8/21/2015 17:08",
                                      "8/21/2015 17:09", "8/21/2015 17:10"]),
    ('trip', 'start_station_name'): ('text', ["Howard at 2nd", "South Van Ness at Market",
                                              "Market at Sansome", "Washington at Kearny",
                                              "Beale at Market", "Clay at Battery",
                                              "Embarcadero at Vallejo", "Davis at Jackson"]),
    ('trip', 'start_station_id'): ('fk', 1, 5000),
    ('trip', 'end_date'): ('date', ["8/21/2015 17:10", "8/21/2015 17:13", "8/21/2015 17:07",
                                    "8/21/2015 17:18", "8/21/2015 17:22", "8/21/2015 17:11",
                                    "8/21/2015 17:14", "8/21/2015 17:21"]),
    ('trip', 'end_station_name'): ('text', ["San Francisco Caltrain 2 (330 Townsend)",
                                            "Harry Bridges Plaza (Ferry Building)", "2nd at Townsend",
                                            "San Francisco Caltrain (Townsend at 4th)", "Howard at 2nd",
                                            "Temporary Transbay Terminal (Howard at Beale)",
                                            "Market at Sansome", "Townsend at 7th"]),
    ('trip', 'end_station_id'): ('fk', 1, 5000),
    ('trip', 'bike_id'): ('int_pool', [16, 67, 187, 363, 427, 454, 574, 636]),
    ('trip', 'subscription_type'): ('enum', ["Subscriber", "Customer"]),
    ('trip', 'zip_code'): ('int_pool', [94010, 94041, 94087, 94103, 94107, 94608, 94925, 95119]),
    ('weather', 'date'): ('date', ["8/29/2013", "8/30/2013", "8/31/2013", "9/1/2013", "9/2/2013",
                                   "9/3/2013", "9/4/2013", "9/5/2013"]),
    ('weather', 'max_temperature_f'): ('int_pool', [71, 72, 73, 74, 75, 78, 85, 88]),
    ('weather', 'mean_temperature_f'): ('int_pool', [64, 65, 66, 67, 68, 69, 71, 73]),
    ('weather', 'min_temperature_f'): ('int_pool', [55, 56, 57, 58, 59, 60, 61, 62]),
    ('weather', 'max_dew_point_f'): ('int_pool', [55, 56, 57, 58, 59, 60, 61, 64]),
    ('weather', 'mean_dew_point_f'): ('int_pool', [51, 53, 54, 55, 56, 57, 58, 60]),
    ('weather', 'min_dew_point_f'): ('int_pool', [45, 46, 51, 52, 53, 54, 56, 58]),
    ('weather', 'max_humidity'): ('int_pool', [77, 78, 83, 84, 86, 87, 90, 93]),
    ('weather', 'mean_humidity'): ('int_pool', [58, 65, 68, 70, 72, 74, 75, 77]),
    ('weather', 'min_humidity'): ('int_pool', [29, 31, 46, 49, 50, 53, 57, 61]),
    ('weather', 'max_sea_level_pressure_inches'): ('numeric', [29.88, 29.96, 29.97, 30.0, 30.02,
                                                               30.04, 30.05, 30.07]),
    ('weather', 'mean_sea_level_pressure_inches'): ('numeric', [29.92, 29.93, 29.94, 29.96, 29.98,
                                                                30.0, 30.01, 30.02]),
    ('weather', 'min_sea_level_pressure_inches'): ('numeric', [29.81, 29.83, 29.9, 29.91, 29.92,
                                                               29.93, 29.95, 29.97]),
    ('weather', 'max_visibility_miles'): ('int_pool', [6, 8, 9, 10, 15, 19, 20]),
    ('weather', 'mean_visibility_miles'): ('int_pool', [4, 5, 6, 7, 8, 9, 10, 13]),
    ('weather', 'min_visibility_miles'): ('int_pool', [0, 2, 4, 6, 7, 8, 9, 10]),
    ('weather', 'max_wind_Speed_mph'): ('int_pool', [17, 21, 23, 24, 25, 26, 29, 31]),
    ('weather', 'mean_wind_speed_mph'): ('int_pool', [8, 9, 11, 12, 13, 15, 19, 21]),
    ('weather', 'max_gust_speed_mph'): ('int_pool', [21, 25, 28, 29, 30, 31, 35, 37]),
    ('weather', 'precipitation_inches'): ('numeric', [0, 0.01, 0.06, 0.23, 0.28, 0.29, 0.63]),
    ('weather', 'cloud_cover'): ('int_pool', [0, 1, 2, 3, 4, 5, 6, 7]),
    ('weather', 'events'): ('enum', ["", "Fog", "Rain", "Fog-Rain", "rain", "Rain-Thunderstorm"]),
    ('weather', 'wind_dir_degrees'): ('int_pool', [269, 270, 276, 277, 284, 286, 287, 291]),
    ('weather', 'zip_code'): ('int_pool', [94041, 94063, 94107, 94301, 95113]),
}

DEFAULT_NULL_TARGETS = [('status', 'station_id'), ('trip', 'start_station_id'),
                        ('trip', 'end_station_id'), ('trip', 'zip_code'), ('weather', 'zip_code')]

DEFAULT_RULES = [
    ('station', 'id', 'gt', 0),
    ('station', 'dock_count', 'gt', 0),
    ('station', 'lat', 'between', (-90, 90)),
    ('station', 'long', 'between', (-180, 180)),
    ('station', 'city', 'in', ["San Jose", "Redwood City", "Mountain View", "Palo Alto", "San Francisco"]),
    ('status', 'bikes_available', 'ge', 0),
    ('status', 'docks_available', 'ge', 0),
    ('trip', 'duration', 'gt', 0),
    ('trip', 'end_date', 'ge_col', 'start_date'),
    ('trip', 'subscription_type', 'in', ["Subscriber", "Customer"]),
    ('weather', 'max_temperature_f', 'ge_col', 'mean_temperature_f'),
    ('weather', 'mean_temperature_f', 'ge_col', 'min_temperature_f'),
    ('weather', 'max_dew_point_f', 'ge_col', 'mean_dew_point_f'),
    ('weather', 'mean_dew_point_f', 'ge_col', 'min_dew_point_f'),
    ('weather', 'max_humidity', 'ge_col', 'mean_humidity'),
    ('weather', 'mean_humidity', 'ge_col', 'min_humidity'),
    ('weather', 'max_sea_level_pressure_inches', 'ge_col', 'mean_sea_level_pressure_inches'),
    ('weather', 'mean_sea_level_pressure_inches', 'ge_col', 'min_sea_level_pressure_inches'),
    ('weather', 'max_visibility_miles', 'ge_col', 'mean_visibility_miles'),
    ('weather', 'mean_visibility_miles', 'ge_col', 'min_visibility_miles'),
    ('weather', 'max_wind_Speed_mph', 'ge_col', 'mean_wind_speed_mph'),
    ('weather', 'max_gust_speed_mph', 'ge_col', 'max_wind_Speed_mph'),
    ('weather', 'precipitation_inches', 'ge', 0),
    ('weather', 'cloud_cover', 'between', (0, 8)),
    ('weather', 'wind_dir_degrees', 'between', (0, 360)),
    ('weather', 'events', 'in', ["", "Fog", "Rain", "Fog-Rain", "rain", "Rain-Thunderstorm"]),
]

DEFAULT_COPIED = [('trip', 'start_station_id', 'station', 'id', 'start_station_name'),
                  ('trip', 'end_station_id', 'station', 'id', 'end_station_name')]

DEFAULT_SIZES = {'station': 70, 'status': 8487, 'trip': 9959, 'weather': 3665}

PK_START_TABLES = {'station': 'id', 'trip': 'id'}


def _infer_domain(column, observed: list):
    """Derive a domain from the compact column when the specification has no entry."""
    t = (column.type_str or '').lower()
    vals = [v for v in observed if v is not None]
    if column.pk_pos > 0:
        ints = [int(v) for v in vals if isinstance(v, (int, float))]
        lo = min(ints) if ints else 1
        hi = max(ints) if ints else max(lo + 1, 1)
        return ('int_seq', lo, max(hi, lo + 5000))
    if 'int' in t:
        ints = [int(v) for v in vals if isinstance(v, (int, float))]
        if ints:
            return ('int_pool', sorted(set(ints)))
        return ('int_pool', [0, 1, 2])
    if any(k in t for k in ('numeric', 'real', 'float', 'double', 'decimal')):
        nums = [float(v) for v in vals if isinstance(v, (int, float))]
        return ('numeric', sorted(set(nums)) or [0.0, 1.0])
    if 'date' in t or 'time' in t:
        return ('date', [str(v) for v in vals][:16] or ['1/1/2014'])
    return ('text', [str(v) for v in vals][:8] or ['a', 'b'])


def spec_from_columns(schema) -> dict:
    """Build the specification dict from the compact database's observed columns."""
    domains = {}
    for t, tm in schema.tables.items():
        for c in tm.columns:
            key = (t, c.name)
            if key in DEFAULT_DOMAINS:
                domains[key] = DEFAULT_DOMAINS[key]
            else:
                domains[key] = _infer_domain(c, schema.original_values.get(key, []))
    return {'domains': domains, 'null_targets': list(DEFAULT_NULL_TARGETS),
            'rules': list(DEFAULT_RULES), 'copied': list(DEFAULT_COPIED),
            'sizes': dict(DEFAULT_SIZES)}


def _coerce_domain(v):
    """Normalise a spec domain entry to a tuple; '*' placeholders become 0."""
    if isinstance(v, str):
        return (v,)
    if not isinstance(v, (list, tuple)):
        return ('text', ['a', 'b'])
    if len(v) == 2 and isinstance(v[1], list):
        return (v[0], list(v[1]))
    if len(v) == 3:
        return (v[0], v[1], v[2])
    return tuple(v)


def load_specification(path: str, schema=None) -> dict:
    """Read a JSON specification written by the pipeline (keys are 'table.column')."""
    with open(path) as f:
        raw = json.load(f)
    domains = {}
    for k, v in (raw.get('domains') or {}).items():
        t, c = k.split('.', 1)
        domains[(t, c)] = _coerce_domain(v)
    null_targets = [tuple(x.split('.', 1)) for x in raw.get('null_targets', [])]
    rules = [tuple(r) for r in raw.get('rules', [])]
    copied = [tuple(x) for x in raw.get('copied', [])]
    sizes = raw.get('sizes') or {}
    if schema is not None:
        for t, pk in PK_START_TABLES.items():
            if t not in schema.tables:
                continue
            key = (t, pk)
            mx = schema.pk_max.get(key)
            if not isinstance(mx, (int, float)):
                continue
            for tpk in schema.tables[t].primary_key:
                pass
            size = int(sizes.get(t, DEFAULT_SIZES.get(t, 230)))
            lo = int(mx) + 1
            hi = lo + max(size, 230) + 10
            kind = domains.get(key, ('int_seq',))[0] if key in domains else 'int_seq'
            domains[key] = ('int_seq', lo, hi) if kind == 'int_seq' else domains.get(key, ('int_seq', lo, hi))
    return {'domains': domains, 'null_targets': null_targets, 'rules': rules,
            'copied': copied, 'sizes': sizes}


def domain_for(spec: dict, table: str, column: str):
    """Domain tuple for a column, falling back to a text pool."""
    return spec['domains'].get((table, column), ('text', ['a', 'b']))


def rules_for(spec: dict, table: str) -> list:
    """Semantic rules of one table."""
    return [r for r in spec['rules'] if r[0] == table]


def copied_for(spec: dict, table: str) -> list:
    """Copied-column dependencies of one table: (child_col, parent_table, parent_col, copy_col)."""
    return [(c, pt, pc, cp) for (t, c, pt, pc, cp) in spec['copied'] if t == table]


def null_share(schema, table: str, column: str) -> float:
    """NULL share of the compact column (0.5% when it has no NULLs so NULL rows still exist)."""
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.005
    share = sum(1 for v in vals if v is None) / float(len(vals))
    return share if share > 0 else 0.005


def is_null_target(spec: dict, table: str, column: str) -> bool:
    """True if the column is a NULL target of the specification."""
    return (table, column) in set(spec['null_targets'])


def is_nullable_column(schema, table: str, column: str) -> bool:
    """True if the compact schema declares the column nullable (not NOT NULL, not PK)."""
    tm = schema.tables.get(table)
    if tm is None:
        return False
    for cm in tm.columns:
        if cm.name == column:
            return not cm.notnull and cm.pk_pos == 0
    return False


def like_patterns(spec: dict) -> list:
    """LIKE patterns without '%' derived from date domains (near-variant support)."""
    out = []
    for (t, c), d in spec['domains'].items():
        if d and d[0] == 'date':
            for v in d[1][:4]:
                m = re.match(r'(\d+)/', str(v))
                if m:
                    out.append((t, c, m.group(1) + '%'))
    return out
