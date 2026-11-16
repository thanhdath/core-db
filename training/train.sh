#!/usr/bin/env bash
# GRPO on CoRE-DB with the FINER-SQL trainer and rewards: one prompt x 32 rollouts per step, lr 8e-6, beta 0.04.
# Usage: DATA_DIR=... GT_CACHE=... CHROMA_SEED=... OUT_DIR=... training/train.sh <0.5b|3b>
set -euo pipefail
: "${DATA_DIR:?}" "${GT_CACHE:?}" "${CHROMA_SEED:?}" "${OUT_DIR:?}"
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT_DIR"
DATA_DIR=$(realpath "$DATA_DIR"); GT_CACHE=$(realpath "$GT_CACHE"); OUT_DIR=$(realpath "$OUT_DIR")
chroma=$OUT_DIR/chroma_db
[ -d "$chroma" ] || cp -r "$CHROMA_SEED" "$chroma"
case "${1:?run: 0.5b | 3b}" in
  0.5b) pd=4 ga=8 util=0.3 steps=13504; model=${MODEL:-griffith-bigdata/FINER-SQL-0.5B-BIRD}
        flags=(--skip_uninformative_members --dynamic_sampling mask --skip_masked_compute) ;;
  3b)   pd=2 ga=16 util=0.14 steps=8892; model=${MODEL:-griffith-bigdata/FINER-SQL-3B-BIRD}
        export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
        chroma run --path "$chroma" --host 127.0.0.1 --port "${CHROMA_PORT:-8031}" > "$OUT_DIR/chroma.log" 2>&1 &
        trap "kill $!" EXIT
        flags=(--ddp_bucket_view --chroma_server "127.0.0.1:${CHROMA_PORT:-8031}") ;;
  *) echo "unknown run $1"; exit 2 ;;
esac
cd "$here"
export PYTHONUNBUFFERED=1 NCCL_CUMEM_ENABLE=0 no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
python -m accelerate.commands.launch --config_file configs/accelerate_1gpu.yaml grpo_writer.py \
  --model_path "$model" --data_root "$DATA_DIR" --gt_cache "$GT_CACHE" --out_dir "$OUT_DIR" \
  --api_url "${API_URL:-http://127.0.0.1:8021/execute}" --chroma_path "$chroma" \
  --max_steps "$steps" --save_steps 250 --save_total_limit 2 --seed 42 --learning_rate 8e-6 --beta 0.04 --loss_type grpo \
  --num_generations 32 --per_device_train_batch_size "$pd" --gradient_accumulation_steps "$ga" \
  --vllm_gpu_memory_utilization "$util" --max_prompt_length 2048 --max_completion_length 2048 \
  --use_vllm --vllm_mode colocate --vllm-no-sleep --use_liger_kernel "${flags[@]}" 2>&1 | tee -a "$OUT_DIR/train.log"
