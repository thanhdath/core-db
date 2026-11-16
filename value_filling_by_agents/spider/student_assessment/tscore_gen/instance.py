"""Random instance construction (fuzz/fuzz.py:83-196)."""
import datetime as dt

from . import spec
from .values import _init_sampler


def _filter(columns: dict, keep: list) -> dict:
    return {c: [v[i] for i in keep] for c, v in columns.items()}


def _nrows(columns: dict) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def sample_fresh_primary_keys(table_meta, columns: dict) -> dict:
    """Drop rows whose PK tuple repeats, first occurrence kept (fuzz.py:188-190)."""
    if not table_meta.primary_key or not columns:
        return columns
    n = _nrows(columns)
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


def _coerce(value, kind):
    """Coerce a parent key value to the child's declared type (spec.COERCE_FK)."""
    if value is None:
        return None
    if kind == 'int':
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value


def _parent_pool(instance: dict, schema, pt: str, pc: str, coerce=None) -> list:
    """Materialized parent values: generated rows first, then compact rows (never NULL)."""
    vals = list(instance.get(pt, {}).get(pc) or [])
    vals += [v for v in schema.original_values.get((pt, pc), []) if v is not None]
    if coerce:
        vals = [_coerce(v, coerce) for v in vals]
        vals = [v for v in vals if v is not None]
    return vals


def _parent_tuples(instance: dict, schema, pt: str, cols: list, coerce_map: dict) -> list:
    """Materialized parent tuples (generated + compact), deduplicated, no NULLs."""
    gen = instance.get(pt, {})
    n = len(gen.get(cols[0], [])) if cols and cols[0] in gen else 0
    tuples = []
    for i in range(n):
        t = tuple(gen[c][i] for c in cols)
        if all(v is not None for v in t):
            tuples.append(t)
    ov = schema.original_values
    m = len(ov.get((pt, cols[0]), [])) if cols else 0
    for i in range(m):
        t = tuple(ov.get((pt, c), [None] * m)[i] for c in cols)
        if all(v is not None for v in t):
            tuples.append(t)
    if coerce_map:
        out = []
        for t in tuples:
            ct = tuple(_coerce(v, coerce_map.get(c)) if c in coerce_map else v for c, v in zip(cols, t))
            if all(v is not None for v in ct):
                out.append(ct)
        tuples = out
    seen, uniq = set(), []
    for t in tuples:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def fill_foreign_keys_consistently(instance: dict, schema, table: str, n: int, rng) -> dict:
    """FK child columns draw from the parent's materialized final values (compact + generated)."""
    out = {}
    for cm in schema.tables[table].columns:
        key = (table, cm.name)
        if key not in schema.fks:
            continue
        pt, pc = schema.fks[key]
        coerce = spec.COERCE_FK.get(key)
        pv = _parent_pool(instance, schema, pt, pc, coerce)
        if not pv:
            raise RuntimeError('empty parent pool for FK %s.%s -> %s.%s' % (table, cm.name, pt, pc))
        out[cm.name] = [rng.choice(pv) for _ in range(n)]
    return out


def choose_table_sizes(schema, rng) -> dict:
    """Spec table sizes with per-instance jitter (0-230 rows per table)."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 20)
        jitter = rng.randint(-2, 2)
        sizes[t] = max(0, base + jitter)
    return sizes


def _apply_null_rule(schema, table: str, cols: dict, rng) -> dict:
    """NULL rule driven by spec.NULL_TARGETS (plus ALL_NULL_COLUMNS at 100%)."""
    tm = schema.tables[table]
    n = _nrows(cols)
    if n == 0:
        return cols
    for cm in tm.columns:
        if cm.name not in cols or cm.notnull or cm.pk_pos > 0:
            continue
        if (table, cm.name) in spec.NOT_NULL_COLUMNS:
            continue
        if (table, cm.name) in schema.fks:
            continue
        if (table, cm.name) in spec.ALL_NULL_COLUMNS:
            cols[cm.name] = [None] * n
            continue
        if (table, cm.name) not in spec.NULL_TARGETS:
            continue
        ov = schema.original_values.get((table, cm.name), [])
        share = (sum(1 for v in ov if v is None) / len(ov)) if ov else 0.15
        k = max(1, int(round(share * n)))
        idx = rng.sample(range(n), min(k, n))
        for i in idx:
            cols[cm.name][i] = None
    return cols


def _inject_forced_values(table: str, cols: dict, rng) -> dict:
    """Force at least one generated row to carry each listed literal (spec.FORCED_VALUES)."""
    n = _nrows(cols)
    if n == 0:
        return cols
    for (t, c), values in spec.FORCED_VALUES.items():
        if t != table or c not in cols:
            continue
        for v in values:
            i = rng.randrange(n)
            cols[c][i] = v
    return cols


def _inject_parent_keys(table: str, cols: dict, rng) -> dict:
    """Inject boundary literals into the PARENT primary-key stream (spec.PARENT_KEY_INJECTIONS)."""
    inj = spec.PARENT_KEY_INJECTIONS.get(table)
    if not inj:
        return cols
    n = _nrows(cols)
    if n == 0:
        return cols
    for c, values in inj.items():
        if c not in cols:
            continue
        for v in values:
            i = rng.randrange(n)
            cols[c][i] = v
    return cols


def _apply_enums(table: str, cols: dict, rng) -> dict:
    """Enum domains (spec.ENUMS): every value drawn from the domain."""
    n = _nrows(cols)
    for (t, c), domain in spec.ENUMS.items():
        if t != table or c not in cols:
            continue
        for i in range(n):
            if cols[c][i] is None or cols[c][i] not in domain:
                cols[c][i] = rng.choice(domain)
    return cols


def _apply_group_size_target(table: str, cols: dict, rng) -> dict:
    """Student_Course_Registrations.course_id: deterministic group sizes 1, 2 and >= 3. Reserve dedicated indices; do
    not shuffle-overwrite them."""
    tgt = spec.GROUP_SIZE_TARGET
    if tgt['table'] != table or tgt['column'] not in cols:
        return cols
    n = len(cols[tgt['column']])
    if n < 6:
        return cols
    pool = [v for v in cols[tgt['column']] if v is not None]
    if not pool:
        return cols
    distinct = sorted(set(pool))
    rng.shuffle(distinct)
    if len(distinct) < 3:
        return cols
    c1, c2, c3 = distinct[0], distinct[1], distinct[2]
    cols[tgt['column']][0] = c1
    cols[tgt['column']][1] = c2
    cols[tgt['column']][2] = c2
    cols[tgt['column']][3] = c3
    cols[tgt['column']][4] = c3
    cols[tgt['column']][5] = c3
    return cols


def _apply_tie_target(table: str, cols: dict, rng) -> dict:
    """Student_Course_Attendance.date_of_attendance: at least two rows tie on the date."""
    tgt = spec.TIE_TARGET
    if tgt['table'] != table or tgt['column'] not in cols:
        return cols
    n = len(cols[tgt['column']])
    if n < 2:
        return cols
    base = cols[tgt['column']][0]
    if base is None:
        return cols
    try:
        d = dt.datetime.strptime(str(base)[:10], '%Y-%m-%d')
    except ValueError:
        return cols
    tie = d.strftime('%Y-%m-%d') + ' 09:00:00'
    cols[tgt['column']][1] = tie
    return cols


def _apply_different_values_target(table: str, cols: dict, rng) -> dict:
    """Candidate_Assessments.assessment_date: >= 2 different values per candidate."""
    tgt = spec.DIFFERENT_VALUES_TARGET
    if tgt['table'] != table or tgt['group_column'] not in cols or tgt['value_column'] not in cols:
        return cols
    groups: dict = {}
    for i, g in enumerate(cols[tgt['group_column']]):
        groups.setdefault(g, []).append(i)
    for g, idxs in groups.items():
        if len(idxs) < tgt['min_per_group']:
            continue
        base = cols[tgt['value_column']][idxs[0]]
        if base is None:
            continue
        try:
            d = dt.datetime.strptime(str(base)[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        for k, i in enumerate(idxs[1:], start=1):
            cols[tgt['value_column']][i] = (d + dt.timedelta(days=k)).strftime('%Y-%m-%d %H:%M:%S')
    return cols


def _apply_semantic_rules(table: str, cols: dict, instance: dict, rng) -> dict:
    """Semantic rules from spec.semantic_rules_and_formulas (Python, not SQL)."""
    n = _nrows(cols)
    if table == 'People_Addresses':
        df = cols.get('date_from')
        dt_ = cols.get('date_to')
        if df is not None and dt_ is not None:
            for i in range(n):
                if dt_[i] is not None and df[i] is not None:
                    try:
                        a = dt.datetime.strptime(str(df[i])[:19], '%Y-%m-%d %H:%M:%S')
                        b = dt.datetime.strptime(str(dt_[i])[:19], '%Y-%m-%d %H:%M:%S')
                        if b < a:
                            dt_[i] = (a + dt.timedelta(days=rng.randint(1, 365))).strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
    if table == 'Student_Course_Attendance':
        reg = instance.get('Student_Course_Registrations', {})
        sid = cols.get('student_id')
        doa = cols.get('date_of_attendance')
        if sid is not None and doa is not None:
            min_reg: dict = {}
            for s, r in zip(reg.get('student_id', []), reg.get('registration_date', [])):
                if s is None or r is None:
                    continue
                try:
                    d = dt.datetime.strptime(str(r)[:19], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    continue
                if s not in min_reg or d < min_reg[s]:
                    min_reg[s] = d
            for i in range(n):
                s = sid[i]
                if s in min_reg and doa[i] is not None:
                    try:
                        a = dt.datetime.strptime(str(doa[i])[:19], '%Y-%m-%d %H:%M:%S')
                        if a < min_reg[s]:
                            doa[i] = (min_reg[s] + dt.timedelta(days=rng.randint(0, 30))).strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
    return cols


def _fill_composite_fk(instance: dict, schema, table: str, n: int, rng) -> dict:
    """Composite FK: sample joint parent tuples from MATERIALIZED final parent rows."""
    cfk = spec.COMPOSITE_FK
    if cfk['child_table'] != table:
        return {}
    coerce_map = {c: spec.COERCE_FK.get((cfk['parent_table'], c)) for c in cfk['parent_cols']}
    tuples = _parent_tuples(instance, schema, cfk['parent_table'], cfk['parent_cols'], coerce_map)
    if not tuples:
        raise RuntimeError('empty composite parent pool for %s' % table)
    out = {c: [] for c in cfk['child_cols']}
    for _ in range(n):
        t = rng.choice(tuples)
        for c, v in zip(cfk['child_cols'], t):
            out[c].append(v)
    return out


def _finalize_table(schema, table: str, cols: dict, instance: dict, rng) -> dict:
    """Apply the full finalization pipeline to a parent table's columns (in order)."""
    tm = schema.tables[table]
    cols = sample_fresh_primary_keys(tm, cols)
    cols = drop_unique_duplicates(tm, cols)
    cols = _apply_group_size_target(table, cols, rng)
    cols = _apply_tie_target(table, cols, rng)
    cols = _apply_different_values_target(table, cols, rng)
    cols = _apply_semantic_rules(table, cols, instance, rng)
    cols = _apply_null_rule(schema, table, cols, rng)
    return cols


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) of rows to append to the compact database."""
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
        cols = _inject_parent_keys(t, cols, rng)
        cols = _inject_forced_values(t, cols, rng)
        cols = _apply_enums(t, cols, rng)
        inst[t] = cols
        comp = _fill_composite_fk(inst, schema, t, n, rng)
        if comp:
            cols.update(comp)
        cols.update(fill_foreign_keys_consistently(inst, schema, t, n, rng))
        for cm in tm.columns:
            pt, pc = schema.fks.get((t, cm.name), (None, None))
            if pt == t:
                final = cols[pc]
                fs = set(final)
                cols[cm.name] = [v if v is None or v in fs else (rng.choice(final) if final else None)
                                 for v in cols[cm.name]]
        cols = _finalize_table(schema, t, cols, inst, rng)
        inst[t] = cols
    return {t: inst[t] for t in schema.tables}
