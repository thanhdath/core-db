#!/usr/bin/env bash
# Official Spider execution accuracy with taoyds/test-suite-sql-eval at commit e97acc54 (cloned on first use).
# Usage: evaluation/spider_test_suite.sh <gold.sql> <pred.sql> <database dir> [out.json]
#   Spider dev:  database dir = <Spider>/database;  Spider test: database dir = <Spider>/test_database
set -euo pipefail
gold=${1:?gold.sql}; pred=${2:?pred.sql}; db=${3:?database dir}
out=${4:-$(dirname "$pred")/spider_exec_persample.json}
here=$(cd "$(dirname "$0")/.." && pwd)
suite=${TEST_SUITE_DIR:-$here/third_party/test-suite-sql-eval}
if [ ! -f "$suite/evaluation.py" ]; then
  git clone -q https://github.com/taoyds/test-suite-sql-eval.git "$suite"
  git -C "$suite" checkout -q e97acc546ecbee8fa27fa8dbf025ef61493a876c
fi
python "$here/evaluation/spider_persample.py" "$suite" "$out" "$gold" "$pred" "$db"
python -c "import json, sys; d = json.load(open(sys.argv[1])); print('EX %d/%d' % (d['correct'], d['n']))" "$out"
