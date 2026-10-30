"""Sample LLM-written neighbor queries for training questions with a text-to-SQL model (vLLM).

Input: a HF ``datasets`` folder (``save_to_disk``) with columns ``messages``, ``dataset_name``, ``db_id``
and ``groundtruth_sqls``.  For every question the model samples ``--n`` candidates at ``--temperature``;
the SQL after the last ``</think>`` tag is kept.  Output: JSON lines {"ds", "db", "gold", "pred", "model"},
read by ``build_pairs.py --llm-neighbors``.  The paper samples SQL-R1 7B and FINER-SQL 0.5B / 3B (N = 30, T = 1.0).
"""
import argparse
import json


def extract_sql(completion):
    """SQL after the last ``</think>`` tag (empty string when the tag is missing)."""
    index = completion.rfind('</think>')
    return completion[index + len('</think>'):].strip() if index >= 0 else ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', required=True, help='HF model id or local path')
    parser.add_argument('--data', required=True, help='datasets.save_to_disk folder of training prompts')
    parser.add_argument('--output', required=True)
    parser.add_argument('--n', type=int, default=30)
    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--limit', type=int, default=0, help='first N questions only (0 = all)')
    args = parser.parse_args()

    from datasets import load_from_disk
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    data = load_from_disk(args.data)
    if args.limit:
        data = data.select(range(min(args.limit, len(data))))
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    prompts = [tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=True)
               for row in data]
    llm = LLM(model=args.model, max_model_len=4096, trust_remote_code=True)
    params = SamplingParams(n=args.n, temperature=args.temperature, max_tokens=2048, seed=args.seed)
    with open(args.output, 'w') as out:
        for row, result in zip(data, llm.generate(prompts, params)):
            for candidate in result.outputs:
                sql = extract_sql(candidate.text)
                if sql:
                    out.write(json.dumps({'ds': row['dataset_name'], 'db': row['db_id'],
                                          'gold': row['groundtruth_sqls'][0], 'pred': sql,
                                          'model': args.model}) + '\n')


if __name__ == '__main__':
    main()
