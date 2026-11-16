"""Random instance construction (fuzz/fuzz.py:83-196) adapted to the specification."""
import random

from . import spec
from .values import _init_sampler

SPEC_SIZES = {'chip_model': 14, 'screen_mode': 7, 'phone': 8}

NULL_SHARE = 0.1


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict, existing: set = frozenset()) -> dict:
    """Drop rows whose PK tuple repeats (or collides with a compact row), first occurrence kept."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(existing), []
    for i in range(n):
        k = tuple(columns[c][i] for c in table_meta.primary_key)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return _filter(columns, keep)


def drop_unique_duplicates(table_meta, columns: dict) -> dict:
    """Drop rows repeating any single unique column value (fuzz.py:192-195)."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Parent values: compact rows (schema.original_values) plus generated rows."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: float = NULL_SHARE) -> dict:
    """FK child columns draw from the parent's rows or are NULL (NULL rule)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        col = []
        for _ in range(n):
            if pv and rng.random() >= null_share:
                col.append(rng.choice(pv))
            else:
                col.append(None)
        if pv and all(v is not None for v in col) and col:
            col[rng.randrange(len(col))] = None
        out[cm.name] = col
    return out


def apply_null_rule(table_meta, columns: dict, rng, null_share: float = NULL_SHARE) -> dict:
    """NULL rule: every nullable non-PK column gets NULL in ~null_share of rows, at least one."""
    if not columns:
        return columns
    n = len(next(iter(columns.values())))
    if n == 0:
        return columns
    pk = set(table_meta.primary_key)
    for cm in table_meta.columns:
        if cm.name not in columns or cm.name in pk or cm.notnull:
            continue
        col = columns[cm.name]
        idx = [i for i in range(n) if rng.random() < null_share]
        if not idx:
            idx = [rng.randrange(n)]
        for i in idx:
            col[i] = None
    return columns


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with per-instance variation (0-230 rows, level x4 capped at 2500)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = SPEC_SIZES.get(t)
            if base is None:
                base = int(30 * rng.random() + int(rng.random() * 200))
            sizes[t] = max(0, base + rng.randint(-2, 2))
    return sizes


def _spec_sampler(table: str, col: str, n: int, rng, existing: set):
    """Return a list of n values for a non-FK column, by construction from the specification."""
    if table == 'chip_model':
        if col == 'Model_name':
            return spec.chip_model_names(n, rng, existing)
        if col == 'Launch_year':
            return spec.launch_years(n, rng)
        if col == 'RAM_MiB':
            return spec.ram_values(n, rng)
        if col == 'ROM_MiB':
            return spec.rom_values(n, rng)
        if col == 'Slots':
            return spec.enum_values(n, spec.SLOTS_ENUM, rng)
        if col == 'WiFi':
            return spec.duplicate_share_values(n, spec.WIFI_ENUM, rng)
        if col == 'Bluetooth':
            return spec.enum_values(n, spec.BLUETOOTH_ENUM, rng)
    if table == 'screen_mode':
        if col == 'Graphics_mode':
            return spec.graphics_modes(n, rng, existing)
        if col == 'Char_cells':
            return spec.duplicate_share_values(n, spec.CHAR_CELLS, rng)
        if col == 'Pixels':
            return spec.duplicate_share_values(n, spec.PIXELS, rng)
        if col == 'Hardware_colours':
            return spec.enum_values(n, spec.HW_COLOURS, rng)
        if col == 'used_kb':
            return spec.used_kb_values(n, rng)
        if col == 'map':
            return spec.duplicate_share_values(n, spec.MAPS, rng)
        if col == 'Type':
            return spec.type_values(n, rng)
    if table == 'phone':
        if col == 'Company_name':
            return spec.company_values(n, rng)
        if col == 'Hardware_Model_name':
            return spec.hw_model_names(n, rng, existing)
        if col == 'Accreditation_type':
            return spec.accreditation_types(n, rng)
        if col == 'Accreditation_level':
            return spec.accreditation_levels(n, rng)
        if col == 'Date':
            return spec.date_values(n, rng)
    return None


def _fallback_sampler(schema, table: str, col: str, literal_pool: dict, rng, n: int) -> list:
    """Generic library sampler for columns without a specification rule."""
    tm = schema.tables[table]
    cm = next(c for c in tm.columns if c.name == col)
    s = _init_sampler(cm, literal_pool.get((table, col), []),
                      schema.original_values.get((table, col), []), 0.2, rng,
                      len(tm.primary_key))
    return [s.sample() for _ in range(n)]


def _existing_pk(schema, table: str) -> set:
    tm = schema.tables[table]
    if not tm.primary_key:
        return set()
    cols = [schema.original_values.get((table, c), []) for c in tm.primary_key]
    n = min((len(c) for c in cols), default=0)
    return {tuple(c[i] for c in cols) for i in range(n)}


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with specification samplers."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        existing = _existing_pk(schema, t)
        cols: dict = {}
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            vals = _spec_sampler(t, cm.name, n, rng, existing)
            if vals is None:
                vals = _fallback_sampler(schema, t, cm.name, literal_pool, rng, n)
            cols[cm.name] = vals
        inst[t] = cols
        fk_cols = fill_foreign_keys_consistently(inst, schema, t, n, rng)
        cols.update(fk_cols)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns}, existing)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = apply_null_rule(tm, cols, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
