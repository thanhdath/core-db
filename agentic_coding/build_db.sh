#!/usr/bin/env bash
# Build the CoRE-DB of one training database: agentic_coding/build_db.sh <bird|spider> <db_id>
# Env: ORIGINAL_DB (required); GOLDS_JSON (steps 1 and 2) or COMPACT_DB + PAIRS_JSON (reuse instead of steps 1 and 2);
#      LLM_NEIGHBORS, BUILD_ROOT (build), COREDB_ROOT (coredb), N_UNITS (200), COREDB_WORKERS (4),
#      AGENTIC=1 with OPENROUTER_API_KEY (write the generation program again with the agents)
set -euo pipefail
ds=${1:?bird|spider}; db=${2:?db_id}
: "${ORIGINAL_DB:?set ORIGINAL_DB}"
[ -n "${COMPACT_DB:-}" ] && [ -n "${PAIRS_JSON:-}" ] || : "${GOLDS_JSON:?set GOLDS_JSON}"
here=$(cd "$(dirname "$0")/.." && pwd)
ORIGINAL_DB=$(realpath "$ORIGINAL_DB"); GOLDS_JSON=${GOLDS_JSON:+$(realpath "$GOLDS_JSON")}
out=$(realpath -m "${BUILD_ROOT:-build}")/$ds/$db
coredb_root=$(realpath -m "${COREDB_ROOT:-coredb}")
llm_neighbors=()
for f in ${LLM_NEIGHBORS:-}; do llm_neighbors+=("$(realpath "$f")"); done
compact_db=${COMPACT_DB:+$(realpath "$COMPACT_DB")}; pairs_json=${PAIRS_JSON:+$(realpath "$PAIRS_JSON")}
compact=$out/compact/$db.sqlite
program=$here/value_filling_by_agents/$ds/$db
mkdir -p "$out"
cd "$here"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1

echo "[1/5] compaction"
if [ -n "$compact_db" ]; then
  mkdir -p "$out/compact" && cp "$compact_db" "$compact"
else
  python -m agentic_coding.compaction.compact --original "$ORIGINAL_DB" --golds "$GOLDS_JSON" --output "$compact"
fi

echo "[2/5] neighbor queries"
if [ -n "$pairs_json" ]; then
  cp "$pairs_json" "$out/pairs.json"
else
  python -m agentic_coding.neighbor_query_generation.build_pairs --ds "$ds" --db "$db" --original "$ORIGINAL_DB" \
      --compact "$compact" --golds "$GOLDS_JSON" --out "$out" --llm-neighbors "${llm_neighbors[@]}"
fi

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
