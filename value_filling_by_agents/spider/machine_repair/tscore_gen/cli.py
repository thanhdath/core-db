"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .instance import build_random_instance
from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .spec import load_spec, default_spec
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args


def _one(i: int) -> tuple:
    """Build and write unit i; returns (i, '') or (i, exception type name)."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        inst = build_random_instance(_G['schema'], _G['pool'], a['spec'], rng)
        write_instance_sqlite(_G['schema'], inst, p, orig=a['orig'])
        return (i, '')
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        return (i, type(e).__name__)


def _locate_spec(explicit: str) -> dict:
    """Specification written by the pipeline, if present; otherwise the built-in default."""
    for cand in ([explicit] if explicit else []) + [os.path.join(os.path.dirname(__file__), 'specification.json'),
                                                    'tscore_gen/specification.json']:
        if cand and os.path.exists(cand):
            try:
                return load_spec(cand)
            except Exception as e:  # pragma: no cover
                print('spec %s unusable: %r' % (cand, e), file=sys.stderr)
    return default_spec()


def _split_spec_column(key):
    """'table.col' -> (table, col); (table, col) passes through; anything else -> (None, None)."""
    if isinstance(key, (tuple, list)) and len(key) == 2:
        return str(key[0]), str(key[1])
    if isinstance(key, str) and '.' in key:
        t, c = key.split('.', 1)
        return t, c
    return None, None


def _merge_spec_literal_pool(schema, pool: dict, spec: dict) -> None:
    """Add spec literal pools (planted literals such as value_points 70) to the query pool."""
    lit = spec.get('literal_pool') or {}
    if not isinstance(lit, dict):
        return
    for key, vals in lit.items():
        t, c = _split_spec_column(key)
        if not t or not c:
            continue
        tab = next((tn for tn in schema.tables if tn.lower() == t.lower()), None)
        if tab is None:
            continue
        col = next((cm.name for cm in schema.tables[tab].columns if cm.name.lower() == c.lower()), None)
        if col is None:
            continue
        target = (tab, col)
        pool.setdefault(target, [])
        if isinstance(vals, (list, tuple)):
            pool[target].extend(str(v) for v in vals)
        elif vals is not None:
            pool[target].append(str(vals))


def main(argv=None) -> None:
    """Entry point."""
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('generate')
    for k in ('--db', '--orig', '--ds', '--root', '--pool-sqls'):
        g.add_argument(k, required=True)
    g.add_argument('--i0', type=int, default=0)
    g.add_argument('--i1', type=int, default=800)
    g.add_argument('--seed-base', type=int, default=42)
    g.add_argument('--procs', type=int, default=6)
    g.add_argument('--tag', default='gen')
    g.add_argument('--spec', default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    with open(a.pool_sqls) as f:
        sqls = [s for s in json.load(f) if isinstance(s, str)]
    good, skipped = [], 0
    for s in sqls:
        try:
            extract_typed_values(s)
            good.append(s)
        except Exception:
            skipped += 1
    schema = read_schema(a.orig)
    spec = _locate_spec(a.spec)
    pool = seed_literal_pool_from_queries(good, schema)
    _merge_spec_literal_pool(schema, pool, spec)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag, 'seed_base': a.seed_base,
            'spec': spec, 'orig': a.orig}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _G.update(schema=schema, pool=pool, args=args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    rows_added: dict = {}
    rows_skipped: dict = {}
    n_ok = 0
    for i, r in res:
        if r:
            errs[r] = errs.get(r, 0) + 1
        else:
            n_ok += 1
        try:
            mp_ = unit_path(a.root, a.ds, a.db, i, a.tag) + '.stats'
            if os.path.exists(mp_):
                with open(mp_) as f:
                    st = json.load(f)
                for t, k in st.get('rows_ok', {}).items():
                    rows_added[t] = rows_added.get(t, 0) + int(k)
                for t, k in st.get('rows_failed', {}).items():
                    rows_skipped[t] = rows_skipped.get(t, 0) + int(k)
        except Exception:
            pass
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good), 'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()), 'errors': errs,
                      'rows_added': rows_added, 'rows_skipped': rows_skipped}))


if __name__ == '__main__':
    main()
