"""In-memory instance construction (FK order, null rule, boundaries, ties, group sizes)."""
from __future__ import annotations

import random

from .sampler import (
    sample_text, sample_ticks, sample_was_compiled, sample_comment_is_xml,
    sample_stars, sample_forks, sample_watchers, sample_lang, sample_lang_boundary,
)
from .spec import (
    TABLE_SIZES, NULL_SHARES, LANG_BOUNDARY,
    STARS_HEAVY, STARS_HEAVY_MIN_ROWS,
    URL_POOL, PATH_POOL, NAME_POOL, TYPE_POOL, PARAM_NAME_POOL,
    COMMENT_POOL, SUMMARY_POOL, API_POOL, TOKENIZED_POOL,
)


def _null_share(table: str, column: str) -> float:
    return NULL_SHARES.get((table, column), 0.15)


def _maybe_null(rng: random.Random, value, share: float):
    if rng.random() < share:
        return None
    return value


def _max_existing_id(schema, table: str) -> int:
    """Max existing integer id in the compact DB for a table (0 if none)."""
    vals = schema.original_values.get((table, 'Id'), [])
    ints = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
    return max(ints) if ints else 0


def _reserved_ids(schema, table: str, k: int) -> list:
    """Reserved ids max(existing_id)+1..+k so they never collide with compact PKs."""
    base = _max_existing_id(schema, table)
    return [base + j for j in range(1, k + 1)]


def _seq_ids_with_reserved(n_regular: int, reserved: list) -> list:
    """Sequential ids 1..n_regular plus the reserved higher ids (uniqueness preserved)."""
    ids = list(range(1, n_regular + 1))
    for r in reserved:
        if r not in ids:
            ids.append(r)
    return ids


def _fk_lookup(parent_ids: list, n_child: int, rng: random.Random) -> list:
    """Build a child->parent assignment with one parent childless, group sizes 1,2,>=3, ties."""
    if not parent_ids:
        return [None] * n_child
    pids = list(parent_ids)
    childless = pids[-1]
    pool = pids[:-1] if len(pids) > 1 else pids
    heavy = pool[0]
    singles = pool[1:1 + max(1, len(pool) // 3)]
    doubles = pool[1 + len(pool) // 3: 1 + 2 * len(pool) // 3]
    others = pool[1 + 2 * len(pool) // 3:] or pool[:1]
    assigns: list = [heavy] * max(3, n_child // 5)
    for s in singles:
        assigns.append(s)
    for d in doubles:
        assigns += [d, d]
    while len(assigns) < n_child:
        if rng.random() < 0.3:
            assigns.append(heavy)
        else:
            assigns.append(rng.choice(others))
    rng.shuffle(assigns)
    out = assigns[:n_child]
    return out


def _build_repo(schema, rng: random.Random, n: int) -> list:
    reserved = _reserved_ids(schema, 'Repo', 3)
    ids = _seq_ids_with_reserved(n, reserved)
    heavy_rows = set(rng.sample(ids, min(STARS_HEAVY_MIN_ROWS, len(ids)))) if ids else set()
    rows = []
    for rid in ids:
        if rid in heavy_rows:
            stars = STARS_HEAVY
        else:
            stars = sample_stars(rng, heavy_value=STARS_HEAVY)
        forks = sample_forks(rng)
        watchers = sample_watchers(rng, stars)
        url = sample_text(rng, URL_POOL)
        rows.append({'Id': rid, 'Url': url, 'Stars': stars, 'Forks': forks,
                     'Watchers': watchers, 'ProcessedTime': sample_ticks(rng)})
    return rows


def _build_solution(schema, rng: random.Random, n: int, repo_rows: list) -> list:
    reserved = _reserved_ids(schema, 'Solution', 5)
    ids = _seq_ids_with_reserved(n, reserved)
    repo_ids = [r['Id'] for r in repo_rows]
    fk = _fk_lookup(repo_ids, len(ids), rng)
    share = _null_share('Solution', 'RepoId')
    pshare = _null_share('Solution', 'Path')
    path_heavy = PATH_POOL[0]
    rows = []
    for idx, sid in enumerate(ids):
        repoid = None if rng.random() < share else fk[idx]
        if rng.random() < 0.30:
            path = path_heavy
        else:
            path = sample_text(rng, PATH_POOL)
        path = _maybe_null(rng, path, pshare)
        rows.append({
            'Id': sid, 'RepoId': repoid, 'Path': path,
            'ProcessedTime': sample_ticks(rng),
            'WasCompiled': sample_was_compiled(rng),
        })
    return rows


def _build_method(schema, rng: random.Random, n: int, solution_rows: list) -> list:
    ids = _seq_ids_with_reserved(n, [])
    sol_ids = [r['Id'] for r in solution_rows]
    fk = _fk_lookup(sol_ids, len(ids), rng)
    sid_share = _null_share('Method', 'SolutionId')
    name_share = _null_share('Method', 'Name')
    full_share = _null_share('Method', 'FullComment')
    sum_share = _null_share('Method', 'Summary')
    lang_share = _null_share('Method', 'Lang')
    rows = []
    for idx, mid in enumerate(ids):
        sid = None if rng.random() < sid_share else fk[idx]
        name = _maybe_null(rng, sample_text(rng, NAME_POOL), name_share)
        full = _maybe_null(rng, sample_text(rng, COMMENT_POOL), full_share)
        summary = _maybe_null(rng, sample_text(rng, SUMMARY_POOL), sum_share)
        api = sample_text(rng, API_POOL)
        if rng.random() < 0.25:
            lang_val = sample_lang_boundary(rng)
        else:
            lang_val = sample_lang(rng)
        lang = _maybe_null(rng, lang_val, lang_share)
        tokenized = sample_text(rng, TOKENIZED_POOL)
        rows.append({
            'Id': mid, 'Name': name, 'FullComment': full, 'Summary': summary,
            'ApiCalls': api, 'CommentIsXml': sample_comment_is_xml(rng),
            'SampledAt': sample_ticks(rng), 'SolutionId': sid, 'Lang': lang,
            'NameTokenized': tokenized,
        })
    return rows


def _build_method_parameter(schema, rng: random.Random, n: int, method_rows: list) -> list:
    ids = _seq_ids_with_reserved(n, [])
    method_ids = [r['Id'] for r in method_rows]
    fk = _fk_lookup(method_ids, len(ids), rng)
    mid_share = _null_share('MethodParameter', 'MethodId')
    name_share = _null_share('MethodParameter', 'Name')
    type_share = _null_share('MethodParameter', 'Type')
    rows = []
    for idx, pid in enumerate(ids):
        if rng.random() < mid_share or not method_ids:
            mid = None
        else:
            mid = str(fk[idx]) if fk[idx] is not None else None
        typ = _maybe_null(rng, sample_text(rng, TYPE_POOL), type_share)
        pname = _maybe_null(rng, sample_text(rng, PARAM_NAME_POOL), name_share)
        rows.append({'Id': pid, 'MethodId': mid, 'Type': typ, 'Name': pname})
    return rows


def build_instance(schema, pool: dict, rng: random.Random) -> dict:
    """Build the instance tables in FK order."""
    sizes = {}
    for t in schema.tables:
        base = TABLE_SIZES.get(t, 50)
        sizes[t] = rng.randint(0, base) if rng.random() < 0.1 else max(1, base + rng.randint(-5, 5))

    repo_rows = _build_repo(schema, rng, sizes.get('Repo', 0))
    solution_rows = _build_solution(schema, rng, sizes.get('Solution', 0), repo_rows)
    method_rows = _build_method(schema, rng, sizes.get('Method', 0), solution_rows)
    mp_rows = _build_method_parameter(schema, rng, sizes.get('MethodParameter', 0), method_rows)
    return {
        'Repo': repo_rows,
        'Solution': solution_rows,
        'Method': method_rows,
        'MethodParameter': mp_rows,
    }
