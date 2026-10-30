# Small Language Models for Text-to-SQL against Spurious Correctness

Small language models (SLMs) make Text-to-SQL practical in settings with limited inference memory and computation,
while reinforcement learning (RL) can further improve their accuracy without increasing model size. However, commonly
used execution-based rewards are vulnerable to *spurious correctness*: a semantically incorrect query may receive a
positive reward simply because it happens to return the same result as the gold query on a particular database
instance. We propose CoRE-DB, a reusable, compact, counterexample-enriched database environment designed to reduce
such false-positive rewards. CoRE-DB first compacts each training database by retaining a small set of rows
sufficient to support its gold queries, including the rows referenced by those queries. It then constructs
gold-neighbor query pairs and employs three agents (Designer, Engineer, and Reviewer) to create and validate a
reusable generation program for each database. The program generates diverse candidate database instances while
preserving data consistency and satisfying applicable integrity constraints and semantic rules. We then execute the
gold and neighbor queries on these instances and apply greedy set cover to select a small, fixed subset that retains
the ability to distinguish semantically incorrect queries from their gold counterparts. The resulting environment can
be reused across training runs without requiring changes to the RL algorithm or its execution-based reward function.
Experiments on Spider and BIRD demonstrate improvements in both execution accuracy and training efficiency. These
findings highlight database design as a promising direction for improving RL-based Text-to-SQL without modifying the
underlying learning algorithms.

## Install

```bash
conda create -n coredb python=3.11 -y && conda activate coredb
pip install -r requirements.txt
```

The official BIRD and Spider databases are not redistributed. Download them and unpack them as
`data/bird/dev/` (dev.json, dev.sql, dev_databases/), `data/bird/train/train_databases/` and `data/spider/`
(database/, test_database/), or pass other locations with `--bird-dev-root`, `--bird-train-root` and
`--spider-root`. Models and prompts are downloaded from the Hugging Face Hub on first use; CoRE-DB (needed for RQ1,
RQ3, RQ6 and training) is downloaded with

```bash
python scripts/coredb_members.py --out data/core-db
```

## Reproduce

### RQ2: execution accuracy

k = 30 candidates at temperature 1.0 with seed 42 and vote-after-verify selection, or greedy decoding; at most 2048
generated tokens. BIRD dev is scored with the official BIRD script, Spider dev and Spider test with
taoyds/test-suite-sql-eval (commit e97acc54, cloned on first use).

```bash
python scripts/run_inference.py --model 0.5b --benchmark bird_dev --decoding k30     # one model, one benchmark
python scripts/run_inference.py --model 0.5b --benchmark bird_dev --limit 5          # smoke test
bash scripts/reproduce_rq2.sh                         # 3 models x {bird_dev, spider_dev, spider_test} x {k30, greedy}
```

Each run writes `outputs/<model>/<benchmark>_<decoding>/RESULT.json`. BIRD dev EX (1,534 questions):

| Model | k = 30 + VAV | Greedy |
|---|---:|---:|
| FINER-SQL-0.5B-v2 | 822 (53.59 %) | 673 (43.87 %) |
| FINER-SQL-1.5B-v2 | 978 (63.75 %) | 823 (53.65 %) |
| FINER-SQL-3B-v2 | 1055 (68.77 %) | 931 (60.69 %) |

### RQ1: spurious-correctness rate

20 samples at temperature 1.0 plus one greedy output for each of the 200 questions in
`evaluation_sets/rq1_questions200.jsonl`. A prediction that matches the gold on the original database is spurious
when CoRE-DB refuses it.

```bash
python scripts/rq1_decode.py --model thanhdath/FINER-SQL-0.5B-v2 --out outputs/rq1/finer05b.jsonl
python scripts/rq1_spurious_rate.py --predictions outputs/rq1/finer05b.jsonl --coredb data/core-db
```

### RQ3 and RQ6: CoRE-DB vs. the original databases

`evaluation_sets/` holds the labelled cases (`spurious`, `correct`, `wrong`): `rq3_spurious_train200_3b.jsonl` and
`rq3_spurious_train200_05b.jsonl` (800 RL rollouts each on 100 BIRD + 100 Spider training questions) and
`rq6_rollout_sample300.jsonl` (300 rollouts with operations unseen during construction). Sampling protocols and judging
records are on `thanhdath/core-db-evaluation-sets`.

```bash
python scripts/score_evaluation_sets.py --set rq3_3b --coredb data/core-db \
    --bird-train-root data/bird/train/train_databases --spider-root data/spider    # also rq3_05b, rq6_sample300
```

## Build CoRE-DB

Five steps per training database: compaction, gold-neighbor pairs from grammar mutations and LLM samples, value
filling by the database's generation program, separation, and greedy set-cover selection.

```bash
ORIGINAL_DB=data/bird/train/train_databases/airline/airline.sqlite GOLDS_JSON=airline_golds.json \
    bash agentic_coding/build_db.sh bird airline      # -> build/bird/airline/ and coredb/dbs/bird/airline/
```

`GOLDS_JSON` is a JSON list of the training gold SQL of the database. Step 3 runs the program written by the agents
for that database, `value_filling_by_agents/<benchmark>/<db_id>/tscore_gen/`, kept exactly as generated. To write it
again with the Designer, Engineer and Reviewer agents, set `OPENROUTER_API_KEY` and `AGENTIC=1`. LLM-sampled
neighbors come from `python -m agentic_coding.neighbor_query_generation.sample_llm_neighbors` and are passed with
`LLM_NEIGHBORS`. The works_cycles literal pool is on `thanhdath/core-db` (`agentic_repo/pools/`).

## Training

GRPO (TRL) with the format + execution reward computed only on CoRE-DB: one prompt x 32 rollouts per step,
learning rate 8e-6, beta 0.04, completion length 2048.

```bash
python training/prepare_coredb_tree.py --coredb data/core-db --tree coredb_tree
bash training/serve_coredb.sh coredb_tree                  # reward endpoint http://127.0.0.1:8021/execute
python training/build_gt_cache.py --data $DATA_DIR --out gt_cache.pkl
DATA_DIR=... GT_CACHE=gt_cache.pkl OUT_DIR=runs/0.5b bash training/train.sh 0.5b
```

`DATA_DIR` holds the training prompts (`datasets.save_to_disk`, columns `messages`, `dataset_name`, `db_id`,
`sample_id`, `groundtruth_sqls`). `training/train.sh` lists the GPUs, batch layout, steps and released checkpoint of
each model. The 1.5B and 3B runs continue from checkpoints trained first with the original FINER-SQL reward (1.5B:
750 steps, 3B: 1,750 steps).

## Hugging Face resources

| Resource | Hub id | Content |
|---|---|---|
| Model 0.5B | [thanhdath/FINER-SQL-0.5B-v2](https://huggingface.co/thanhdath/FINER-SQL-0.5B-v2) | GRPO on CoRE-DB from FINER-SQL-0.5B-BIRD |
| Model 1.5B | [thanhdath/FINER-SQL-1.5B-v2](https://huggingface.co/thanhdath/FINER-SQL-1.5B-v2) | GRPO on CoRE-DB from Qwen-2.5-Coder-1.5B-SQL-Writer |
| Model 3B | [thanhdath/FINER-SQL-3B-v2](https://huggingface.co/thanhdath/FINER-SQL-3B-v2) | GRPO on CoRE-DB from FINER-SQL-3B-BIRD |
| CoRE-DB | [thanhdath/core-db](https://huggingface.co/datasets/thanhdath/core-db) | compact databases + selected instances of the 215 training databases |
| Evaluation prompts | [thanhdath/core-db-evaluation-prompts](https://huggingface.co/datasets/thanhdath/core-db-evaluation-prompts) | BIRD dev, Spider dev, Spider test prompts and gold files |
| Evaluation sets | [thanhdath/core-db-evaluation-sets](https://huggingface.co/datasets/thanhdath/core-db-evaluation-sets) | full RQ3 / RQ6 evaluation folders (incl. judging dumps) |

## License

Apache-2.0 (see `LICENSE`). The BIRD and Spider databases keep their own licenses.
