"""RQ1: spurious-correctness rate measured with CoRE-DB.

A prediction is an *original match* when it returns the gold's result on the official training database
(comparator positional_bag_v1).  An original match is *spurious* when CoRE-DB refuses it: gold and
prediction return different results on at least one CoRE-DB member (compact database or selected
instance).  Spurious rate = spurious matches / original matches, per decoding.

Input: JSON lines with ds, db, gold_sql, pred_sql (e.g. scripts/rq1_decode.py output).
Usage:
    python scripts/rq1_spurious_rate.py --predictions outputs/rq1/finer05b.jsonl --coredb data/core-db \
        --bird-train-root data/bird/train/train_databases --spider-root data/spider
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentic_coding.common import (coredb_verdict, execute_all, has_top_level_order, pair_status,  # noqa: E402
                                   read_jsonl, sha_text)
from scripts.coredb_members import coredb_members, original_database  # noqa: E402


def verdicts_for_database(rows, original, members):
    """(original status, CoRE-DB verdict) for every row of one database."""
    sqls = sorted({r['gold_sql'] for r in rows} | {r['pred_sql'] for r in rows if r['pred_sql']})
    on_original = execute_all(original, sqls)
    on_members = [execute_all(m, sqls) for m in members]
    out = []
    for row in rows:
        gold, pred, ordered = sha_text(row['gold_sql']), sha_text(row['pred_sql']), has_top_level_order(row['gold_sql'])
        original_status = pair_status(on_original.get(gold), on_original.get(pred), ordered) if row['pred_sql'] \
            else 'unknown'
        statuses = [pair_status(m.get(gold), m.get(pred), ordered) for m in on_members]
        out.append((original_status, coredb_verdict(statuses) if members else 'no_coredb'))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--coredb', required=True, help='local copy of thanhdath/core-db')
    parser.add_argument('--bird-train-root', default='data/bird/train/train_databases')
    parser.add_argument('--spider-root', default='data/spider')
    parser.add_argument('--out', default=None, help='optional JSON summary path')
    args = parser.parse_args()
    by_db = defaultdict(list)
    for row in read_jsonl(args.predictions):
        by_db[(row['ds'], row['db'])].append(row)
    counts = defaultdict(Counter)
    for (ds, db), rows in sorted(by_db.items()):
        original = original_database(ds, db, args.bird_train_root, args.spider_root)
        verdicts = verdicts_for_database(rows, original, coredb_members(args.coredb, ds, db))
        for row, (original_status, verdict) in zip(rows, verdicts):
            decoding = row.get('decoding', 'all')
            counts[decoding]['predictions'] += 1
            if original_status == 'accept':
                counts[decoding]['original_matches'] += 1
                counts[decoding]['coredb_' + verdict] += 1
    summary = {d: dict(c, spurious_rate_pct=round(100.0 * c['coredb_refuse'] / c['original_matches'], 1)
                       if c['original_matches'] else None) for d, c in counts.items()}
    print(json.dumps(summary, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=1) + '\n')


if __name__ == '__main__':
    main()
