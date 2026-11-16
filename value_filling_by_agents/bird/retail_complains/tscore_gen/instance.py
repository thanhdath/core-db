"""Random instance construction implementing the specification by construction."""
import datetime as dt

from .specification import DEPENDENCIES, EXCEPTIONS, TABLE_SIZES
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _null_share(schema, table: str, column: str, exception: dict) -> float:
    """NULL share: specification target if given, else the compact database's share."""
    tgt = (exception or {}).get('targets', {}).get('null_share')
    if tgt is not None:
        return float(tgt)
    vals = schema.original_values.get((table, column), [])
    if not vals:
        return 0.0
    n_null = sum(1 for v in vals if v is None)
    return n_null / len(vals)


def _is_nullable(schema, table: str, column: str) -> bool:
    tm = schema.tables[table]
    for cm in tm.columns:
        if cm.name == column:
            return not cm.notnull and cm.pk_pos == 0
    return False


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept."""
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
    """Drop rows repeating any single unique column value."""
    for cm in table_meta.columns:
        if cm.unique and cm.name in columns:
            seen, keep = set(), []
            for i, v in enumerate(columns[cm.name]):
                if v not in seen:
                    seen.add(v)
                    keep.append(i)
            columns = _filter(columns, keep)
    return columns


def _fk_parent(schema, table: str, column: str):
    """Return (parent_table, parent_column) for a FK column, or None."""
    for ct, cc, pt, pc in DEPENDENCIES:
        if ct == table and cc == column:
            return pt, pc
    return schema.fks.get((table, column))


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng,
                                   null_share: float = 0.0) -> dict:
    """FK child columns draw from the parent's in-memory values; NULL per the NULL rule."""
    out = {}
    for cm in schema.tables[table].columns:
        parent = _fk_parent(schema, table, cm.name)
        if parent is None:
            continue
        pt, pc = parent
        pv = instance.get(pt, {}).get(pc) or []
        pv = [v for v in pv if v is not None]
        vals = []
        for _ in range(n):
            if null_share > 0 and rng.random() < null_share:
                vals.append(None)
            elif pv:
                vals.append(rng.choice(pv))
            else:
                vals.append(None)
        out[cm.name] = vals
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification sizes with a small per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 0)
        if base <= 0:
            sizes[t] = 0
            continue
        jitter = int(rng.random() * 0.2 * base)
        sizes[t] = max(0, min(2500, base - jitter + int(rng.random() * jitter)))
    return sizes


def _time_to_seconds(s: str) -> int:
    h, m, sec = (int(x) for x in s.split(':'))
    return h * 3600 + m * 60 + sec


def _seconds_to_time(n: int) -> str:
    n = max(0, n)
    return '%02d:%02d:%02d' % (n // 3600, (n % 3600) // 60, n % 60)


def _apply_callcenter_derived(cols: dict, rng) -> None:
    """ser_exit >= ser_start and ser_time = ser_exit - ser_start (Python, in memory)."""
    starts = cols.get('ser_start')
    exits = cols.get('ser_exit')
    if starts is None or exits is None:
        return
    times = []
    for i in range(len(starts)):
        s, e = starts[i], exits[i]
        if s is None or e is None:
            times.append(None)
            continue
        ss, es = _time_to_seconds(s), _time_to_seconds(e)
        if es < ss:
            es = ss + rng.randrange(0, 3600)
            exits[i] = _seconds_to_time(es)
        times.append(_seconds_to_time(es - ss))
    cols['ser_time'] = times


def _apply_events_derived(cols: dict, rng) -> None:
    """Date sent to company >= Date received (Python, in memory)."""
    recv = cols.get('Date received')
    sent = cols.get('Date sent to company')
    if recv is None or sent is None:
        return
    for i in range(len(recv)):
        r, s = recv[i], sent[i]
        if r is None or s is None:
            continue
        try:
            rd = dt.date.fromisoformat(str(r)[:10])
            sd = dt.date.fromisoformat(str(s)[:10])
        except (ValueError, TypeError):
            continue
        if sd < rd:
            sent[i] = (rd + dt.timedelta(days=rng.randrange(0, 30))).isoformat()


def _plant_nulls(schema, table: str, cols: dict, rng) -> None:
    """Plant NULLs at the compact database's null rate."""
    for cm in schema.tables[table].columns:
        if cm.name not in cols:
            continue
        if not _is_nullable(schema, table, cm.name):
            continue
        exc = EXCEPTIONS.get((table, cm.name), {})
        share = _null_share(schema, table, cm.name, exc)
        if share <= 0.0:
            continue
        vals = cols[cm.name]
        if not vals:
            continue
        for i in range(len(vals)):
            if vals[i] is None:
                continue
            if rng.random() < share:
                vals[i] = None


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (generated rows only; the writer appends them to a copy)."""
    order = [t for lvl in schema.table_order for t in lvl]
    if size is None:
        size = choose_table_sizes(schema, rng)

    samplers = {}
    for t in order:
        tm = schema.tables[t]
        for cm in tm.columns:
            if _fk_parent(schema, t, cm.name) is not None:
                continue
            exc = EXCEPTIONS.get((t, cm.name), {})
            ns = _null_share(schema, t, cm.name, exc) if _is_nullable(schema, t, cm.name) else 0.0
            samplers[(t, cm.name)] = _init_sampler(
                cm, exc, literal_pool.get((t, cm.name), []),
                schema.original_values.get((t, cm.name), []), rng, ns)

    inst: dict = {}
    for t in order:
        tm = schema.tables[t]
        n = int(size.get(t, 0))
        cols = {cm.name: [samplers[(t, cm.name)].sample() for _ in range(n)]
                for cm in tm.columns if (t, cm.name) in samplers}
        for cm in tm.columns:
            parent = _fk_parent(schema, t, cm.name)
            if parent is None:
                continue
            exc = EXCEPTIONS.get((t, cm.name), {})
            ns = _null_share(schema, t, cm.name, exc) if _is_nullable(schema, t, cm.name) else 0.0
            pt, pc = parent
            pv = inst.get(pt, {}).get(pc) or []
            pv = [v for v in pv if v is not None]
            vals = []
            for _ in range(n):
                if ns > 0 and rng.random() < ns:
                    vals.append(None)
                elif pv:
                    vals.append(rng.choice(pv))
                else:
                    vals.append(None)
            cols[cm.name] = vals
        _plant_nulls(schema, t, cols, rng)
        if t == 'callcenterlogs':
            _apply_callcenter_derived(cols, rng)
        elif t == 'events':
            _apply_events_derived(cols, rng)
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            parent = _fk_parent(schema, t, cm.name)
            if parent is not None and parent[0] == t:
                final = cols.get(parent[1], [])
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
