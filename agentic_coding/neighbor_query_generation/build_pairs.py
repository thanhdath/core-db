"""Construction pairs (gold, neighbor) of one database.

Golds: the training gold queries of the database that are informative on the original database.
Neighbors, at most ``--per-gold`` per gold and source, chosen deterministically:
  grammar  grammar mutations of the gold (``grammar_mutations.py``) that compile in SQLite;
  llm      LLM-written queries for the same question (``sample_llm_neighbors.py`` output).
Whether a pair is eligible (same result as the gold on the original) is decided in the separation step.

Output: <out>/pairs.json
"""
import argparse
import json
import random
from pathlib import Path

from ..common import connect, execute, read_jsonl, save_json, schema_columns, sha_text
from .grammar_mutations import neighbor_queries


def normalise(sql):
    """Whitespace- and case-insensitive form used to drop duplicates of the gold."""
    return ' '.join((sql or '').strip().rstrip(';').split()).lower()


def capped(gold, candidates, per_gold):
    """At most ``per_gold`` distinct candidates, sampled with a seed derived from the gold."""
    unique = sorted({c for c in candidates if normalise(c) != normalise(gold)})
    if len(unique) > per_gold:
        unique = sorted(random.Random(int(sha_text(gold), 16) % (2 ** 32)).sample(unique, per_gold))
    return unique


def informative_golds(original, golds):
    """Golds that run on the original and return at least one non-NULL value."""
    connection = connect(original)
    kept = set()
    for gold in golds:
        result = execute(connection, gold)
        if result['ok'] and result['informative']:
            kept.add(gold)
    connection.close()
    return sorted(kept)


def grammar_neighbors(gold, columns, compact_connection):
    """Grammar mutations of ``gold`` that SQLite can compile on the compact database."""
    def compiles(sql):
        try:
            compact_connection.execute('EXPLAIN ' + sql)
            return True
        except Exception:
            return False
    try:
        return [q for q in neighbor_queries(gold, columns, rng=random.Random(42)) if compiles(q)]
    except Exception:
        return []


def llm_neighbors_by_gold(paths, ds, db):
    """{gold: [prediction, ...]} from sample_llm_neighbors.py outputs."""
    by_gold = {}
    for path in paths:
        for row in read_jsonl(path):
            if row['ds'] == ds and row['db'] == db and row.get('pred'):
                by_gold.setdefault(row['gold'], []).append(row['pred'])
    return by_gold


def build_pairs(ds, db, original, compact, golds, llm_files, per_gold):
    """All construction pairs of one database."""
    golds = informative_golds(original, golds)
    columns = {c.upper() for names in schema_columns(original).values() for c in names}
    compact_connection = connect(compact)
    llm = llm_neighbors_by_gold(llm_files, ds, db)
    pairs = []
    for gold in golds:
        sources = (('grammar', grammar_neighbors(gold, columns, compact_connection)), ('llm', llm.get(gold, [])))
        for source, candidates in sources:
            for neighbor in capped(gold, candidates, per_gold):
                pairs.append({'pair_id': len(pairs), 'source': source, 'gold_sql': gold, 'neighbor_sql': neighbor})
    compact_connection.close()
    return golds, pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ds', required=True, choices=['bird', 'spider'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--original', required=True, help='original SQLite database')
    parser.add_argument('--compact', required=True, help='compact SQLite database (step 1)')
    parser.add_argument('--golds', required=True, help='JSON list of the training gold SQL of this database')
    parser.add_argument('--llm-neighbors', nargs='*', default=[], help='JSONL files from sample_llm_neighbors.py')
    parser.add_argument('--per-gold', type=int, default=5)
    parser.add_argument('--out', required=True, help='output directory of this database')
    args = parser.parse_args()
    golds, pairs = build_pairs(args.ds, args.db, args.original, args.compact,
                               json.loads(Path(args.golds).read_text()), args.llm_neighbors, args.per_gold)
    counts = {s: sum(p['source'] == s for p in pairs) for s in ('grammar', 'llm')}
    save_json(Path(args.out) / 'pairs.json', {'ds': args.ds, 'db': args.db, 'golds': golds, 'pairs': pairs,
                                              'counts': dict(counts, golds=len(golds)), 'per_gold': args.per_gold})
    print(args.db, len(golds), counts)


if __name__ == '__main__':
    main()
