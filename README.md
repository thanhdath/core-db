# Boosting Small Language Models for Text-to-SQL with Cost-Efficient Reinforcement Environment against Spurious Correctness

Small language models (SLMs) make Text-to-SQL practical in settings with limited inference memory and computation, while
reinforcement learning (RL) can further improve their accuracy without increasing model size. However, execution-based
rewards are vulnerable to **spurious correctness**: a semantically incorrect query may return the same result as the
gold query on the current database state, yet produce different results after valid database updates. Such accidental
matches lead to false-positive rewards that reinforce incorrect SQL generation. To reduce such false-positive rewards,
we propose **CoRE-DB, a reusable, compact, counterexample-enriched database environment**. CoRE-DB first compacts each
training database while preserving the execution results of its gold queries. It then constructs plausible but
semantically incorrect variations of these queries, referred to as neighbor queries, to identify cases where the
original database fails to distinguish correct from incorrect SQL. To expose these hidden errors, **three LLM agents
collaborate to develop a reusable Python generation program**: the Designer specifies generation strategies and
constraints, the Engineer implements them in Python, and the Reviewer validates the program for correctness and
consistency. The program generates diverse database instances that satisfy applicable integrity constraints and semantic
rules. Each instance is evaluated by executing gold–neighbor query pairs to identify counterexamples where their results
differ, providing more discriminative execution feedback without substantially increasing training overhead. The
resulting environment can be reused across training runs without requiring changes to the RL algorithm. Experiments on
Spider and BIRD demonstrate that training Text-to-SQL models on CoRE-DB improves execution and test-suite accuracy by
1–4%, while achieving a 1.51× training speedup.

## Install

```bash
conda create -n coredb python=3.11 -y && conda activate coredb
pip install -r requirements.txt
pip install flash-attn --no-build-isolation
python scripts/coredb_members.py --out data/core-db   # CoRE-DB
```

Download the official BIRD and Spider databases to `data/bird/dev/`, `data/bird/train/train_databases/` and
`data/spider/` (or pass `--bird-dev-root`, `--bird-train-root`, `--spider-root`), and the test-suite databases of
taoyds/test-suite-sql-eval to `data/test_suite_database/` for Spider dev TS. Models and prompts are downloaded from the
Hugging Face Hub on first use.

## Repository layout

| Path | Content |
|---|---|
| `scripts/` | CoRE-DB download, inference and scoring |
| `db_execution/` | SQLite execution API and CoRE-DB proxy |
| `inference/` | candidate generation with vLLM |
| `evaluation/` | official BIRD script and Spider test-suite wrapper |
| `evaluation_sets/` | training questions and labelled (gold, predicted) SQL pairs |
| `agentic_coding/` | CoRE-DB build steps, run by `build_db.sh` |
| `value_filling_by_agents/` | generation program, specification and literal pool of each of the 215 training databases |
| `training/` | GRPO training, reward and reward endpoint |

## Reproduce

### RQ2: execution accuracy

k = 30 candidates at temperature 1.0 + majority voting, or greedy decoding. BIRD dev is scored with the official BIRD script, Spider dev and Spider test with
taoyds/test-suite-sql-eval.

```bash
python scripts/run_inference.py --model 0.5b --benchmark bird_dev --decoding k30
bash scripts/reproduce_rq2.sh # 3 models x {bird_dev, spider_dev, spider_test} x {k30, greedy}
```

Each run writes `outputs/<model>/<benchmark>_<decoding>/RESULT.json`. BIRD dev EX (1,534 questions):

| Model | k = 30 + MV | Greedy |
|---|---:|---:|
| FINER-SQL-0.5B-v2 | 53.59 % | 43.87 % |
| FINER-SQL-1.5B-v2 | 63.75 % | 53.65 % |
| FINER-SQL-3B-v2 | 68.77 % | 60.69 % |

k = 30 numbers vary by about ±0.1 across runs; the paper reports 53.59, 63.82 and 68.84.

### RQ1: spurious-correctness rate

20 samples at temperature 1.0 + one greedy output for each of the 200 questions of the evaluation set
(`evaluation_sets/rq1_questions200.jsonl`). A prediction that matches the gold on the original database but not on CoRE-DB
is spurious.

```bash
python scripts/rq1_decode.py --model griffith-bigdata/FINER-SQL-0.5B-v2 --out outputs/rq1/finer05b.jsonl
python scripts/rq1_spurious_rate.py --predictions outputs/rq1/finer05b.jsonl --coredb data/core-db
```

### RQ3 and RQ6: CoRE-DB vs. the original databases

The spurious-correctness evaluation set (800 gold-prediction pairs labelled `spurious`, `correct` or `wrong`) is in
`evaluation_sets/`; its sampling protocol and judging records are on `griffith-bigdata/core-db-spurious-correctness-evaluation-set`.

```bash
python scripts/score_evaluation_sets.py --set rq3_3b --coredb data/core-db \
    --bird-train-root data/bird/train/train_databases --spider-root data/spider    # also rq6_sample300
```

The current CoRE-DB includes bug fixes, so results can be better than in the paper (`rq3_3b`: FPR 10.1 % vs. 14.7 %).

## Build CoRE-DB

Five steps per database: compaction, gold-neighbor pairs, value filling, separation, greedy set-cover selection.
`griffith-bigdata/core-db-der215` is rebuilt from its compact database and pairs with the stored program
`value_filling_by_agents/<benchmark>/<db_id>/tscore_gen/`:

```bash
D=data/core-db/dbs/bird/trains
ORIGINAL_DB=data/bird/train/train_databases/trains/trains.sqlite COMPACT_DB=$D/compact/trains.sqlite \
    PAIRS_JSON=$D/pairs.json bash agentic_coding/build_db.sh bird trains      # -> coredb/dbs/bird/trains/
```

Set `OPENROUTER_API_KEY` and `AGENTIC=1` to write the program again with the Designer, Engineer and Reviewer agents.

## Training Reproduce

GRPO with the FINER-SQL trainer and rewards (`training/grpo_writer.py`), executed on CoRE-DB: one prompt x 32 rollouts per
step, learning rate 8e-6.

```bash
hf download griffith-bigdata/core-db-prompts --repo-type dataset --local-dir data/prompts --include "training/*"
python training/prepare_coredb_tree.py --coredb data/core-db --tree coredb_tree
bash training/serve_coredb.sh coredb_tree                  # execution endpoint http://127.0.0.1:8021/execute
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-Embedding-0.6B --task embed --port 9000 \
    --dtype float16 --max-model-len 8192 --gpu-memory-utilization 0.06 &         # embedder of the memory reward
D=data/prompts/training
python training/build_gt_cache.py --data $D/prompts/0.5b --out gt_cache.pkl
DATA_DIR=$D/prompts/0.5b GT_CACHE=gt_cache.pkl CHROMA_SEED=$D/chroma_seed/0.5b OUT_DIR=runs/0.5b \
    bash training/train.sh 0.5b                            # or 3b
```

## Hugging Face resources

| Resource | Hub id | Content |
|---|---|---|
| Model 0.5B | [griffith-bigdata/FINER-SQL-0.5B-v2](https://huggingface.co/griffith-bigdata/FINER-SQL-0.5B-v2) | GRPO on CoRE-DB from FINER-SQL-0.5B-BIRD |
| Model 1.5B | [griffith-bigdata/FINER-SQL-1.5B-v2](https://huggingface.co/griffith-bigdata/FINER-SQL-1.5B-v2) | GRPO on CoRE-DB from Qwen-2.5-Coder-1.5B-SQL-Writer |
| Model 3B | [griffith-bigdata/FINER-SQL-3B-v2](https://huggingface.co/griffith-bigdata/FINER-SQL-3B-v2) | GRPO on CoRE-DB from FINER-SQL-3B-BIRD |
| CoRE-DB | [griffith-bigdata/core-db-der215](https://huggingface.co/datasets/griffith-bigdata/core-db-der215) | compact databases + selected instances of the 215 training databases, generated by the programs in `value_filling_by_agents/` |
| Prompts | [griffith-bigdata/core-db-prompts](https://huggingface.co/datasets/griffith-bigdata/core-db-prompts) | training prompts and FINER-SQL memory stores (`training/`); BIRD dev, Spider dev and Spider test prompts and gold files (`evaluation/`) |
| Spurious-correctness evaluation set | [griffith-bigdata/core-db-spurious-correctness-evaluation-set](https://huggingface.co/datasets/griffith-bigdata/core-db-spurious-correctness-evaluation-set) | 800 gold-prediction pairs on 100 BIRD + 100 Spider training questions (152 spurious, 648 non-spurious), sampling protocol and judging records; rollouts of RQ6 |

## License

Apache-2.0 (see `LICENSE`). The BIRD and Spider databases keep their own licenses.
