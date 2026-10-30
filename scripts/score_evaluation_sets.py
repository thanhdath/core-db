"""Score CoRE-DB against the original databases on the RQ3 / RQ6 evaluation sets (``evaluation_sets/``).

Every case is a (gold SQL, predicted SQL) pair of a training question with a reference label:
  spurious  original match AND semantically wrong (3-LLM majority);
  correct   original match AND semantically correct;
  wrong     original mismatch, prediction error or gold error.
Verdicts: ``original`` on the official training database alone, ``coredb`` aggregated over the CoRE-DB members
(any refusal refuses, otherwise any unknown is unknown).  Positive = accepted as correct:
FPR = accepted (spurious + wrong) / (spurious + wrong), FNR = refused correct / correct; unknown verdicts stay in
the denominators.

Usage:
    python scripts/score_evaluation_sets.py --set rq3_3b --coredb data/core-db \
        --bird-train-root data/bird/train/train_databases --spider-root data/spider
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from agentic_coding.common import (coredb_verdict, execute_all, has_top_level_order, pair_status,  # noqa: E402
                                   read_jsonl, sha_text)
from scripts.coredb_members import coredb_members, original_database  # noqa: E402

SETS = {
    'rq3_05b': REPO / 'evaluation_sets' / 'rq3_spurious_train200_05b.jsonl',
    'rq3_3b': REPO / 'evaluation_sets' / 'rq3_spurious_train200_3b.jsonl',
    'rq6_sample300': REPO / 'evaluation_sets' / 'rq6_rollout_sample300.jsonl',
}


def normalise_case(case):
    """Fields used for scoring: case_id, ds, db, gold, pred and the reference label."""
    return {'case_id': case['case_id'], 'ds': case['ds'], 'db': case['db'], 'gold': case['gold_sql'],
            'pred': case['pred_sql'] or '', 'reference': case['label']}


def database_verdicts(cases, original, members):
    """{case_id: {"original": verdict, "coredb": verdict}} for the cases of one database."""
    sqls = sorted({c['gold'] for c in cases} | {c['pred'] for c in cases if c['pred']})
    on_original = execute_all(original, sqls) if original.exists() else {}
    on_members = [execute_all(m, sqls) for m in members]
    verdicts = {}
    for case in cases:
        if not case['pred']:
            verdicts[case['case_id']] = {'original': 'unknown', 'coredb': 'unknown'}
            continue
        gold, pred, ordered = sha_text(case['gold']), sha_text(case['pred']), has_top_level_order(case['gold'])
        original_status = pair_status(on_original.get(gold), on_original.get(pred), ordered)
        verdicts[case['case_id']] = {
            'original': coredb_verdict([original_status]),
            'coredb': coredb_verdict([pair_status(m.get(gold), m.get(pred), ordered) for m in on_members])
            if on_members else 'unknown'}
    return verdicts


def table_row(cases, verdicts, setting):
    """Confusion counts and rates of one setting."""
    counts = Counter((c['reference'], verdicts[c['case_id']][setting]) for c in cases)
    size = Counter(c['reference'] for c in cases)
    incorrect = size['spurious'] + size['wrong']
    accepted_incorrect = counts['spurious', 'accept'] + counts['wrong', 'accept']
    return {'setting': setting, 'cases': len(cases),
            'spurious': size['spurious'], 'spurious_refused': counts['spurious', 'refuse'],
            'spurious_accepted': counts['spurious', 'accept'], 'spurious_unknown': counts['spurious', 'unknown'],
            'correct': size['correct'], 'correct_refused': counts['correct', 'refuse'],
            'correct_unknown': counts['correct', 'unknown'],
            'wrong': size['wrong'], 'wrong_accepted': counts['wrong', 'accept'],
            'FPR_pct': round(100.0 * accepted_incorrect / incorrect, 1) if incorrect else None,
            'FNR_pct': round(100.0 * counts['correct', 'refuse'] / size['correct'], 1) if size['correct'] else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--set', required=True, choices=sorted(SETS))
    parser.add_argument('--coredb', required=True, help='local copy of thanhdath/core-db')
    parser.add_argument('--bird-train-root', default='data/bird/train/train_databases')
    parser.add_argument('--spider-root', default='data/spider')
    parser.add_argument('--out', default=None, help='optional JSON output (table + per-case verdicts)')
    args = parser.parse_args()
    cases = [normalise_case(c) for c in read_jsonl(SETS[args.set])]
    by_db = defaultdict(list)
    for case in cases:
        by_db[(case['ds'], case['db'])].append(case)
    verdicts = {}
    for (ds, db), db_cases in sorted(by_db.items()):
        original = original_database(ds, db, args.bird_train_root, args.spider_root)
        verdicts.update(database_verdicts(db_cases, original, coredb_members(args.coredb, ds, db)))
    table = [table_row(cases, verdicts, s) for s in ('original', 'coredb')]
    print('| Setting | FPR % | FNR % | spurious refused / accepted / unknown | correct refused | wrong accepted |')
    print('|---|---:|---:|---:|---:|---:|')
    for row in table:
        print('| %s | %s | %s | %d / %d / %d (of %d) | %d (of %d) | %d (of %d) |' % (
            row['setting'], row['FPR_pct'], row['FNR_pct'], row['spurious_refused'], row['spurious_accepted'],
            row['spurious_unknown'], row['spurious'], row['correct_refused'], row['correct'], row['wrong_accepted'],
            row['wrong']))
    if args.out:
        Path(args.out).write_text(json.dumps({'set': args.set, 'table': table, 'verdicts': verdicts}, indent=1))


if __name__ == '__main__':
    main()
