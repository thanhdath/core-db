#!/usr/bin/env bash
# Serve the CoRE-DB reward endpoint: execution API on the tree + CoRE-DB proxy in front of it.
# Usage: training/serve_coredb.sh <tree from prepare_coredb_tree.py>
# Env: API_PORT (8011), PROXY_PORT (8021). Stop with: kill $(cat <tree>/servers.pid)
set -euo pipefail
tree=$(cd "${1:?tree directory}" && pwd)
app_dir=$(cd "$(dirname "$0")/../db_execution" && pwd)
api_port=${API_PORT:-8011}
proxy_port=${PROXY_PORT:-8021}
export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
BIRD_TRAIN_DB_ROOT=$tree/bird BIRD_DEV_DB_ROOT=$tree/bird SPIDER_DB_ROOT=$tree/spider \
  uvicorn api:app --app-dir "$app_dir" --host 127.0.0.1 --port "$api_port" --workers 16 > "$tree/api.log" 2>&1 &
api_pid=$!
COREDB_UPSTREAM=http://127.0.0.1:$api_port COREDB_TREE=$tree \
  uvicorn bundle_proxy:app --app-dir "$app_dir" --host 127.0.0.1 --port "$proxy_port" --workers 8 \
  > "$tree/proxy.log" 2>&1 &
echo "$api_pid $!" > "$tree/servers.pid"
for _ in $(seq 1 150); do
  curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$proxy_port/healthz/live" && break
  sleep 2
done
echo "CoRE-DB reward endpoint: http://127.0.0.1:$proxy_port/execute"
