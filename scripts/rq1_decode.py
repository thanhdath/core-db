"""RQ1 decodes: sampled (20 candidates, temperature 1.0) and greedy SQL for the 100 BIRD-train + 100 Spider-train
questions of ``evaluation_sets/rq1_questions200.jsonl`` (FINER-SQL prompt format, SQL after ``</think>``).

Output JSON lines: {"question_uid", "ds", "db", "gold_sql", "pred_sql", "decoding", "draw"}.
Usage:
    python scripts/rq1_decode.py --model thanhdath/FINER-SQL-0.5B-v2 --out outputs/rq1/finer05b.jsonl [--limit 5]
"""
import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / 'evaluation_sets' / 'rq1_questions200.jsonl'


def extract_sql(completion):
    """SQL after the last ``</think>`` tag ('' when missing)."""
    index = completion.rfind('</think>')
    return completion[index + len('</think>'):].strip() if index >= 0 else ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    questions = [json.loads(line) for line in open(QUESTIONS)]
    questions = questions[:args.limit] if args.limit else questions
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    prompts = [tokenizer.apply_chat_template(q['messages'], tokenize=False, add_generation_prompt=True)
               for q in questions]
    llm = LLM(model=args.model, max_model_len=4096, trust_remote_code=True)
    settings = {'sampled': SamplingParams(n=args.samples, temperature=1.0, max_tokens=2048, seed=42),
                'greedy': SamplingParams(n=1, temperature=0.0, max_tokens=2048)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'w') as out:
        for decoding, params in settings.items():
            for question, result in zip(questions, llm.generate(prompts, params)):
                for draw, candidate in enumerate(result.outputs):
                    out.write(json.dumps({'question_uid': question['question_uid'], 'ds': question['ds'],
                                          'db': question['db'], 'gold_sql': question['gold_sql'],
                                          'pred_sql': extract_sql(candidate.text), 'decoding': decoding,
                                          'draw': draw}) + '\n')


if __name__ == '__main__':
    main()
