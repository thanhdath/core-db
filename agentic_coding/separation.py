"""Step 4: execute the construction pairs on every candidate instance and record the separations.

A pair is *eligible* when the gold is informative on the original database and the neighbor returns the
same result there (the original cannot tell them apart).  An instance *separates* an eligible pair when the
gold is informative on the instance and the two results differ.  Execution errors and timeouts are
``unknown`` and never count as a separation.  The compact database is always instance 0 of the pool.

Output: <out>/separation.json
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import time

from .common import execute_all, has_top_level_order, load_json, pair_status, save_json, sha_text, worker_count


def unit_statuses(job):
    """Status of every eligible pair on one instance."""
    unit, sqls, pairs = job
    results = execute_all(unit, sqls)
    return unit, {p['pair_id']: pair_status(results.get(sha_text(p['gold_sql'])),
                                            results.get(sha_text(p['neighbor_sql'])),
                                            has_top_level_order(p['gold_sql']))
                  for p in pairs}


def eligible_pairs(original, pairs):
    """Pairs whose gold and neighbor agree on the original database."""
    sqls = sorted({p['gold_sql'] for p in pairs} | {p['neighbor_sql'] for p in pairs})
    results = execute_all(original, sqls)
    return [p for p in pairs
            if pair_status(results[sha_text(p['gold_sql'])], results[sha_text(p['neighbor_sql'])],
                           has_top_level_order(p['gold_sql'])) == 'accept']


def separate(original, units, pairs, workers):
    """{unit: [separated pair ids]} plus the eligible pairs."""
    eligible = eligible_pairs(original, pairs)
    needed = sorted({p['gold_sql'] for p in eligible} | {p['neighbor_sql'] for p in eligible})
    with ProcessPoolExecutor(workers) as pool:
        matrix = dict(pool.map(unit_statuses, [(u, needed, eligible) for u in units], chunksize=4))
    separated = {u: sorted(pid for pid, s in statuses.items() if s == 'refuse') for u, statuses in matrix.items()}
    unknown = {u: sum(s == 'unknown' for s in statuses.values()) for u, statuses in matrix.items()}
    return eligible, separated, unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--original', required=True, help='original SQLite database')
    parser.add_argument('--compact', required=True, help='compact SQLite database (instance 0)')
    parser.add_argument('--out', required=True, help='directory with pairs.json and generation.json')
    args = parser.parse_args()
    out, start = Path(args.out), time.time()
    pairs = load_json(out / 'pairs.json')['pairs']
    units = [str(Path(args.compact).resolve())] + load_json(out / 'generation.json')['units']
    eligible, separated, unknown = separate(args.original, units, pairs, worker_count())
    separable = sorted(set().union(*separated.values())) if separated else []
    save_json(out / 'separation.json', {
        'units': units, 'pairs_total': len(pairs),
        'eligible_pair_ids': [p['pair_id'] for p in eligible],
        'eligible_by_source': {s: sum(p['source'] == s for p in eligible) for s in ('grammar', 'llm')},
        'separated': separated, 'unknown_counts': unknown, 'separable_pair_ids': separable,
        'wall_s': round(time.time() - start, 1)})
    print('eligible', len(eligible), 'separable', len(separable), round(time.time() - start, 1), 's')


if __name__ == '__main__':
    main()
