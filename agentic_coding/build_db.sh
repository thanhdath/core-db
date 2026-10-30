#!/usr/bin/env bash
# Build the CoRE-DB of one training database: agentic_coding/build_db.sh <bird|spider> <db_id>
#
# Environment:
#   ORIGINAL_DB    original SQLite file (BIRD train or Spider database)             [required]
#   GOLDS_JSON     JSON list of the training gold SQL of this database              [required]
#   BUILD_ROOT     build output root (default build)    -> $BUILD_ROOT/<ds>/<db>/
#   COREDB_ROOT    release layout root (default coredb) -> $COREDB_ROOT/dbs/<ds>/<db>/
#   LLM_NEIGHBORS  JSONL files written by neighbor_query_generation.sample_llm_neighbors (optional)
#   AGENTIC=1      rebuild the generation program with the agents (needs OPENROUTER_API_KEY);
#                  default: run the released program value_filling_by_agents/<ds>/<db>/
#   N_UNITS        candidate instances (default 200); COREDB_WORKERS processes (default 4)
set -euo pipefail
ds=${1:?bird|spider}; db=${2:?db_id}
: "${ORIGINAL_DB:?set ORIGINAL_DB}"; : "${GOLDS_JSON:?set GOLDS_JSON}"
here=$(cd "$(dirname "$0")/.." && pwd)
ORIGINAL_DB=$(realpath "$ORIGINAL_DB"); GOLDS_JSON=$(realpath "$GOLDS_JSON")
out=$(realpath -m "${BUILD_ROOT:-build}")/$ds/$db
coredb_root=$(realpath -m "${COREDB_ROOT:-coredb}")
llm_neighbors=()
for f in ${LLM_NEIGHBORS:-}; do llm_neighbors+=("$(realpath "$f")"); done
compact=$out/compact/$db.sqlite
program=$here/value_filling_by_agents/$ds/$db
mkdir -p "$out"
cd "$here"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1

echo "[1/5] compaction"
python -m agentic_coding.compaction.compact --original "$ORIGINAL_DB" --golds "$GOLDS_JSON" --output "$compact"

echo "[2/5] neighbor queries"
python -m agentic_coding.neighbor_query_generation.build_pairs --ds "$ds" --db "$db" --original "$ORIGINAL_DB" \
    --compact "$compact" --golds "$GOLDS_JSON" --out "$out" --llm-neighbors "${llm_neighbors[@]}"

echo "[3/5] value filling"
if [ "${AGENTIC:-0}" = 1 ]; then
  python -m agentic_coding.value_filling.pipeline --ds "$ds" --db "$db" --original "$ORIGINAL_DB" \
      --compact "$compact" --pairs "$out/pairs.json" --out "$out/program"
  program=$out/program
fi
python -m agentic_coding.value_filling.generate --ds "$ds" --db "$db" --compact "$compact" --program "$program" \
    --out "$out" --n-units "${N_UNITS:-200}" --procs "${COREDB_WORKERS:-4}"

echo "[4/5] separation"
python -m agentic_coding.separation --original "$ORIGINAL_DB" --compact "$compact" --out "$out"

echo "[5/5] greedy set-cover selection"
python -m agentic_coding.selection --out "$out" --coredb-root "$coredb_root" --ds "$ds" --db "$db"
