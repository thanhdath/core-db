"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt

from .values import (DUPLICATE_SHARE, GROUP_SIZE_COLUMNS, NULLABLE_COLUMNS, NUMERIC_TEXT_COLUMNS,
                     PLANTED_STRINGS, REQUIRED_LITERALS, TABLE_SIZES, TIE_COLUMNS, _init_sampler,
                     is_numeric_type, safe_float, safe_int)

_FORMATS = ('%Y-%m-%d %H:%M', '%Y-%m-%d')


def _parse(s):
    """Parse a datetime string with either of the project's formats."""
    if s is None:
        return None
    if isinstance(s, dt.datetime):
        return s
    for f in _FORMATS:
        try:
            return dt.datetime.strptime(str(s), f)
        except ValueError:
            pass
    return None


def _fmt(d: dt.datetime, with_time: bool) -> str:
    return d.strftime('%Y-%m-%d %H:%M' if with_time else '%Y-%m-%d')


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


def _parent_pool(instance: dict, schema, pt: str, pc: str) -> list:
    """Compact + generated values of the parent column (in memory, no SQL)."""
    vals = list(schema.original_values.get((pt, pc), []))
    vals += list(instance.get(pt, {}).get(pc, []))
    return [v for v in vals if v is not None]


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's compact+generated values; empty parent -> NULL."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        pv = _parent_pool(instance, schema, pt, pc)
        out[cm.name] = [rng.choice(pv) for _ in range(n)] if pv else [None] * n
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Specification table sizes with per-instance variation (0-230 rows, level x4 capped at 2500)."""
    sizes = {}
    for lvl in schema.table_order:
        for t in lvl:
            base = TABLE_SIZES.get(t)
            if base is None:
                base = int(30 * rng.random() + int(rng.random() * 200))
            jitter = 1.0 + (rng.random() - 0.5) * 0.5
            sizes[t] = max(1, int(round(base * jitter)))
    return sizes


def _apply_null_rule(table: str, columns: dict, rng) -> dict:
    """NULL rule: every nullable column gets >=1 NULL and a share following the compact DB."""
    for (t, c), share in NULLABLE_COLUMNS.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        n = len(vals)
        if n == 0:
            continue
        k = max(1, int(round(share * n)))
        k = min(k, n - 1) if n > 1 else 1
        idx = rng.sample(range(n), k)
        for i in idx:
            vals[i] = None
    return columns


def _apply_duplicate_share(table: str, columns: dict, rng) -> dict:
    """DISTINCT-exercised columns: force a 20-50% duplicate share by copying existing values."""
    for (t, c), share in DUPLICATE_SHARE.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        n = len(vals)
        if n < 2:
            continue
        k = max(1, int(round(share * n)))
        for i in rng.sample(range(n), min(k, n - 1)):
            j = rng.randrange(n)
            if j != i:
                vals[i] = vals[j]
    return columns


def _apply_group_sizes(table: str, columns: dict, rng) -> dict:
    """Group-size targets: ensure groups of size 1, 2 and >= 3 exist for the listed columns."""
    for (t, c) in GROUP_SIZE_COLUMNS:
        if t != table or c not in columns:
            continue
        vals = columns[c]
        n = len(vals)
        if n < 6:
            continue
        base = [vals[0], vals[1], vals[1], vals[2], vals[2], vals[2]]
        for i in range(6, n):
            base.append(vals[i])
        columns[c] = base
    return columns


def _apply_ties(table: str, columns: dict, rng) -> dict:
    """Tie targets: plant >= 2 rows sharing the tie value at the listed rank."""
    for (t, c), ranks in TIE_COLUMNS.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        if len(vals) < 2:
            continue
        vals[1] = vals[0]
    return columns


def _apply_required_literals(table: str, columns: dict, rng) -> dict:
    """Guarantee the listed boundary literals appear verbatim in the generated rows."""
    for (t, c), lits in REQUIRED_LITERALS.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        n = len(vals)
        if n == 0:
            continue
        for k, lit in enumerate(lits):
            if k < n:
                vals[k] = lit
    return columns


def _apply_planted_strings(table: str, columns: dict, rng) -> dict:
    """Guarantee planted strings (e.g. 'John Wen' / 'john wen') appear in the generated rows."""
    for (t, c), strs in PLANTED_STRINGS.items():
        if t != table or c not in columns:
            continue
        vals = columns[c]
        n = len(vals)
        if n == 0:
            continue
        for k, s in enumerate(strs):
            if k < n:
                vals[k] = s
    return columns


def _apply_semantic_rules(table: str, columns: dict, instance: dict, schema, rng) -> dict:
    """Semantic formulas implemented by construction (Python only, no SQL)."""
    if table == 'Appointment' and 'Start' in columns and 'End' in columns:
        starts, ends = columns['Start'], columns['End']
        for i in range(len(starts)):
            sd = _parse(starts[i])
            if sd is None:
                continue
            ends[i] = _fmt(sd + dt.timedelta(hours=1), True)
    if table == 'Trained_In' and 'CertificationDate' in columns and 'CertificationExpires' in columns:
        cds, ces = columns['CertificationDate'], columns['CertificationExpires']
        for i in range(len(cds)):
            cdd = _parse(cds[i])
            if cdd is None:
                continue
            ces[i] = _fmt(cdd + dt.timedelta(days=365), False)
    if table == 'Stay' and 'StayStart' in columns and 'StayEnd' in columns:
        ss, se = columns['StayStart'], columns['StayEnd']
        for i in range(len(ss)):
            sd = _parse(ss[i])
            if sd is None:
                continue
            se[i] = _fmt(sd + dt.timedelta(days=3), False)
    if table == 'On_Call' and 'OnCallStart' in columns and 'OnCallEnd' in columns:
        cs, ce = columns['OnCallStart'], columns['OnCallEnd']
        for i in range(len(cs)):
            sd = _parse(cs[i])
            if sd is None:
                continue
            ce[i] = _fmt(sd + dt.timedelta(hours=8), True)
    if table == 'Procedures' and 'Cost' in columns:
        columns['Cost'] = [max(0.0, safe_float(v, 0.0)) for v in columns['Cost']]
    if table == 'Prescribes' and 'Dose' in columns:
        lo = NUMERIC_TEXT_COLUMNS.get(('Prescribes', 'Dose'), (1, 20))[0]
        columns['Dose'] = [str(max(lo, safe_int(v, lo))) for v in columns['Dose']]
    if table == 'Undergoes' and 'DateUndergoes' in columns and 'Stay' in columns:
        ss = {}
        for sid, sstart in zip(list(schema.original_values.get(('Stay', 'StayID'), [])) +
                               list(instance.get('Stay', {}).get('StayID', [])),
                               list(schema.original_values.get(('Stay', 'StayStart'), [])) +
                               list(instance.get('Stay', {}).get('StayStart', []))):
            if sid is not None:
                ss[sid] = sstart
        for i, sid in enumerate(columns['Stay']):
            sd = _parse(ss.get(sid))
            if sd is None:
                continue
            columns['DateUndergoes'][i] = _fmt(sd + dt.timedelta(days=1), False)
    return columns


def _finalize_foreign_keys(table: str, columns: dict, inst: dict, schema, rng) -> None:
    """Validate every child FK value against the FINAL parent key set (after PK dedup and unique drops)."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in columns:
            continue
        pt, pc = schema.fks[key]
        final_parent = [v for v in inst.get(pt, {}).get(pc, []) if v is not None]
        if not final_parent:
            final_parent = [v for v in schema.original_values.get((pt, pc), []) if v is not None]
        allowed = set(final_parent)
        out = []
        for v in columns[cm.name]:
            if v is None:
                out.append(None)
            elif v in allowed:
                out.append(v)
            elif final_parent:
                out.append(rng.choice(final_parent))
            else:
                out.append(None)
        columns[cm.name] = out


def _plant_unmatched_joins(table: str, columns: dict, inst: dict, schema, rng) -> None:
    """Plant unmatched-join targets: parent rows without children and child rows with NULL FK."""
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks or cm.name not in columns:
            continue
        pt, pc = schema.fks[key]
        parent_vals = [v for v in (list(schema.original_values.get((pt, pc), [])) +
                                   list(inst.get(pt, {}).get(pc, []))) if v is not None]
        if not parent_vals:
            continue
        child_vals = columns[cm.name]
        referenced = {v for v in child_vals if v is not None}
        unreferenced = [v for v in parent_vals if v not in referenced]
        if not unreferenced and len(parent_vals) > 1:
            drop = parent_vals[0]
            for i, v in enumerate(child_vals):
                if v == drop:
                    child_vals[i] = parent_vals[1]
                    break
        if cm.notnull is False and child_vals and all(v is not None for v in child_vals):
            child_vals[0] = None
        columns[cm.name] = child_vals


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance of *appended* rows (fuzz.py:111-196 + specification rules)."""
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
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        cols = sample_fresh_primary_keys(tm, {cm.name: cols[cm.name] for cm in tm.columns})
        cols = drop_unique_duplicates(tm, cols)
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t and pc in cols:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _apply_null_rule(t, cols, rng)
        cols = _apply_duplicate_share(t, cols, rng)
        cols = _apply_group_sizes(t, cols, rng)
        cols = _apply_ties(t, cols, rng)
        cols = _apply_required_literals(t, cols, rng)
        cols = _apply_planted_strings(t, cols, rng)
        cols = _apply_semantic_rules(t, cols, inst, schema, rng)
        _finalize_foreign_keys(t, cols, inst, schema, rng)
        _plant_unmatched_joins(t, cols, inst, schema, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
