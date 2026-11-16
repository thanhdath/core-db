"""CLI: python -m tscore_gen.cli generate ..."""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

from .literals import extract_typed_values, seed_literal_pool_from_queries
from .schema import read_schema
from .writer import unit_path, write_instance_sqlite

_G: dict = {}


def _init(orig: str, pool: dict, args: dict) -> None:
    """Worker initializer: read the original ONCE per process."""
    from .spec_sampler import build_spec_rows
    _G['schema'] = read_schema(orig)
    _G['pool'] = pool
    _G['args'] = args
    _G['build'] = build_spec_rows


def _one(i: int) -> dict:
    """Build, copy and write unit i."""
    a = _G['args']
    p = unit_path(a['root'], a['ds'], a['db'], i, a['tag'])
    rep = {'ok': True, 'err': None, 'added': {}, 'skipped': {}}
    if os.path.exists(p):
        rep['err'] = 'Exists'
        return rep
    try:
        rng = random.Random(a['seed_base'] * 100003 + i)
        rows = _G['build'](_G['schema'], _G['pool'], rng, a['sizes'])
        added, skipped = write_instance_sqlite(_G['schema'], rows, p, a['orig'])
        rep['added'] = added
        rep['skipped'] = skipped
        if sum(skipped.values()) > 0:
            rep['ok'] = False
            rep['err'] = 'RowsSkipped'
    except Exception as e:
        print('unit %d failed: %r' % (i, e), file=sys.stderr)
        rep['ok'] = False
        rep['err'] = type(e).__name__
    return rep


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
    _augment_pool_from_sqls(good, schema)
    pool = seed_literal_pool_from_queries(good, schema)
    args = {'root': a.root, 'ds': a.ds, 'db': a.db, 'tag': a.tag,
            'seed_base': a.seed_base, 'orig': a.orig, 'sizes': None}
    idx = list(range(a.i0, a.i1))
    if a.procs <= 1 or len(idx) < 50:
        _init(a.orig, pool, args)
        res = [_one(i) for i in idx]
    else:
        with mp.Pool(a.procs, initializer=_init, initargs=(a.orig, pool, args)) as P:
            res = P.map(_one, idx, chunksize=max(1, len(idx) // (a.procs * 4)))
    errs: dict = {}
    added: dict = {}
    skipped_rows: dict = {}
    for r in res:
        if not r['ok']:
            k = r['err'] or 'unknown'
            errs[k] = errs.get(k, 0) + 1
        for t, n in r['added'].items():
            added[t] = added.get(t, 0) + n
        for t, n in r['skipped'].items():
            skipped_rows[t] = skipped_rows.get(t, 0) + n
    n_ok = sum(1 for r in res if r['ok'])
    print(json.dumps({'db': a.db, 'n_ok': n_ok, 'n_fail': len(res) - n_ok,
                      'wall_s': round(time.time() - t0, 2), 'pool_sqls': len(good),
                      'pool_skipped': skipped,
                      'pool_values': sum(len(v) for v in pool.values()),
                      'errors': errs, 'rows_added': added, 'rows_skipped': skipped_rows}))


_SPEC_LITERALS = {
    ('company', 'HEADQUARTERS'): ['USA', 'USA%', '%USA%', 'usa', 'USB', 'USA x', 'USAx', 'Netherlands',
                                  'China', 'UK', 'Brazil', 'Russia', 'Germany', 'France'],
    ('company', 'SALES_IN_BILLION'): ['199.9', '200.0', '200.1', '200.9', '201.0', '201.1'],
    ('company', 'INDUSTRY'): ['Oil and gas', 'oil and gas', 'Banking', 'Conglomerate', 'Retailing', 'Automotive'],
}


def _augment_pool_from_sqls(sqls: list, schema) -> None:
    """Merge the specification literals into the schema's observed-value pools (read-only use)."""
    for (t, c), vals in _SPEC_LITERALS.items():
        key = None
        for tn, tm in schema.tables.items():
            if tn.lower() != t:
                continue
            for cm in tm.columns:
                if cm.name.upper() == c:
                    key = (tn, cm.name)
        if key is None:
            continue
        bucket = schema.original_values.setdefault(key, [])
        for v in vals:
            try:
                cast = int(float(v)) if _isnum(v) and _looks_int(schema.tables[key[0]], key[1]) else (
                    float(v) if _isnum(v) else v)
            except (TypeError, ValueError):
                cast = v
            if cast not in bucket:
                bucket.append(cast)


def _isnum(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _looks_int(table_meta, colname) -> bool:
    for c in table_meta.columns:
        if c.name == colname:
            t = (c.type_str or '').lower()
            return 'int' in t and 'real' not in t and 'float' not in t
    return False


if __name__ == '__main__':
    main()
