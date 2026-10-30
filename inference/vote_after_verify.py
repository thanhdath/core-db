"""Vote-after-verify selection over the executed candidates of generate_and_execute.py.

Candidates that execute are grouped by their result (header-agnostic set of rows). Groups whose result is empty
or all zeros are skipped; the largest remaining group wins (ties broken by the larger result key) and its
lowest-index candidate is selected. Writes predict_dev.json (BIRD) or pred_dev.sql (Spider) next to the input.

Usage: python inference/vote_after_verify.py <run dir with detailed_results.pkl>
"""
import argparse
import json
import pickle
import re
from collections import defaultdict
from pathlib import Path

PREFIX = 'SUCCESS_VALUES:'
NUMBER = re.compile(r'^[\s\-+]?(\d+(\.\d+)?)$')


def result_key(result):
    """Group key of a successful execution: sorted distinct rows of sorted cell strings, cut at 200 characters."""
    rows = result.get('rows')
    if not isinstance(rows, list):
        return 'SUCCESS_ROWS_COUNT:%s' % result.get('row_count', 0)
    cells = [tuple(sorted(str('' if v is None else v) for v in row.values())) for row in rows if isinstance(row, dict)]
    return PREFIX + ';'.join(sorted({'|'.join(row) for row in cells}))[:200]


def key_values(key):
    """Non-empty row tokens of a SUCCESS_VALUES key."""
    return [token.strip() for token in key[len(PREFIX):].split(';') if token.strip()]


def to_number(token):
    """Absolute value of a numeric token (an optional trailing % allowed), else None."""
    match = NUMBER.match(token[:-1].strip() if token.strip().endswith('%') else token)
    return float(match.group(1)) if match else None


def is_all_zero(values):
    numbers = [x for x in map(to_number, values) if x is not None]
    return bool(numbers) and all(abs(x) < 1e-12 for x in numbers)


def choose_group(sizes):
    """Key of the winning group among {key: size}; None when no group returned rows."""
    candidates = {k: n for k, n in sizes.items() if k.startswith(PREFIX)}
    informative = {k: n for k, n in candidates.items() if key_values(k) and not is_all_zero(key_values(k))}
    pool = informative or candidates
    return max(pool, key=lambda k: (pool[k], k)) if pool else None


def select(sample):
    """(selected SQL, candidate index) of one question; ('', -1) when no candidate executes."""
    groups = defaultdict(list)
    results = sample['candidate_execution_results']
    for index, sql in enumerate(sample['predicted_sqls']):
        result = results[index] if index < len(results) else None
        if sql and sql.strip() and isinstance(result, dict) and result.get('ok', False):
            groups[result_key(result)].append(index)
    winner = choose_group({k: len(v) for k, v in groups.items()})
    if winner is None:
        return '', -1
    index = groups[winner][0]
    return sample['predicted_sqls'][index], index


def write_bird(samples, selections, path):
    entries = [[s.get('question', ''), '%s\t----- bird -----\t%s' % (selections[str(s['sample_id'])], s['db_id'])]
               for s in samples]
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def write_spider(samples, selections, path):
    lines = [re.sub(r'\s+', ' ', selections[str(s['sample_id'])].replace('\r', ' ')).strip() or 'SELECT 1'
             for s in samples]
    path.write_text(''.join(line + '\n' for line in lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir')
    run_dir = Path(parser.parse_args().run_dir)
    with open(run_dir / 'detailed_results.pkl', 'rb') as handle:
        samples = sorted(pickle.load(handle), key=lambda s: int(s['sample_id']))
    chosen = {str(s['sample_id']): select(s) for s in samples}
    (run_dir / 'selection.json').write_text(json.dumps(
        [{'sample_id': s['sample_id'], 'index': chosen[str(s['sample_id'])][1],
          'sql': chosen[str(s['sample_id'])][0]} for s in samples], indent=1))
    selections = {k: sql for k, (sql, _) in chosen.items()}
    if any('bird' in str(s.get('dataset_name', '')).lower() for s in samples):
        write_bird(samples, selections, run_dir / 'predict_dev.json')
    else:
        write_spider(samples, selections, run_dir / 'pred_dev.sql')


if __name__ == '__main__':
    main()
