"""Random instance construction (fuzz/fuzz.py:83-196) adapted to append rows to a compact database."""
import datetime as dt
import re

from .values import _init_sampler, make_column_sampler

TABLE_SIZES = {'Categories': 8, 'Customers': 20, 'Employees': 10, 'Shippers': 3, 'Suppliers': 12,
               'Products': 30, 'Orders': 40, 'OrderDetails': 80}

NULL_TARGETS = {'Orders.EmployeeID', 'Products.SupplierID', 'Customers.City', 'Products.CategoryID',
                'Orders.CustomerID', 'Orders.ShipperID'}
NON_NULL_FORCED = {'Employees.BirthDate', 'Orders.OrderDate', 'Products.Price', 'OrderDetails.Quantity',
                   'Products.ProductName', 'Categories.CategoryName', 'Suppliers.SupplierName',
                   'Shippers.ShipperName', 'OrderDetails.OrderID', 'OrderDetails.ProductID'}

NULL_SHARE = 0.15
DUP_SHARE = 0.30
NEAR_VARIANT_SHARE = 0.10

ORDER_DATE_LITERALS = ['1996-08%', '1996-08-01']
ORDER_DATE_VARIANTS = ['1996-07-31', '1996-08-31', '1996-09-01']
CATEGORY_DESC_LITERALS = ['%Soft drinks%', 'Soft drinks, coffees, teas, beers, and ales']
CATEGORY_DESC_VARIANTS = ['Soft drinks', 'Soft drinkt', 'Soft drinks x', 'soft drinks']

LASTNAME_BOUNDARY = ['Suyama', 'suyama', 'Peacock', 'peacock']


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


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes, jittered per instance (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 20)
        jitter = int(base * 0.25)
        sizes[t] = max(0, min(230, base + rng.randint(-jitter, jitter)))
    return sizes


def _is_nullable(schema, table: str, col: str) -> bool:
    """A column may receive NULL only if it is a null_target or the compact DB has NULLs in it."""
    key = '%s.%s' % (table, col)
    if key in NON_NULL_FORCED:
        return False
    if key in NULL_TARGETS:
        return True
    vals = schema.original_values.get((table, col), [])
    return any(v is None for v in vals)


def _apply_null_rule(table: str, col: str, values: list, rng, protected: set) -> list:
    """Plant NULLs on nullable columns: at least one NULL, share ~NULL_SHARE (5-30 %)."""
    if not values:
        return values
    n = len(values)
    k = max(1, int(round(n * NULL_SHARE)))
    k = min(k, n - 1) if n > 1 else 1
    candidates = [i for i in range(n) if i not in protected]
    if not candidates:
        return values
    k = min(k, len(candidates))
    idx = set(rng.sample(candidates, k))
    return [None if i in idx else v for i, v in enumerate(values)]


def _near_variant(v: str, rng) -> str:
    """Case change / trailing char / truncation variant of a string."""
    if not isinstance(v, str) or not v:
        return v
    u = rng.random()
    if u < 0.25:
        return v.lower()
    if u < 0.5:
        return v.upper()
    if u < 0.75:
        return v + rng.choice('xXzZ ')
    return v[:-1] if len(v) > 1 else v + 'x'


def _apply_duplicates(values: list, rng, protected: set, share: float = DUP_SHARE) -> list:
    """Force a duplicate share on a DISTINCT-targeted column (20-50 %)."""
    if len(values) < 2:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    src = list(values)
    cand = [i for i in range(n) if i not in protected]
    if not cand:
        return values
    for i in rng.sample(cand, min(k, len(cand))):
        j = rng.randrange(n)
        if j != i and values[j] is not None:
            values[i] = values[j]
    return values


def _apply_near_variants(values: list, rng, protected: set, share: float = NEAR_VARIANT_SHARE) -> list:
    if not values:
        return values
    n = len(values)
    k = max(1, int(round(n * share)))
    cand = [i for i in range(n) if i not in protected and values[i] is not None]
    for i in rng.sample(candidates := cand, min(k, len(candidates))) if cand else []:
        values[i] = _near_variant(values[i], rng)
    return values


def _apply_group_sizes(values: list, rng, protected: set) -> list:
    """Group sizes 1, 2 and >= 3 across rows (Employees.FirstName / Notes)."""
    if len(values) < 6:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    a, b, c = rng.choice(pool), rng.choice(pool), rng.choice(pool)
    out = list(values)
    out[0] = a
    out[1] = b
    out[2] = b
    out[3] = c
    out[4] = c
    out[5] = c
    protected.update(range(6))
    return out


def _apply_ties(values: list, rng, protected: set) -> list:
    """Tie at rank 1 for ORDER BY COUNT(*) DESC: make the most frequent value shared."""
    if len(values) < 4:
        return values
    pool = [v for v in values if v is not None]
    if not pool:
        return values
    a, b = rng.choice(pool), rng.choice(pool)
    out = list(values)
    out[0] = a
    out[1] = a
    out[2] = b
    out[3] = b
    protected.update(range(4))
    return out


def _apply_comparison_boundary(values: list, rng, protected: set, boundary: list) -> list:
    """Plant the exact boundary literals (and case variants) so =, >=, <= differ."""
    if not values:
        return values
    out = list(values)
    for i, lit in enumerate(boundary):
        if i < len(out):
            out[i] = lit
            protected.add(i)
    return out


def _apply_like_variants(values: list, rng, protected: set, literals: list, variants: list) -> list:
    """Plant values that match the LIKE pattern but differ from the exact literal, plus boundary days."""
    if not values:
        return values
    out = list(values)
    seq = list(literals) + list(variants)
    for i, lit in enumerate(seq):
        if i < len(out):
            out[i] = lit
            protected.add(i)
    return out


def _apply_rows_with_different_values(values: list, rng, protected: set) -> list:
    """Ensure >= 2 rows per group carry different values (distinct dates)."""
    if len(values) < 2:
        return values
    out = list(values)
    seen = set()
    for i, v in enumerate(out):
        if v in seen:
            if isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                d = dt.date.fromisoformat(v) + dt.timedelta(days=rng.randint(1, 30))
                out[i] = d.isoformat()
            elif isinstance(v, (int, float)):
                out[i] = v + rng.randint(1, 5)
            protected.add(i)
        seen.add(out[i])
    return out


def _parent_keys(instance: dict, schema, table: str, col: str) -> list:
    """Compact + generated parent key values (in memory)."""
    pt, pc = schema.fks[(table, col)]
    vals = list(schema.original_values.get((pt, pc), []))
    vals += [v for v in instance.get(pt, {}).get(pc, []) if v is not None]
    return vals


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pv = _parent_keys(instance, schema, table, cm.name)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of *new* rows to append to the compact database (fuzz.py:111-196)."""
    p = 0.0 if rng.random() < 0.3 else 0.2
    order = [t for lvl in schema.table_order for t in lvl]
    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if (t, cm.name) not in schema.fks:
                samplers[(t, cm.name)] = _init_sampler(cm, literal_pool.get((t, cm.name), []),
                                                       schema.original_values.get((t, cm.name), []), p, rng,
                                                       len(tm.primary_key))
    if size is None:
        size = choose_table_sizes(schema, rng)
    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        inst[t] = cols
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
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
    inst = {t: inst[t] for t in schema.tables}
    _apply_specification(schema, inst, rng)
    return inst


def _apply_specification(schema, inst: dict, rng) -> None:
    """Apply the NULL rule first, then per-column specification patterns (excluding NULL positions)."""
    for t, tm in schema.tables.items():
        if t not in inst:
            continue
        for cm in tm.columns:
            if cm.pk_pos > 0:
                continue
            if not _is_nullable(schema, t, cm.name):
                continue
            if cm.name in inst[t]:
                inst[t][cm.name] = _apply_null_rule(t, cm.name, inst[t][cm.name], rng, set())

    def prot(t, c):
        return {i for i, v in enumerate(inst[t].get(c, [])) if v is None}

    if 'Products' in inst and 'ProductName' in inst['Products']:
        pr = prot('Products', 'ProductName')
        inst['Products']['ProductName'] = _apply_duplicates(inst['Products']['ProductName'], rng, pr)
        inst['Products']['ProductName'] = _apply_ties(inst['Products']['ProductName'], rng, pr)
    if 'Categories' in inst and 'CategoryName' in inst['Categories']:
        pr = prot('Categories', 'CategoryName')
        inst['Categories']['CategoryName'] = _apply_duplicates(inst['Categories']['CategoryName'], rng, pr)
    if 'Suppliers' in inst and 'Country' in inst['Suppliers']:
        pr = prot('Suppliers', 'Country')
        inst['Suppliers']['Country'] = _apply_duplicates(inst['Suppliers']['Country'], rng, pr)
    if 'Suppliers' in inst and 'ContactName' in inst['Suppliers']:
        pr = prot('Suppliers', 'ContactName')
        inst['Suppliers']['ContactName'] = _apply_duplicates(inst['Suppliers']['ContactName'], rng, pr)
    if 'Orders' in inst and 'ShipperID' in inst['Orders']:
        pr = prot('Orders', 'ShipperID')
        inst['Orders']['ShipperID'] = _apply_duplicates(inst['Orders']['ShipperID'], rng, pr)

    if 'Employees' in inst:
        e = inst['Employees']
        if 'FirstName' in e:
            pr = prot('Employees', 'FirstName')
            e['FirstName'] = _apply_group_sizes(e['FirstName'], rng, pr)
            e['FirstName'] = _apply_ties(e['FirstName'], rng, pr)
        if 'LastName' in e:
            pr = prot('Employees', 'LastName')
            e['LastName'] = _apply_ties(e['LastName'], rng, pr)
            e['LastName'] = _apply_comparison_boundary(e['LastName'], rng, pr, LASTNAME_BOUNDARY)
        if 'Notes' in e:
            pr = prot('Employees', 'Notes')
            e['Notes'] = _apply_group_sizes(e['Notes'], rng, pr)
        if 'BirthDate' in e:
            pr = prot('Employees', 'BirthDate')
            e['BirthDate'] = _apply_rows_with_different_values(e['BirthDate'], rng, pr)

    if 'Orders' in inst and 'OrderDate' in inst['Orders']:
        pr = prot('Orders', 'OrderDate')
        inst['Orders']['OrderDate'] = _apply_like_variants(inst['Orders']['OrderDate'], rng, pr,
                                                           ORDER_DATE_LITERALS, ORDER_DATE_VARIANTS)
    if 'Categories' in inst and 'Description' in inst['Categories']:
        pr = prot('Categories', 'Description')
        inst['Categories']['Description'] = _apply_like_variants(inst['Categories']['Description'], rng, pr,
                                                                 CATEGORY_DESC_LITERALS, CATEGORY_DESC_VARIANTS)
