"""Row generation by construction (specification implemented in Python, no SQL evaluation)."""
import string

from .schema import q
from .spec import table_size

_CHARS = string.ascii_letters + ' ' + string.digits


def _perturb_num(v, rng):
    r = rng.random()
    if r < 1 / 6:
        return v + 1
    if r < 1 / 3:
        return v - 1
    if r < 1 / 2:
        return v + 2
    if r < 2 / 3:
        return v - 2
    return v


def _perturb_str(v, rng):
    r = rng.random()
    if r < 0.2:
        return v + ''.join(rng.choice(_CHARS) for _ in range(3))
    if r < 0.4:
        return ''.join(rng.choice(_CHARS) for _ in range(3)) + v
    if r < 0.6 and len(v) > 1:
        return v[:-1]
    if r < 0.8 and len(v) > 1:
        return v[1:]
    return v


def _rand_str(rng, n=12):
    return ''.join(rng.choice(_CHARS) for _ in range(n))


class ColumnGen:
    """Stateful per-column generator: pool + fresh values + duplicate share."""

    def __init__(self, plan, extra_pool, rng):
        self.plan = plan
        self.rng = rng
        self.pool = [str(x) for x in plan['pool']] + [str(x) for x in extra_pool]
        self.vocab = [str(x) for x in plan['vocab']]
        self.boundary = list(plan['boundary'])
        self.like_lits = list(plan['like_lits'])
        self.drawn = []
        self.fresh = []
        self.max_fresh = rng.randint(5, 30)
        self.kind = plan['kind']
        self.lo, self.hi = plan['lo'], plan['hi']
        self.null_share = plan['null_share']
        self.dup_share = plan['dup_share']

    def _draw(self):
        r = self.rng
        k = self.kind
        if k in ('int', 'year'):
            if self.boundary and r.random() < 0.3:
                return r.choice(self.boundary)
            if self.pool and r.random() < 0.3:
                try:
                    return int(float(r.choice(self.pool)))
                except (TypeError, ValueError):
                    pass
            lo = self.lo if self.lo is not None else 0
            hi = self.hi if self.hi is not None else 1000
            v = r.randint(lo, hi)
            return _perturb_num(v, r)
        if self.like_lits and r.random() < 0.3:
            base = r.choice(self.like_lits)
            u = r.random()
            if u < 0.5:
                return base
            if u < 0.75:
                return base.lower()
            return base + ' x'
        if self.boundary and r.random() < 0.25:
            return r.choice(self.boundary)
        if self.pool and r.random() < 0.3:
            return _perturb_str(r.choice(self.pool), r)
        if self.vocab and r.random() < 0.5:
            return _perturb_str(r.choice(self.vocab), r)
        if k == 'url':
            return 'http://example.org/' + _rand_str(r, 8)
        if k == 'keyword':
            return '; '.join(_rand_str(r, 6) for _ in range(r.randint(1, 3)))
        return _rand_str(r, r.randint(4, 20))

    def sample(self):
        r = self.rng
        if self.null_share > 0 and r.random() < self.null_share:
            return None
        if self.drawn and r.random() < self.dup_share:
            return r.choice(self.drawn)
        if self.fresh and len(self.fresh) > self.max_fresh:
            v = r.choice(self.fresh)
        else:
            v = self._draw()
            self.fresh.append(v)
        self.drawn.append(v)
        return v


def _pk_start(schema, table):
    """First free integer PK value (max existing + 1) for a single-column int PK."""
    tm = schema.tables[table]
    if len(tm.primary_key) != 1:
        return None
    pk = tm.primary_key[0]
    vals = [v for v in schema.original_values.get((table, pk), []) if isinstance(v, int)]
    return (max(vals) + 1) if vals else 1


def _plant_pk_sequence(schema, table, plan, extra_pool, rng, n):
    """Sequential integer PKs starting after the compact max, with boundary literals from the spec planted in-order
    while keeping uniqueness."""
    start = _pk_start(schema, table) or 1
    taken = set(v for v in schema.original_values.get((table, table.lower() == 'paper' and 'Id' or 'Id'), [])
                if isinstance(v, int))
    tm = schema.tables[table]
    pk = tm.primary_key[0]
    taken = set(v for v in schema.original_values.get((table, pk), []) if isinstance(v, int))
    boundary = [b for b in plan.get('boundary', []) if isinstance(b, int) and b > 0 and b not in taken]
    extra_ints = []
    for v in extra_pool:
        try:
            iv = int(float(v))
        except (TypeError, ValueError):
            continue
        if iv > 0 and iv not in taken:
            extra_ints.append(iv)
    boundary = list(dict.fromkeys(boundary + extra_ints))
    rng.shuffle(boundary)
    boundary_iter = iter(boundary)
    out = []
    cur = start
    planted_remaining = True
    if boundary:
        want = rng.randint(1, len(boundary))
        plant_set = set(boundary[rng.randrange(len(boundary))] for _ in range(want))
        plant_set = {b for b in plant_set if b >= start}
    else:
        plant_set = set()
    while len(out) < n:
        if plant_set and cur in plant_set:
            out.append(cur)
            plant_set.discard(cur)
            cur += 1
            continue
        if cur in taken:
            cur += 1
            continue
        if any(b < cur for b in plant_set):
            plant_set = {b for b in plant_set if b >= cur}
        out.append(cur)
        taken.add(cur)
        cur += 1
        if not plant_set and planted_remaining:
            planted_remaining = False
    return out


def generate_rows(schema, spec, pool, rng):
    """Return {table: {column: [values]}} in FK order."""
    order = [t for lvl in schema.table_order for t in lvl]
    out = {}
    for t in order:
        tm = schema.tables[t]
        n = table_size(t, rng)
        cols = {}
        gens = {}
        for cm in tm.columns:
            key = (t, cm.name)
            plan = spec[key]
            extra = pool.get(key, [])
            gens[cm.name] = ColumnGen(plan, extra, rng)

        single_pk = (len(tm.primary_key) == 1)
        fk_names = {c for k, c in [(t, c.name) for c in tm.columns] if k in schema.fks}
        for cm in tm.columns:
            key = (t, cm.name)
            if cm.pk_pos > 0 and single_pk:
                plan = spec[key]
                if isinstance(plan['kind'], str) and plan['kind'] in ('int', 'year'):
                    cols[cm.name] = _plant_pk_sequence(schema, t, plan, pool.get(key, []), rng, n)
                else:
                    cols[cm.name] = [gens[cm.name].sample() for _ in range(n)]
            elif key in schema.fks:
                continue
            else:
                cols[cm.name] = [gens[cm.name].sample() for _ in range(n)]

        for cm in tm.columns:
            key = (t, cm.name)
            if key not in schema.fks:
                continue
            pt, pc = schema.fks[key]
            parent_vals = list(schema.original_values.get((pt, pc), []))
            parent_vals += out.get(pt, {}).get(pc, [])
            parent_vals = [v for v in parent_vals if v is not None]
            if (t, cm.name) == ('PaperAuthor', 'AuthorId'):
                parent_vals = list(out.get('Author', {}).get('Id', []))
            ns = spec[key]['null_share']
            dup = spec[key]['dup_share']
            col_boundary = [b for b in spec[key]['boundary']
                            if b in set(parent_vals)] if isinstance(parent_vals, list) else []
            col = []
            for _ in range(n):
                if ns > 0 and rng.random() < ns:
                    col.append(None)
                elif parent_vals and col_boundary and rng.random() < 0.2:
                    col.append(rng.choice(col_boundary))
                elif parent_vals:
                    col.append(rng.choice(parent_vals))
                else:
                    col.append(None)
            if dup > 0 and parent_vals:
                for i in range(len(col)):
                    if rng.random() < dup:
                        col[i] = rng.choice(parent_vals)
            cols[cm.name] = col

        if t == 'PaperAuthor':
            _copy_author_fields(schema, out, cols, rng)

        out[t] = cols
    return out


def _copy_author_fields(schema, out, cols, rng):
    """PaperAuthor.Name/Affiliation mirror Author when AuthorId matches a generated Author."""
    author = out.get('Author')
    if not author:
        return
    a_ids = author.get('Id', [])
    a_name = author.get('Name', [])
    a_aff = author.get('Affiliation', [])
    lookup = {a_ids[i]: (a_name[i], a_aff[i]) for i in range(len(a_ids))}
    ids = cols.get('AuthorId', [])
    names = cols.get('Name', [])
    affs = cols.get('Affiliation', [])
    if len(names) != len(ids):
        names = [None] * len(ids)
    if len(affs) != len(ids):
        affs = [None] * len(ids)
    for i, aid in enumerate(ids):
        if aid is None:
            names[i] = None
            affs[i] = None
            continue
        nm, af = lookup.get(aid, (names[i], affs[i]))
        names[i] = nm
        affs[i] = af
    cols['Name'] = names
    cols['Affiliation'] = affs


def insert_generated(con, schema, rows):
    """Insert generated rows with executemany inside one transaction; skip failing rows."""
    added, skipped = {}, {}
    order = [t for lvl in schema.table_order for t in lvl]
    for t in order:
        tm = schema.tables[t]
        cols = rows.get(t, {})
        names = [c.name for c in tm.columns]
        if not names:
            continue
        n = len(cols.get(names[0], [])) if names else 0
        if n == 0:
            added[t] = 0
            skipped[t] = 0
            continue
        sql = 'INSERT INTO %s VALUES (%s)' % (q(t), ','.join('?' * len(names)))
        ok = bad = 0
        batch = [[cols[c][i] for c in names] for i in range(n)]
        try:
            con.executemany(sql, batch)
            ok = len(batch)
        except Exception:
            for row in batch:
                try:
                    con.execute(sql, row)
                    ok += 1
                except Exception:
                    bad += 1
        added[t] = ok
        skipped[t] = bad
    return added, skipped
