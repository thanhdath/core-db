#!/usr/bin/env bash
# RQ2 table: BIRD dev EX, Spider dev EX and Spider test EX (test-suite-sql-eval) of the three released models,
# k = 30, T = 1.0, seed 42 + vote-after-verify, and greedy decoding.
#
# Usage: scripts/reproduce_rq2.sh [limit]        (limit = first N questions per benchmark; default all)
# Env:   BIRD_DEV_ROOT (default data/bird/dev), SPIDER_ROOT (default data/spider), MODELS ("0.5b 1.5b 3b"),
#        DECODINGS ("k30 greedy"), BENCHMARKS ("bird_dev spider_dev spider_test")
set -euo pipefail
cd "$(dirname "$0")/.."
limit=${1:-0}
for model in ${MODELS:-0.5b 1.5b 3b}; do
  for benchmark in ${BENCHMARKS:-bird_dev spider_dev spider_test}; do
    for decoding in ${DECODINGS:-k30 greedy}; do
      python scripts/run_inference.py --model "$model" --benchmark "$benchmark" --decoding "$decoding" \
        --limit "$limit" --bird-dev-root "${BIRD_DEV_ROOT:-data/bird/dev}" --spider-root "${SPIDER_ROOT:-data/spider}"
    done
  done
done
python - <<'PY'
import json, pathlib
rows = [json.loads(p.read_text()) for p in sorted(pathlib.Path('outputs').glob('*/*/RESULT.json'))]
for r in rows:
    print('%-32s %-12s %-7s %5d/%-5d %6.2f' % (r['model'], r['benchmark'], r['decoding'], r['correct'], r['n'], r['ex_pct']))
PY
