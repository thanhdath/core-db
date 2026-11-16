"""Random instance construction (fuzz/fuzz.py:83-196) + specification by construction."""
import random

from . import spec
from .values import _init_sampler


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
    """Spec table_sizes_per_instance = GENERATED rows, small jitter."""
    sizes = {}
    for t in schema.tables:
        base = spec.TABLE_SIZES.get(t, 10)
        sizes[t] = max(0, base + rng.randint(-2, 2))
    return sizes


def _is_int_type(type_str: str) -> bool:
    return any(k in (type_str or '').lower() for k in ('int', 'integer'))


def _compact_pk_max(schema, table: str, col: str):
    vals = [v for v in schema.original_values.get((table, col), []) if isinstance(v, int)]
    return max(vals) if vals else 0


def _compact_pk_set(schema, table: str, col: str) -> set:
    return {v for v in schema.original_values.get((table, col), []) if v is not None}


def fresh_pk_values(table_meta, schema, n: int) -> list:
    """Generate n fresh PK values that do not collide with compact PKs."""
    cols = table_meta.columns
    pk = [c for c in cols if c.pk_pos > 0]
    pk.sort(key=lambda c: c.pk_pos)
    out: list = []
    if len(pk) == 1:
        c = pk[0]
        used = _compact_pk_set(schema, table_meta.name, c.name)
        if _is_int_type(c.type_str):
            start = _compact_pk_max(schema, table_meta.name, c.name) + 1
            v = start
            while len(out) < n:
                if v not in used:
                    out.append(v)
                v += 1
        else:
            pref = (c.name[:1].upper() or 'K')
            width = 3
            counter = 1
            existing = [str(x) for x in used]
            nums = [int(s[len(pref):]) for s in existing
                    if s.startswith(pref) and s[len(pref):].isdigit()]
            if nums:
                counter = max(nums) + 1
            while len(out) < n:
                tok = '%s%0*d' % (pref, width, counter)
                if tok not in used:
                    out.append(tok)
                counter += 1
    else:
        for _ in range(n):
            out.append(tuple((i + 1) for i in range(len(pk))))
    return out


def _compact_null_share(schema, table: str, col: str) -> float:
    vals = schema.original_values.get((table, col))
    if not vals:
        return spec.NULL_SHARE
    n = len(vals)
    if n == 0:
        return spec.NULL_SHARE
    nulls = sum(1 for v in vals if v is None)
    return nulls / n


def _apply_null_rule(schema, table_meta, columns: dict, rng, protected: dict) -> dict:
    """Nullable columns: NULL share from compact DB, >=1 NULL, not on protected rows."""
    n = len(next(iter(columns.values()))) if columns else 0
    if n == 0:
        return columns
    for cm in table_meta.columns:
        if cm.name not in columns:
            continue
        if cm.notnull or cm.pk_pos > 0:
            continue
        share = _compact_null_share(schema, table_meta.name, cm.name)
        k = int(round(n * share))
        k = max(1, min(k, n))
        prot = protected.get(cm.name, set())
        candidates = [i for i in range(n) if i not in prot]
        if not candidates:
            continue
        k = min(k, len(candidates))
        if k == 0:
            k = 1
        idx = rng.sample(candidates, k)
        for i in idx:
            columns[cm.name][i] = None
    return columns


def _assign_group_sizes_to_domain(n: int, domain: list, rng) -> list:
    """Assign FK values from `domain` so that group sizes 1, 2, >=3 occur."""
    if not domain:
        return [None] * n
    n = int(n)
    if n == 0:
        return []
    distinct = list(dict.fromkeys(domain))
    if len(distinct) < 3:
        out = [distinct[i % len(distinct)] for i in range(n)]
        rng.shuffle(out)
        return out
    chosen = rng.sample(distinct, 3)
    v1, v2, v3 = chosen
    g3_size = n - 3 if n >= 4 else 1
    labels = [v1] + [v2, v2] + [v3] * g3_size
    labels = labels[:n] if len(labels) >= n else labels + [v3] * (n - len(labels))
    rng.shuffle(labels)
    return labels


def _group_counts(values: list) -> dict:
    counts: dict = {}
    for v in values:
        if v is None:
            continue
        counts[v] = counts.get(v, 0) + 1
    return counts


def _has_group_sizes(values: list, need=(1, 2, 3)) -> bool:
    sizes = set(_group_counts(values).values())
    return all(any(s >= t for s in sizes) for t in need)


def _post_roles(inst, schema, rng):
    """Roles.role_code enum; skip tokens already present in the compact DB."""
    cols = inst.get('Roles')
    if not cols:
        return {}
    n = len(cols['role_code'])
    compact = {str(x) for x in schema.original_values.get(('Roles', 'role_code'), []) if x is not None}
    free = [c for c in spec.ROLE_CODES if c not in compact]
    fresh = list(cols['role_code'])
    codes = []
    for i in range(n):
        if free:
            codes.append(free.pop(0))
        else:
            codes.append(fresh[i])
    cols['role_code'] = codes
    cols['role_description'] = [spec.ROLE_DESCRIPTIONS.get(c) for c in codes]
    return {}


def _post_users(inst, schema, rng):
    """Users.role_code group sizes; user_login boundary values."""
    cols = inst.get('Users')
    if not cols:
        return {}
    n = len(cols['user_id'])
    roles = inst.get('Roles', {}).get('role_code') or spec.ROLE_CODES
    cols['role_code'] = _assign_group_sizes_to_domain(n, roles, rng)
    logins = [spec.USER_LOGIN_VALUES[i % len(spec.USER_LOGIN_VALUES)] for i in range(n)]
    rng.shuffle(logins)
    cols['user_login'] = logins
    boundary_idx = set(range(min(n, len(spec.USER_LOGIN_VALUES))))
    return {'user_login': boundary_idx}


def _post_document_structures(inst, schema, rng):
    """Document_Structures codes, descriptions, self-FK parents."""
    cols = inst.get('Document_Structures')
    if not cols:
        return {}
    n = len(cols['document_structure_code'])
    codes = fresh_pk_values(schema.tables['Document_Structures'], schema, n)
    cols['document_structure_code'] = codes
    desc_map = {c: spec.STRUCTURE_DESCRIPTIONS[i % len(spec.STRUCTURE_DESCRIPTIONS)]
                for i, c in enumerate(codes)}
    cols['document_structure_description'] = [desc_map[c] for c in codes]
    compact = set(str(x) for x in schema.original_values.get(
        ('Document_Structures', 'document_structure_code'), []) if x is not None)
    all_codes = list(compact) + codes
    parents = []
    protected = set()
    for i, c in enumerate(codes):
        if n >= 2 and i == 0:
            parents.append(None)
            protected.add(i)
        elif n >= 2 and rng.random() < spec.NULL_SHARE:
            parents.append(None)
            protected.add(i)
        else:
            parents.append(rng.choice(all_codes))
    cols['parent_document_structure_code'] = parents
    return {'parent_document_structure_code': protected}


def _post_functional_areas(inst, schema, rng):
    """Functional_Areas codes, descriptions, self-FK parents."""
    cols = inst.get('Functional_Areas')
    if not cols:
        return {}
    n = len(cols['functional_area_code'])
    codes = fresh_pk_values(schema.tables['Functional_Areas'], schema, n)
    cols['functional_area_code'] = codes
    cols['functional_area_description'] = [
        spec.FUNCTIONAL_AREA_DESCRIPTIONS[i % len(spec.FUNCTIONAL_AREA_DESCRIPTIONS)]
        for i in range(n)]
    compact = set(str(x) for x in schema.original_values.get(
        ('Functional_Areas', 'functional_area_code'), []) if x is not None)
    all_codes = list(compact) + codes
    parents = []
    protected = set()
    for i, c in enumerate(codes):
        if n >= 1 and i == 0:
            parents.append(None)
            protected.add(i)
        elif n >= 1 and rng.random() < spec.NULL_SHARE:
            parents.append(None)
            protected.add(i)
        else:
            parents.append(rng.choice(all_codes))
    cols['parent_functional_area_code'] = parents
    return {'parent_functional_area_code': protected}


def _post_images(inst, schema, rng):
    """Images duplicate-share targets on image_name and image_url."""
    cols = inst.get('Images')
    if not cols:
        return {}
    n = len(cols['image_id'])
    d = spec.distinct_count_for_share(n)
    names_pool = spec.IMAGE_NAMES[:max(1, min(len(spec.IMAGE_NAMES), d))]
    while len(names_pool) < d:
        names_pool.append('img%d' % len(names_pool))
    names = [names_pool[i % len(names_pool)] for i in range(n)]
    rng.shuffle(names)
    cols['image_name'] = names
    url_pool = spec.url_pool(d)
    while len(url_pool) < d:
        url_pool.append('http://example.org/%d.jpg' % len(url_pool))
    urls = [url_pool[i % len(url_pool)] for i in range(n)]
    rng.shuffle(urls)
    cols['image_url'] = urls
    cols['image_alt_text'] = [spec.IMAGE_ALTS[i % len(spec.IMAGE_ALTS)] for i in range(n)]
    rng.shuffle(cols['image_alt_text'])
    return {}


def _post_documents(inst, schema, rng):
    """Documents: codes, type enum, structure FK, names, access_count SUM+tie."""
    cols = inst.get('Documents')
    if not cols:
        return {}
    n = len(cols['document_code'])
    codes = fresh_pk_values(schema.tables['Documents'], schema, n)
    cols['document_code'] = codes
    cols['document_type_code'] = _assign_group_sizes_to_domain(n, spec.DOCUMENT_TYPES, rng)
    structs = inst.get('Document_Structures', {}).get('document_structure_code') or []
    compact_structs = [str(x) for x in schema.original_values.get(
        ('Document_Structures', 'document_structure_code'), []) if x is not None]
    structs_domain = list(dict.fromkeys(compact_structs + list(structs)))
    if len(structs_domain) < 3:
        structs_domain = spec.STRUCTURE_CODES
    cols['document_structure_code'] = _assign_group_sizes_to_domain(n, structs_domain, rng)
    names = [spec.DOC_NAMES[i % len(spec.DOC_NAMES)] for i in range(n)]
    for j, v in enumerate(spec.DOC_NAME_VARIANTS):
        if j < n:
            names[j] = v
    rng.shuffle(names)
    cols['document_name'] = names
    counts = _build_access_counts(n, rng)
    cols['access_count'] = counts
    m = min(counts)
    tie_idx = [i for i, v in enumerate(counts) if v == m][:2]
    return {'access_count': set(tie_idx)}


def _build_access_counts(n: int, rng) -> list:
    """Set the target SUM first, then plant the rank-1 ASC tie preserving the SUM."""
    if n <= 0:
        return []
    target = rng.choice(spec.ACCESS_SUM_TARGETS)
    lo, hi = spec.ACCESS_COUNT_MIN, spec.ACCESS_COUNT_MAX
    base = target // n
    rem = target % n
    counts = [base + (1 if i < rem else 0) for i in range(n)]
    counts = [max(lo, min(hi, v)) for v in counts]
    if n >= 2:
        m = min(counts)
        tie_idx = [0, 1]
        old = [counts[tie_idx[0]], counts[tie_idx[1]]]
        counts[tie_idx[0]] = m
        counts[tie_idx[1]] = m
        delta = (old[0] + old[1]) - (2 * m)
        if delta != 0:
            others = [i for i in range(n) if i not in tie_idx]
            if others:
                j = others[0]
                newv = counts[j] + delta
                if lo <= newv <= hi:
                    counts[j] = newv
                else:
                    remaining = delta
                    for j in others:
                        if remaining == 0:
                            break
                        room = (hi - counts[j]) if remaining > 0 else (counts[j] - lo)
                        step = min(abs(remaining), room)
                        if step <= 0:
                            continue
                        counts[j] += step if remaining > 0 else -step
                        remaining -= step if remaining > 0 else -step
                    if remaining != 0:
                        raise AssertionError('access_count SUM compensation failed')
    if sum(counts) != target:
        raise AssertionError('access_count SUM target not reached: sum=%d target=%d' % (sum(counts), target))
    m = min(counts)
    if sum(1 for v in counts if v == m) < 2:
        raise AssertionError('rank-1 tie not planted on access_count')
    return counts


def _post_document_sections(inst, schema, rng):
    """Document_Sections: titles duplicate-share, sequence > 0, short codes."""
    cols = inst.get('Document_Sections')
    if not cols:
        return {}
    n = len(cols['section_id'])
    d = spec.distinct_count_for_share(n)
    titles_pool = spec.SECTION_TITLES[:max(1, min(len(spec.SECTION_TITLES), d))]
    while len(titles_pool) < d:
        titles_pool.append('title%d' % len(titles_pool))
    titles = [titles_pool[i % len(titles_pool)] for i in range(n)]
    rng.shuffle(titles)
    cols['section_title'] = titles
    cols['section_sequence'] = [rng.randint(1, 9999) for _ in range(n)]
    cols['section_code'] = [str(rng.randint(10, 99)) for _ in range(n)]
    return {}


def _final_parent_keys(inst: dict, schema, table: str, col: str) -> list:
    """Final written parent key values (compact + generated), deduplicated."""
    vals = list(inst.get(table, {}).get(col) or [])
    compact = schema.original_values.get((table, col)) or []
    vals.extend(v for v in compact if v is not None)
    seen, out = set(), []
    for v in vals:
        if v is None:
            continue
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _assign_fks(inst: dict, schema, rng) -> None:
    """Assign every FK column from the FINAL parent key pool (after post-processing)."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        n = len(inst[ct][cc])
        parent_keys = _final_parent_keys(inst, schema, pt, pc)
        if not parent_keys:
            inst[ct][cc] = [None] * n
            continue
        new_vals = []
        for v in inst[ct][cc]:
            if v is None:
                new_vals.append(None)
            else:
                new_vals.append(rng.choice(parent_keys))
        inst[ct][cc] = new_vals


def _ensure_unmatched_parents(inst: dict, schema, rng) -> None:
    """Construct at least one parent row without children for named targets."""
    if 'Document_Structures' in inst and 'Documents' in inst:
        parents = inst['Document_Structures']['document_structure_code']
        children = inst['Documents']['document_structure_code']
        child_set = set(children)
        if parents and all(c in child_set for c in parents):
            parent = parents[-1]
            others = [p for p in parents if p != parent]
            if others:
                for i, v in enumerate(children):
                    if v == parent:
                        children[i] = others[0]
    if 'Documents' in inst and 'Document_Sections' in inst:
        parent_docs = inst['Documents']['document_code']
        sections = inst['Document_Sections']['document_code']
        child_set = set(sections)
        if parent_docs and all(p in child_set for p in parent_docs):
            parent = parent_docs[-1]
            others = [p for p in parent_docs if p != parent]
            if others:
                for i, v in enumerate(sections):
                    if v == parent:
                        sections[i] = others[0]


def _assert_unmatched_parents(inst: dict) -> None:
    """Assert at least one parent row has no child (generated rows only)."""
    if 'Document_Structures' in inst and 'Documents' in inst:
        parents = set(inst['Document_Structures']['document_structure_code'])
        children = set(inst['Documents']['document_structure_code'])
        if parents and not (parents - children):
            raise AssertionError('no unmatched Document_Structures parent')
    if 'Documents' in inst and 'Document_Sections' in inst:
        parents = set(inst['Documents']['document_code'])
        children = set(inst['Document_Sections']['document_code'])
        if parents and not (parents - children):
            raise AssertionError('no unmatched Documents parent')


def _validate_fks(inst: dict, schema) -> None:
    """Assert every non-NULL FK value exists in the final parent key set."""
    for (ct, cc), (pt, pc) in schema.fks.items():
        if ct not in inst or cc not in inst[ct]:
            continue
        parent_keys = set(_final_parent_keys(inst, schema, pt, pc))
        for v in inst[ct][cc]:
            if v is not None and v not in parent_keys:
                raise ValueError('FK violation %s.%s -> %s.%s: %r' % (ct, cc, pt, pc, v))


def _assert_duplicate_share(inst: dict, table: str, col: str) -> None:
    """Assert duplicate share on non-NULL values is in [20%, 50%]."""
    vals = [v for v in inst.get(table, {}).get(col, []) if v is not None]
    n = len(vals)
    if n <= 1:
        return
    d = len(set(vals))
    share = (n - d) / n
    if not (spec.DUP_SHARE_LO - 1e-9 <= share <= spec.DUP_SHARE_HI + 1e-9):
        raise AssertionError('duplicate share out of range %s.%s: %.3f' % (table, col, share))


def build_random_instance(schema, literal_pool: dict, size, rng) -> dict:
    """Build one random instance (fuzz.py:111-196) + specification by construction."""
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
        for cm in tm.columns:
            if (t, cm.name) in schema.fks:
                cols[cm.name] = [None] * n
        pk_vals = fresh_pk_values(tm, schema, n)
        if len(tm.primary_key) == 1 and tm.primary_key[0] in cols:
            cols[tm.primary_key[0]] = pk_vals
        cols = sample_fresh_primary_keys(tm, cols)
        cols = drop_unique_duplicates(tm, cols)
        inst[t] = cols

    protected: dict = {}
    for fn in (_post_roles, _post_users, _post_document_structures,
               _post_functional_areas, _post_images, _post_documents,
               _post_document_sections):
        prot = fn(inst, schema, rng)
        if prot:
            tname = fn.__name__[len('_post_'):]
            tmap = {'roles': 'Roles', 'users': 'Users',
                    'document_structures': 'Document_Structures',
                    'functional_areas': 'Functional_Areas', 'images': 'Images',
                    'documents': 'Documents', 'document_sections': 'Document_Sections'}
            table = tmap.get(tname, tname)
            for cname, idxs in prot.items():
                protected[(table, cname)] = set(idxs)

    _assign_fks(inst, schema, rng)
    _ensure_unmatched_parents(inst, schema, rng)

    for t in order:
        if t in inst:
            col_prot = {cname: idxs for (tt, cname), idxs in protected.items() if tt == t}
            inst[t] = _apply_null_rule(schema, schema.tables[t], inst[t], rng, col_prot)

    _validate_fks(inst, schema)
    _assert_unmatched_parents(inst)
    _assert_duplicate_share(inst, 'Document_Sections', 'section_title')
    _assert_duplicate_share(inst, 'Images', 'image_name')
    _assert_duplicate_share(inst, 'Images', 'image_url')
    return {t: inst[t] for t in schema.tables}
