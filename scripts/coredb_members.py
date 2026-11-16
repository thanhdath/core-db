"""Locate CoRE-DB members and the official databases; download CoRE-DB from HF ``griffith-bigdata/core-db-der215``."""
import argparse
from pathlib import Path

COREDB_REPO = 'griffith-bigdata/core-db-der215'


def download_coredb(out, dbs=None, cache_dir=None):
    """Download the CoRE-DB dataset (optionally only some databases); returns the local root."""
    from huggingface_hub import snapshot_download
    patterns = ['README.md', '*.json'] + (['dbs/*/%s/*' % d for d in dbs] + ['dbs/*/%s/*/*' % d for d in dbs]
                                          if dbs else ['dbs/*'])
    return Path(snapshot_download(COREDB_REPO, repo_type='dataset', local_dir=out, allow_patterns=patterns,
                                  cache_dir=cache_dir))


def coredb_members(coredb_root, ds, db):
    """[compact database, selected instances...] of one database (empty when absent)."""
    base = Path(coredb_root) / 'dbs' / ds / db
    compact = base / 'compact' / (db + '.sqlite')
    if not compact.exists():
        return []
    return [compact] + sorted((base / 'units').glob('*.sqlite'))


def original_database(ds, db, bird_train_root, spider_root):
    """Official training database of a BIRD-train or Spider question."""
    if ds == 'bird':
        return Path(bird_train_root) / db / (db + '.sqlite')
    return Path(spider_root) / 'database' / db / (db + '.sqlite')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default='data/core-db')
    parser.add_argument('--dbs', nargs='*', default=None)
    args = parser.parse_args()
    print(download_coredb(args.out, args.dbs))


if __name__ == '__main__':
    main()
