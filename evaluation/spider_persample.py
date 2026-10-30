"""Run the official Spider evaluator (test-suite-sql-eval ``evaluation.py``, execution match) and save its
per-question verdicts; ``eval_exec_match`` is wrapped, not modified.

Usage: python spider_persample.py <test-suite-sql-eval dir> <out.json> <gold.sql> <pred.sql> <database dir>
"""
import json
import os
import sys


def main():
    evaluator_dir, out_json, gold, pred, db_dir = sys.argv[1:6]
    sys.path.insert(0, os.path.abspath(evaluator_dir))
    import evaluation

    verdicts = []
    official_exec_match = evaluation.eval_exec_match

    def recording_exec_match(*args, **kwargs):
        result = official_exec_match(*args, **kwargs)
        verdicts.append(int(bool(result)))
        return result

    evaluation.eval_exec_match = recording_exec_match
    evaluation.evaluate(gold, pred, db_dir, 'exec', None, False, False, False)
    with open(out_json, 'w') as handle:
        json.dump({'exec': verdicts, 'correct': sum(verdicts), 'n': len(verdicts)}, handle)


if __name__ == '__main__':
    main()
