"""Turn the CoRE-DB release layout into the database tree and members.json served during training.

Input (HF dataset thanhdath/core-db):
    <coredb>/dbs/<ds>/<db>/compact/<db>.sqlite
    <coredb>/dbs/<ds>/<db>/units/<db>__dc_NNNN.sqlite
Output:
    <tree>/<ds>/<db>/<db>.sqlite                  -> compact database (member 0)
    <tree>/<ds>/<unit>/<unit>.sqlite              -> one selected instance
    <tree>/members.json                           {db: [db, unit, ...]}
Files are symlinked (``--copy`` copies them instead).
"""
import argparse
import json
import os
import shutil
from pathlib import Path


def place(source, target, copy):
    """Symlink (or copy) one SQLite file into the tree."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    if copy:
        shutil.copyfile(source, target)
    else:
        os.symlink(Path(source).resolve(), target)


def build_tree(coredb, tree, copy=False):
    """Create the tree; returns {db: members}."""
    members = {}
    for db_dir in sorted(Path(coredb, 'dbs').glob('*/*')):
        ds, db = db_dir.parent.name, db_dir.name
        compact = db_dir / 'compact' / (db + '.sqlite')
        if not compact.exists():
            continue
        place(compact, Path(tree, ds, db, db + '.sqlite'), copy)
        units = sorted((db_dir / 'units').glob('*.sqlite'))
        for unit in units:
            place(unit, Path(tree, ds, unit.stem, unit.name), copy)
        members[db] = [db] + [u.stem for u in units]
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--coredb', required=True, help='local copy of thanhdath/core-db')
    parser.add_argument('--tree', required=True, help='output tree directory')
    parser.add_argument('--copy', action='store_true')
    args = parser.parse_args()
    members = build_tree(args.coredb, args.tree, args.copy)
    Path(args.tree, 'members.json').write_text(json.dumps(members, indent=1))
    print(len(members), 'databases,', sum(len(m) for m in members.values()), 'members')


if __name__ == '__main__':
    main()
