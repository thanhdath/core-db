"""Random instance construction (fuzz/fuzz.py:83-196) + the specification by construction."""
import datetime as dt
import random

from . import spec
from .values import _init_sampler, make_column_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = len(next(iter(columns.values())))
    seen, keep = set(), []
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


def _parent_values(schema, instance: dict, pt: str, pc: str) -> list:
    """Parent key values: compact rows first, then generated rows (in memory)."""
    vals = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's rows (compact or generated) with replacement; empty parent -> NULL
    (fuzz.py:31-35)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_values(schema, instance, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes (Dish 200, Menu 120, MenuPage 180, MenuItem 400), exact."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            sizes[t] = max(0, min(2500, spec.TABLE_SIZES.get(t, 100)))
    return sizes


def _next_pk(schema, instance, table: str, col: str) -> int:
    """Fresh integer key: max(compact, generated) + 1."""
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    vals += [v for v in instance.get(table, {}).get(col, []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _boundary_pool(schema, table: str, col: str) -> list:
    """Boundary literals (literal, one step below, one above) for a column."""
    out = list(spec.BOUNDARY.get((table, col), []))
    for v in list(out):
        if isinstance(v, int):
            out += [v - 1, v + 1]
        elif isinstance(v, float):
            out += [round(v - 0.01, 2), round(v + 0.01, 2)]
        elif isinstance(v, str) and len(v) == 10 and v[4] == '-' and v[7] == '-':
            try:
                d = dt.date.fromisoformat(v)
                out += [(d - dt.timedelta(days=1)).isoformat(), (d + dt.timedelta(days=1)).isoformat()]
            except ValueError:
                pass
    return out


def _plant_boundaries(table: str, col: str, values: list, rng) -> None:
    """Overwrite the first rows with the boundary literals (literal, below, above)."""
    pool = _boundary_pool(None, table, col)
    if not pool or not values:
        return
    for i, v in enumerate(pool[:len(values)]):
        values[i] = v


def _plant_nulls(table: str, col: str, values: list, rng) -> None:
    """NULL rule: at least one NULL row; share follows the compact database."""
    if not values:
        return
    if (table, col) not in spec.NULL_TARGETS:
        return
    if (table, col) in spec.NULL_DOMINANT:
        k_nonnull = max(1, int(round(spec.NULL_DOMINANT_NONNULL_SHARE * len(values))))
        k_nonnull = min(k_nonnull, len(values))
        nonnull_idx = set(rng.sample(range(len(values)), k_nonnull))
        for i in range(len(values)):
            if i not in nonnull_idx:
                values[i] = None
        return
    share = spec.NULL_SHARE.get((table, col), 0.0)
    k = max(1, int(round(share * len(values))))
    k = min(k, len(values))
    idx = rng.sample(range(len(values)), k)
    for i in idx:
        values[i] = None


def _plant_duplicates(table: str, col: str, values: list, rng) -> None:
    """DISTINCT columns: duplicates covering 20-50 % of rows."""
    if (table, col) not in spec.DUPLICATE_COLUMNS or len(values) < 2:
        return
    k = max(1, int(round(spec.DUPLICATE_SHARE * len(values))))
    src = [v for v in values if v is not None]
    if not src:
        return
    for i in rng.sample(range(len(values)), min(k, len(values))):
        values[i] = rng.choice(src)


def _plant_ties(table: str, col: str, values: list, rng) -> None:
    """ORDER BY ..."""
    if (table, col) not in spec.TIE_COLUMNS or len(values) < 2:
        return
    top = max((v for v in values if v is not None), default=None)
    if top is None:
        return
    idx = rng.sample(range(len(values)), 2)
    for i in idx:
        values[i] = top


def _plant_group_distinct(table: str, cols: dict, rng) -> None:
    """Per-FK-group distinct-value coverage: each group with >= 2 children has at least two distinct non-NULL values
    in the value column."""
    for (t, fk, vcol) in spec.GROUP_DISTINCT:
        if t != table or fk not in cols or vcol not in cols:
            continue
        groups: dict = {}
        for i, g in enumerate(cols[fk]):
            if g is not None:
                groups.setdefault(g, []).append(i)
        for g, idxs in groups.items():
            if len(idxs) < 2:
                continue
            vals = [cols[vcol][i] for i in idxs if cols[vcol][i] is not None]
            if len(set(vals)) >= 2:
                continue
            base = vals[0] if vals else 0.0
            cols[vcol][idxs[1]] = round(base + 0.01, 2)


def _fix_formulas(table: str, cols: dict, rng) -> None:
    """Repair rows that violate a semantic formula (NULL operands never touched)."""
    n = len(next(iter(cols.values()))) if cols else 0
    for i in range(n):
        row = {c: v[i] for c, v in cols.items()}
        for f in spec.FORMULAS.get(table, []):
            if f(row):
                continue
            if 'last_appeared' in row and 'first_appeared' in row and row['last_appeared'] is not None \
                    and row['first_appeared'] is not None and row['last_appeared'] < row['first_appeared']:
                cols['last_appeared'][i] = row['first_appeared']
            elif 'highest_price' in row and 'lowest_price' in row and row['highest_price'] is not None \
                    and row['lowest_price'] is not None and row['highest_price'] < row['lowest_price']:
                cols['highest_price'][i] = row['lowest_price']
            elif 'high_price' in row and 'price' in row and row['high_price'] is not None \
                    and row['price'] is not None and row['high_price'] < row['price']:
                cols['high_price'][i] = row['price']
            elif 'page_count' in row and row['page_count'] is not None and row['page_count'] <= 0:
                cols['page_count'][i] = 1
            elif 'page_number' in row and row['page_number'] is not None and row['page_number'] < 0:
                cols['page_number'][i] = 0
            elif 'full_height' in row and row['full_height'] is not None and row['full_height'] <= 0:
                cols['full_height'][i] = 1
            elif 'full_width' in row and row['full_width'] is not None and row['full_width'] <= 0:
                cols['full_width'][i] = 1
            elif 'xpos' in row and row['xpos'] is not None and not (0 <= row['xpos'] <= 1):
                cols['xpos'][i] = min(1.0, max(0.0, row['xpos']))
            elif 'ypos' in row and row['ypos'] is not None and not (0 <= row['ypos'] <= 1):
                cols['ypos'][i] = min(1.0, max(0.0, row['ypos']))
            elif 'status' in row and row['status'] is not None and row['status'] not in ('complete',):
                cols['status'][i] = 'complete'
            elif 'date' in row and row['date'] is not None:
                try:
                    d = dt.date.fromisoformat(str(row['date'])[:10])
                    if not (spec.DATE_LO <= d <= spec.DATE_HI):
                        cols['date'][i] = spec.DATE_LO.isoformat()
                except ValueError:
                    cols['date'][i] = spec.DATE_LO.isoformat()
            elif 'first_appeared' in row and row['first_appeared'] is not None \
                    and not (spec.YEAR_LO <= row['first_appeared'] <= spec.YEAR_HI):
                cols['first_appeared'][i] = spec.YEAR_LO
            elif 'last_appeared' in row and row['last_appeared'] is not None \
                    and not (spec.YEAR_LO <= row['last_appeared'] <= spec.YEAR_HI):
                cols['last_appeared'][i] = spec.YEAR_HI
            elif 'menus_appeared' in row and row['menus_appeared'] is not None and row['menus_appeared'] < 0:
                cols['menus_appeared'][i] = 0
            elif 'times_appeared' in row and row['times_appeared'] is not None and row['times_appeared'] < 0:
                cols['times_appeared'][i] = 0
            elif 'dish_count' in row and row['dish_count'] is not None and row['dish_count'] < 0:
                cols['dish_count'][i] = 0
            elif 'lowest_price' in row and row['lowest_price'] is not None and row['lowest_price'] < 0:
                cols['lowest_price'][i] = 0.0
            elif 'highest_price' in row and row['highest_price'] is not None and row['highest_price'] < 0:
                cols['highest_price'][i] = 0.0
            elif 'price' in row and row['price'] is not None and row['price'] < 0:
                cols['price'][i] = 0.0
            elif 'high_price' in row and row['high_price'] is not None and row['high_price'] < 0:
                cols['high_price'][i] = 0.0


def _special_sampler(table: str, col: str, cm, pool: list, ov: list, rng):
    """Column-specific samplers implementing the specification's domains."""
    key = (table, col)
    if key in spec.ENUMS:
        return make_column_sampler(cm, list(spec.ENUMS[key]) + pool, 0.0, float('inf'), rng)
    if key == ('MenuPage', 'uuid'):
        from .values import UuidSampler
        return UuidSampler(list(spec.BOUNDARY.get(key, [])) + pool, 0.0, float('inf'), rng)
    if key in (('MenuItem', 'created_at'), ('MenuItem', 'updated_at')):
        from .values import TimestampSampler
        return TimestampSampler(pool, 0.0, float('inf'), rng)
    if key in (('Dish', 'lowest_price'), ('Dish', 'highest_price'), ('MenuItem', 'price'),
               ('MenuItem', 'high_price')):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=False, precision=2,
                             lo=spec.PRICE_LO, hi=spec.PRICE_HI)
    if key in (('MenuItem', 'xpos'), ('MenuItem', 'ypos')):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=False, precision=6, lo=0.0, hi=1.0)
    if key in (('Dish', 'first_appeared'), ('Dish', 'last_appeared')):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=True,
                             lo=spec.YEAR_LO, hi=spec.YEAR_HI)
    if key in (('Dish', 'menus_appeared'), ('Dish', 'times_appeared'), ('Menu', 'dish_count')):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=True, lo=0, hi=spec.QUANTITY_HI)
    if key == ('Menu', 'page_count'):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=True, lo=1, hi=spec.QUANTITY_HI)
    if key == ('MenuPage', 'page_number'):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=True, lo=0, hi=spec.QUANTITY_HI)
    if key in (('MenuPage', 'full_height'), ('MenuPage', 'full_width')):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=True, lo=1, hi=10000)
    if key == ('MenuPage', 'image_id'):
        from .values import NumberSampler
        return NumberSampler(pool, 0.0, float('inf'), rng, is_int=False, precision=1, lo=1.0, hi=1e7)
    return None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) with the specification by construction."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                continue
            pool = list(literal_pool.get((t, cm.name), []))
            pool += _boundary_pool(schema, t, cm.name)
            ov = schema.original_values.get((t, cm.name), [])
            sp = _special_sampler(t, cm.name, cm, pool, ov, rng)
            if sp is None:
                sp = _init_sampler(cm, pool, ov, p, rng, len(tm.primary_key))
            samplers[(t, cm.name)] = sp
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for c in tm.primary_key:
            if c in cols and all(isinstance(v, int) for v in cols[c] if v is not None):
                start = _next_pk(schema, inst, t, c)
                cols[c] = [start + i for i in range(n)]
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            if cm.name in cols and not cm.notnull and cm.pk_pos == 0:
                _plant_nulls(t, cm.name, cols[cm.name], rng)
        for cm in tm.columns:
            if cm.name not in cols:
                continue
            _plant_duplicates(t, cm.name, cols[cm.name], rng)
            _plant_boundaries(t, cm.name, cols[cm.name], rng)
            _plant_ties(t, cm.name, cols[cm.name], rng)
        _plant_group_distinct(t, cols, rng)
        _fix_formulas(t, cols, rng)
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    _ensure_unmatched(schema, inst, rng)
    return {t: inst[t] for t in schema.tables}


def _ensure_unmatched(schema, inst: dict, rng) -> None:
    """Parent rows without children and child rows with NULL FK (unmatched joins)."""
    for pt, (ct, cc) in spec.GROUP_SIZE_TARGETS.items():
        if pt not in inst or ct not in inst:
            continue
        pkeys = [v for v in inst[pt].get('id', []) if v is not None]
        if not pkeys:
            continue
        used = set(v for v in inst[ct].get(cc, []) if v is not None)
        free = [k for k in pkeys if k not in used]
        if not free:
            for i, v in enumerate(inst[ct].get(cc, [])):
                if v is not None:
                    inst[ct][cc][i] = None
                    break
    for ct, cc in spec.NULL_FK:
        if ct in inst and cc in inst[ct] and inst[ct][cc]:
            if all(v is not None for v in inst[ct][cc]):
                inst[ct][cc][rng.randrange(len(inst[ct][cc]))] = None
