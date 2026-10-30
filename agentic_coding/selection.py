"""Step 5: database instance selection by greedy set cover.

C_i = construction pairs separated by instance i, U = union of all C_i.  Starting from J = {} and R = U,
repeatedly add the instance that separates the most uncovered pairs (ties: lowest index) until R is empty.
The compact database (instance 0) is always kept; set cover adds the fewest generated instances that
separate the pairs it does not separate.  Variants restrict the pairs to one neighbor source.

Output: <out>/selection.json and, with ``--coredb-root``, the members of variant ``full`` in the release layout
<coredb>/dbs/<ds>/<db>/compact/<db>.sqlite and .../units/<unit>.sqlite.
"""
import argparse
import shutil
from pathlib import Path

from .common import load_json, save_json

VARIANTS = {'full': {'grammar', 'llm'}, 'wo_grammar': {'llm'}, 'wo_llm': {'grammar'}}


def select_cover(sets):
    """Greedy set cover over {instance id: set of pair ids}; returns (selected ids, covered union)."""
    universe = set().union(*sets.values()) if sets else set()
    remaining, selected = set(universe), []
    while remaining:
        gain, _, best = min((-len(covered & remaining), int(unit), unit)
                            for unit, covered in sets.items() if unit not in selected)
        if gain == 0:
            raise ValueError('uncovered pairs that no instance separates')
        selected.append(best)
        remaining -= sets[best]
    return selected, universe


def select_variant(separation, source_of, sources):
    """Selected instance paths for one variant (compact database first)."""
    index = {unit: i for i, unit in enumerate(separation['units'])}
    sets = {str(index[u]): {pid for pid in pids if source_of[pid] in sources}
            for u, pids in separation['separated'].items()}
    by_base = sets.get('0', set())
    rest = {k: v - by_base for k, v in sets.items() if k != '0' and v - by_base}
    chosen, universe = select_cover(rest) if rest else ([], set())
    return {'sources': sorted(sources),
            'units': [separation['units'][0]] + [separation['units'][int(i)] for i in chosen],
            'separated_by_base': len(by_base),
            'separated_pairs': len(by_base | universe)}


def export(members, build_dir, target, db):
    """Copy the compact database, the selected instances and selection.json to ``target``."""
    (target / 'compact').mkdir(parents=True, exist_ok=True)
    (target / 'units').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(members[0], target / 'compact' / (db + '.sqlite'))
    for unit in members[1:]:
        shutil.copyfile(unit, target / 'units' / Path(unit).name)
    shutil.copyfile(Path(build_dir) / 'selection.json', target / 'selection.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True, help='directory with pairs.json and separation.json')
    parser.add_argument('--coredb-root', help='release root to copy the selected members to')
    parser.add_argument('--ds', choices=['bird', 'spider'])
    parser.add_argument('--db')
    args = parser.parse_args()
    if args.coredb_root and not (args.ds and args.db):
        parser.error('--coredb-root needs --ds and --db')
    out = Path(args.out)
    source_of = {p['pair_id']: p['source'] for p in load_json(out / 'pairs.json')['pairs']}
    separation = load_json(out / 'separation.json')
    result = {name: select_variant(separation, source_of, sources) for name, sources in VARIANTS.items()}
    result['wo_selection'] = {'units': separation['units']}
    save_json(out / 'selection.json', result)
    if args.coredb_root:
        export(result['full']['units'], out, Path(args.coredb_root) / 'dbs' / args.ds / args.db, args.db)
    print({k: len(v['units']) for k, v in result.items()})


if __name__ == '__main__':
    main()
